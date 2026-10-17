"""Сервис mcpext: сторонние MCP-подключения — CRUD, проверка, обёртки инструментов для агентов."""

import json
import logging
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ...agent.spec import AgentContext
from ...kernel.asyncio_bridge import run_coro_sync
from ...kernel.clock import SystemClock, now_iso
from ...kernel.db import UnitOfWorkFactory
from ...kernel.errors import Conflict, NotFound, ValidationFailed
from ...kernel.tools.spec import ToolSpec
from .agents import mcp_designer, valid_mcp_name
from .gateway import call_remote_tool, describe_error, list_remote_tools
from .infra.tables import external_mcps

log = logging.getLogger("learnos.mcpext")

SERVER_ROOT = Path(__file__).resolve().parents[3]  # server/
BUILTIN_CONFIG = SERVER_ROOT / "config" / "external-mcp.json"  # подключения из git (дефолты)

_NAME_SANITIZE = re.compile(r"[^a-z0-9_]")


def _tool_wrapper_name(mcp_name: str, tool: str) -> str:
    return f"mcp_{_NAME_SANITIZE.sub('_', mcp_name.lower())}_{_NAME_SANITIZE.sub('_', tool.lower())}"


class McpExtService:
    """Use-cases внешних MCP: добавить по ссылке/конфигу, проверить, дать инструменты агентам."""

    def __init__(self, uow: UnitOfWorkFactory, tools_registry, runtime=None) -> None:
        self._uow = uow
        self._tools = tools_registry
        self._runtime = runtime
        self._clock = SystemClock()
        self._registered: dict[str, list[str]] = {}  # mcp name → имена обёрток в реестре

    # --- список/каталог ---

    def list_mcps(self) -> list[dict]:
        """Подключения с числом инструментов и статусом."""
        with self._uow() as uow:
            rows = uow.session.execute(external_mcps.select().order_by(external_mcps.c.id)).all()
        out = []
        for r in rows:
            tools = json.loads(r.tools_json or "[]")
            out.append(
                {
                    "name": r.name,
                    "url": r.url,
                    "description": r.description,
                    "enabled": bool(r.enabled),
                    "status": r.status,
                    "last_error": r.last_error,
                    "tools_count": len(tools),
                    "tool_names": sorted(t["name"] for t in tools),
                    "created_at": r.created_at,
                }
            )
        return out

    # --- проверка и конструктор ---

    def probe(self, url: str, headers: dict[str, str] | None = None) -> dict:
        """Живая проверка endpoint: список инструментов или понятная ошибка."""
        if not _is_http_url(url):
            return {"ok": False, "error": "нужна http(s)-ссылка на MCP-сервер (streamable http)"}
        try:
            tools = run_coro_sync(list_remote_tools(url.strip(), headers))
        except BaseException as e:  # noqa: BLE001 — недоступный сервер не должен ронять вызов
            log.warning("probe %s не удался: %s", url, describe_error(e))
            return {"ok": False, "error": describe_error(e)[:300]}
        return {"ok": True, "tools": tools, "count": len(tools)}

    def draft(self, brief: str) -> dict:
        """Разобрать ссылку/файл/описание в конфиг (mcp_designer)."""
        if not brief.strip():
            raise ValidationFailed("пришли ссылку, JSON-конфиг или описание")
        if self._runtime is None:
            raise NotFound("LLM не настроен — конструктор недоступен")
        out = run_coro_sync(self._runtime.run_structured(mcp_designer, AgentContext(), brief))
        name = out.name.strip().lower().replace(" ", "_").replace("-", "_")
        return {
            "name": name if valid_mcp_name(name) else "",
            "url": out.url.strip(),
            "description": out.description.strip(),
            "headers": {str(k): str(v) for k, v in (out.headers or {}).items()},
            "summary": out.summary.strip(),
        }

    # --- CRUD ---

    def create(self, name: str, url: str, description: str = "", headers: dict | None = None) -> dict:
        """Подключить сервер: сохранить, проверить, обёртки инструментов — в реестр."""
        name = (name or "").strip()
        if not valid_mcp_name(name):
            raise ValidationFailed("имя: латиница/цифры/_, начинается с буквы")
        if not _is_http_url(url):
            raise ValidationFailed("поддерживаются remote MCP по http(s) — локальный stdio пока нельзя")
        if self._get_row(name) is not None:
            raise Conflict(f"подключение '{name}' уже есть")
        now = now_iso(self._clock)
        with self._uow() as uow:
            uow.session.execute(
                external_mcps.insert().values(
                    name=name,
                    url=url.strip(),
                    description=(description or "").strip(),
                    headers_json=json.dumps(headers or {}),
                    tools_json="[]",
                    enabled=1,
                    status="unchecked",
                    created_at=now,
                    updated_at=now,
                )
            )
        return self.refresh(name)

    def refresh(self, name: str) -> dict:
        """Перепроверить сервер: обновить кэш инструментов и обёртки в реестре."""
        row = self._get_row(name)
        if row is None:
            raise NotFound(f"подключение '{name}' не найдено")
        headers = json.loads(row.headers_json or "{}")
        result = self.probe(row.url, headers)
        now = now_iso(self._clock)
        if result["ok"]:
            tools_json = json.dumps(result["tools"], ensure_ascii=False)
            with self._uow() as uow:
                uow.session.execute(
                    external_mcps.update()
                    .where(external_mcps.c.name == name)
                    .values(tools_json=tools_json, status="ok", last_error=None, updated_at=now)
                )
            self._register_wrappers(name, row.url, headers, result["tools"])
        else:
            with self._uow() as uow:
                uow.session.execute(
                    external_mcps.update()
                    .where(external_mcps.c.name == name)
                    .values(status="error", last_error=result["error"][:400], updated_at=now)
                )
        return {
            "ok": True,  # операция прошла; живость сервера — в connected/status
            "connected": result["ok"],
            "status": "ok" if result["ok"] else "error",
            "mcp": name,
            "tools": result.get("count", 0),
            "error": result.get("error"),
        }

    def delete(self, name: str) -> dict:
        """Отключить сервер: обёртки снять, запись удалить."""
        if self._get_row(name) is None:
            raise NotFound(f"подключение '{name}' не найдено")
        with self._uow() as uow:
            uow.session.execute(external_mcps.delete().where(external_mcps.c.name == name))
        self._unregister_wrappers(name)
        return {"ok": True, "deleted": name}

    # --- старт: БД + дефолты из git-конфига ---

    def load_on_start(self) -> int:
        """Зарегистрировать обёртки из БД (кэш инструментов); дефолты из config/external-mcp.json."""
        self._import_builtin_config()
        with self._uow() as uow:
            rows = uow.session.execute(external_mcps.select()).all()
        loaded = 0
        for r in rows:
            tools = json.loads(r.tools_json or "[]")
            if r.enabled and tools:
                self._register_wrappers(r.name, r.url, json.loads(r.headers_json or "{}"), tools)
                loaded += 1
        return loaded

    def wrapper_specs(self) -> list[ToolSpec]:
        """Обёртки для Module.tools (стартовая регистрация в реестре)."""
        # load_on_start уже регистрирует напрямую; метод оставлен для контракта модуля
        return []

    # --- внутреннее ---

    def _import_builtin_config(self) -> None:
        """config/external-mcp.json (в git): импортировать отсутствующие подключения."""
        if not BUILTIN_CONFIG.is_file():
            return
        try:
            items = json.loads(BUILTIN_CONFIG.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("битый %s — пропускаю", BUILTIN_CONFIG)
            return
        for item in items:
            name, url = str(item.get("name", "")).strip(), str(item.get("url", "")).strip()
            if not valid_mcp_name(name) or not _is_http_url(url) or self._get_row(name) is not None:
                continue
            now = now_iso(self._clock)
            with self._uow() as uow:
                uow.session.execute(
                    external_mcps.insert().values(
                        name=name,
                        url=url,
                        description=str(item.get("description", ""))[:200],
                        headers_json=json.dumps(item.get("headers") or {}),
                        tools_json="[]",
                        enabled=1,
                        status="unchecked",
                        created_at=now,
                        updated_at=now,
                    )
                )
            log.info("импортирован MCP из git-конфига: %s", name)

    def _get_row(self, name: str):
        with self._uow() as uow:
            row = uow.session.execute(external_mcps.select().where(external_mcps.c.name == name)).first()
        return row

    def _register_wrappers(self, mcp_name: str, url: str, headers: dict, tools: list[dict]) -> None:
        """Обёртки инструментов сервера → ToolRegistry (канал agent; вызов ленивый)."""
        self._unregister_wrappers(mcp_name)
        names = []
        for t in tools:
            wname = _tool_wrapper_name(mcp_name, t["name"])
            if self._tools.has(wname):
                log.warning("конфликт имени инструмента %s — пропускаю", wname)
                continue
            desc = (t.get("description") or "").strip()[:300]
            self._tools.register(
                ToolSpec(
                    name=wname,
                    module="mcpext",
                    description=f"[{mcp_name}] {desc or t['name']}",
                    args_model=_make_args_model(),
                    handler=_remote_handler(url, t["name"], headers),
                    channels=frozenset({"agent"}),
                    label=f"MCP {mcp_name}: {t['name']}",
                )
            )
            names.append(wname)
        self._registered[mcp_name] = names
        log.info("MCP %s: зарегистрировано инструментов %d", mcp_name, len(names))

    def _unregister_wrappers(self, mcp_name: str) -> None:
        for wname in self._registered.pop(mcp_name, []):
            self._tools.unregister(wname)


def _is_http_url(url: str) -> bool:
    return isinstance(url, str) and url.strip().lower().startswith(("http://", "https://"))


def _make_args_model() -> type[BaseModel]:
    """Аргументы произвольные: валидацию делает сам удалённый сервер."""

    class _RemoteArgs(BaseModel):
        model_config = ConfigDict(extra="allow")

    return _RemoteArgs


def _remote_handler(url: str, tool: str, headers: dict):
    def handler(args, ctx):  # noqa: ANN001, ANN202 — сигнатура ToolSpec
        del ctx
        payload = args.model_dump(exclude_none=True) if isinstance(args, BaseModel) else dict(args)
        try:
            return run_coro_sync(call_remote_tool(url, tool, payload, headers))
        except Exception as e:  # noqa: BLE001 — внешний сервер недоступен — сообщаем агенту
            return {"error": "remote_unavailable", "message": str(e)[:300]}

    return handler
