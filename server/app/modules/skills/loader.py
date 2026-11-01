"""Загрузчик скиллов: builtin (server/skills) и агентские (data/agent-skills, T-037).

Builtin — доверенный код продукта, исполняется в процессе. Агентские — песочница:
отдельный subprocess (sys.executable), cwd = каталог скилла, таймаут из настроек,
разрешённая запись передаётся переменной окружения LEARNOS_WRITE_DIR.
"""

import importlib.util
import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, create_model

from ...kernel.errors import NotFound
from ...kernel.tools.spec import ToolContext, ToolSpec

log = logging.getLogger("learnos.skills")

_TYPES = {
    "str": (str, ...),
    "string": (str, ...),
    "int": (int, ...),
    "float": (float, ...),
    "bool": (bool, ...),
}

# файлы скилла; переопределение builtin-скилла — теми же именами в data/skill-overrides
SKILL_FILES = ("SKILL.md", "run.py")

# что видно subprocess-скиллу из окружения сервиса: никакого ZAI_API_KEY/TAVILY/…
# (R-06: раньше env наследовался целиком — инжект через save_skill мог слить ключи)
_ENV_ALLOWLIST = frozenset(
    {
        "PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TMPDIR",
        "PYTHONIOENCODING",
        "PYTHONDONTWRITEBYTECODE",
        "SSL_CERT_FILE",
        "REQUESTS_CA_BUNDLE",
    }
)


def _sandbox_env(args_json: str, result_path: str, write_dir: Path) -> dict[str, str]:
    """Env для subprocess-скилла: только рабочий минимум + LEARNOS_SKILL_* и WRITE_DIR."""
    env = {k: v for k, v in os.environ.items() if k in _ENV_ALLOWLIST or k.startswith("LEARNOS_SKILL_")}
    env.update(
        {
            "LEARNOS_SKILL_ARGS": args_json,
            "LEARNOS_SKILL_RESULT": result_path,
            "LEARNOS_WRITE_DIR": str(write_dir),
        }
    )
    return env


# протокол subprocess-песочницы: run.py.main(**LEARNOS_SKILL_ARGS) → JSON в LEARNOS_SKILL_RESULT
_RUNNER = """\
import importlib.util, json, os, sys
try:  # лимит памяти песочницы (linux; на mac RLIMIT_AS не работает — пропускаем)
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024,) * 2)
except Exception:
    pass
spec = importlib.util.spec_from_file_location("agent_skill", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
result = mod.main(**json.loads(os.environ.get("LEARNOS_SKILL_ARGS", "{}")))
result = result if isinstance(result, dict) else {"ok": True, "result": result}
with open(os.environ["LEARNOS_SKILL_RESULT"], "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, default=str)
"""


def _parse_frontmatter(text: str) -> dict:
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("SKILL.md: нет блока frontmatter")
    meta = yaml.safe_load(parts[1]) or {}
    if isinstance(meta.get("params"), str):
        meta["params"] = json.loads(meta["params"])
    return meta


def _load_entry(run_py: Path):
    spec = importlib.util.spec_from_file_location(f"skill_{run_py.parent.name}", run_py)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.main


def _clip(text: str | None, limit: int = 2000) -> str:
    """Обрезка stdout/stderr для результата инструмента."""
    if not text:
        return ""
    return text if len(text) <= limit else text[:limit] + f"… (обрезано, всего {len(text)})"


class SkillLoader:
    """Читает скиллы с диска и превращает их в ToolSpec.

    builtin: server/skills/<name>/ (код продукта, override из data/skill-overrides/<name>/).
    агентские: data/agent-skills/<agent>/<skill>/ — владелец из пути, исполнение в subprocess.
    """

    def __init__(self, settings) -> None:
        self._settings = settings
        self._skills_dir = Path(settings.skills_dir)
        self._agent_dir = Path(settings.data_dir) / "agent-skills"
        self._override_dir = Path(settings.data_dir) / "skill-overrides"
        self._registry: dict[str, dict[str, Any]] = {}

    # --- сканирование ---

    def load(self) -> dict[str, dict[str, Any]]:
        """Перечитать скиллы с диска (старт сервиса и горячая перезагрузка)."""
        self._registry.clear()
        for skill_dir in sorted(p for p in self._skills_dir.glob("*") if p.is_dir()):
            self._load_builtin(skill_dir)
        for skill_dir in sorted(p for p in self._agent_dir.glob("*/*") if p.is_dir()):
            self._load_agent(skill_dir)
        return self._registry

    def _load_builtin(self, skill_dir: Path) -> None:
        meta = self._read_meta(self._resolve(skill_dir, "SKILL.md"))
        name = meta.get("name", skill_dir.name)
        self._registry[name] = {
            "name": name,
            "description": meta.get("description", ""),
            "params": meta.get("params") or {},
            "owner": None,
            "kind": "builtin",
            "dir": skill_dir,
            "entry": _load_entry(self._resolve(skill_dir, "run.py")),
        }

    def _load_agent(self, skill_dir: Path) -> None:
        try:
            meta = self._read_meta(skill_dir / "SKILL.md")
        except Exception as e:  # noqa: BLE001 — битый агентский скилл не должен ронять старт
            log.warning("агентский скилл %s пропущен: %s", skill_dir, e)
            return
        name = meta.get("name", skill_dir.name)
        if name in self._registry:
            log.warning(
                "агентский скилл %s (%s) пропущен: имя '%s' уже занято", skill_dir.parent.name, name, name
            )
            return
        self._registry[name] = {
            "name": name,
            "description": meta.get("description", ""),
            "params": meta.get("params") or {},
            "owner": skill_dir.parent.name,
            "kind": "agent",
            "dir": skill_dir,
        }

    def _read_meta(self, skill_md: Path) -> dict:
        return _parse_frontmatter(skill_md.read_text(encoding="utf-8"))

    def _resolve(self, skill_dir: Path, filename: str) -> Path:
        """Файл builtin-скилла с учётом override из data/skill-overrides (правки карточкой)."""
        override = self._override_dir / skill_dir.name / filename
        return override if override.is_file() else skill_dir / filename

    # --- справочники ---

    def _ready(self) -> dict[str, dict[str, Any]]:
        if not self._registry:
            self.load()
        return self._registry

    def names(self) -> set[str]:
        return set(self._ready())

    def builtin_names(self) -> set[str]:
        return {n for n, s in self._ready().items() if s["kind"] == "builtin"}

    def agent_skill_names(self) -> set[str]:
        return {n for n, s in self._ready().items() if s["kind"] == "agent"}

    def names_owned_by(self, agent: str) -> set[str]:
        return {n for n, s in self._ready().items() if s["owner"] == agent}

    def owners_of(self, name: str) -> set[str]:
        skill = self._ready().get(name)
        return {skill["owner"]} if skill and skill["owner"] else set()

    def kind_of(self, name: str) -> str | None:
        skill = self._ready().get(name)
        return skill["kind"] if skill else None

    def builtin_file(self, name: str, filename: str) -> Path:
        """Путь файла builtin-скилла из кода (без override) — для propose_change."""
        skill = self._ready().get(name)
        if skill is None or skill["kind"] != "builtin":
            raise NotFound(f"builtin-скилл '{name}' не найден")
        path = skill["dir"] / filename
        if not path.is_file():
            raise NotFound(f"у скилла '{name}' нет файла {filename}")
        return path

    def effective_file(self, name: str, filename: str) -> Path:
        """Действующий файл builtin-скилла (override, если применён)."""
        skill = self._ready().get(name)
        if skill is None or skill["kind"] != "builtin":
            raise NotFound(f"builtin-скилл '{name}' не найден")
        return self._resolve(skill["dir"], filename)

    def agent_skill_dir(self, owner: str, skill_name: str) -> Path:
        return self._agent_dir / owner / skill_name

    def info(self) -> list[dict[str, Any]]:
        """Список скиллов с параметрами (для list_skills)."""
        if not self._registry:
            self.load()
        return [
            {
                "name": s["name"],
                "description": s["description"],
                "params": s["params"],
                "owner": s["owner"],
                "kind": s["kind"],
            }
            for s in self._registry.values()
        ]

    # --- исполнение ---

    def run(self, name: str, kwargs: dict[str, Any], caller: str | None = None) -> dict[str, Any]:
        """Выполнить скилл по имени; агентский — только владелец или root."""
        if not self._registry:
            self.load()
        skill = self._registry.get(name)
        if skill is None:
            return {
                "error": "skill_not_found",
                "message": f"скилл '{name}' не найден",
                "available": sorted(self._registry),
            }
        if skill["kind"] == "agent" and caller not in (skill["owner"], "root"):
            return {
                "error": "not_allowed",
                "message": (
                    f"скилл '{name}' принадлежит агенту '{skill['owner']}' — вызвать может владелец или root"
                ),
            }
        if skill["kind"] == "agent":
            return self._exec(skill, kwargs)
        try:
            result = skill["entry"](**kwargs)
        except TypeError as e:
            return {
                "error": "validation_failed",
                "message": f"неверные аргументы: {e}",
                "params": skill["params"],
            }
        return result if isinstance(result, dict) else {"ok": True, "result": result}

    def _exec(self, skill: dict[str, Any], kwargs: dict[str, Any]) -> dict[str, Any]:
        """Subprocess-песочница агентского скилла: таймаут, stdout/stderr/код выхода в результате."""
        skill_dir: Path = skill["dir"]
        timeout = self._settings.skill_exec_timeout
        fd, result_path = tempfile.mkstemp(suffix=".json", prefix="learnos-skill-")
        os.close(fd)
        # своя песочница на скилл: пишут только сюда; learnos.db больше не сосед
        write_dir = Path(self._settings.data_dir) / "skill-work" / (skill["owner"] or "_") / skill["name"]
        write_dir.mkdir(parents=True, exist_ok=True)
        env = _sandbox_env(json.dumps(kwargs, ensure_ascii=False, default=str), result_path, write_dir)
        try:
            try:
                # код скилла агент пишет сам; изоляция — subprocess + таймаут + контейнер на проде
                proc = subprocess.run(
                    [sys.executable, "-c", _RUNNER, str(skill_dir / "run.py")],
                    cwd=skill_dir,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired as e:
                return {
                    "error": "skill_timeout",
                    "message": f"скилл превысил {timeout} с и был остановлен",
                    "stdout": _clip(e.stdout),
                    "stderr": _clip(e.stderr),
                }
            details = {
                "exit_code": proc.returncode,
                "stdout": _clip(proc.stdout),
                "stderr": _clip(proc.stderr),
            }
            if proc.returncode != 0:
                return {
                    "error": "skill_failed",
                    "message": f"run.py завершился с кодом {proc.returncode}",
                    **details,
                }
            try:
                payload = json.loads(Path(result_path).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return {
                    "error": "skill_failed",
                    "message": "main() не вернул словарь (файл результата пуст или битый)",
                    **details,
                }
            return {**payload, **details}
        finally:
            Path(result_path).unlink(missing_ok=True)

    # --- инструменты ---

    def tool_specs(self) -> list[ToolSpec]:
        """Спецификации: run_skill + авто-скиллы как отдельные инструменты."""
        if not self._registry:
            self.load()

        def run_skill(args: RunSkillArgs, ctx: ToolContext) -> dict[str, Any]:
            return self.run(args.name, args.kwargs, caller=ctx.agent_name)

        def list_skills(args: _EmptyArgs, ctx: ToolContext) -> list[dict[str, Any]]:
            del ctx
            return self.info()

        specs = [
            ToolSpec(
                name="run_skill",
                module="skills",
                description="Выполнить drop-in скилл. kwargs — аргументы согласно list_skills.",
                args_model=RunSkillArgs,
                handler=run_skill,
                label="Скилл",
            ),
            ToolSpec(
                name="list_skills",
                module="skills",
                description="Доступные drop-in скиллы и их параметры.",
                args_model=_EmptyArgs,
                handler=list_skills,
                label="Список скиллов",
            ),
        ]
        for name, skill in self._registry.items():
            specs.append(self._skill_spec(name, skill))
        return specs

    def _skill_spec(self, name: str, skill: dict[str, Any]) -> ToolSpec:
        fields: dict[str, Any] = {}
        for pname, p in skill["params"].items():
            ann, default = _TYPES.get(str(p.get("type", "str")), (str, ...))
            if p.get("optional"):
                # optional без дефолта получает None: аннотация X | None, чтобы MCP-клиент
                # мог не передавать поле вовсе (иначе null ломает pydantic-валидацию)
                default = p.get("default")
                ann = ann | None
            fields[pname] = (ann, default)
        model = create_model(f"{name}_args", **fields) if fields else _EmptyArgs

        def handler(args: BaseModel, ctx: ToolContext) -> dict[str, Any]:
            # None-параметры не доходят до run.py: скиллы ждут дефолты («»), а не None
            kwargs = {k: v for k, v in args.model_dump().items() if v is not None}
            return self.run(name, kwargs, caller=ctx.agent_name if ctx else None)

        params_brief = ", ".join(
            f"{p}:{p_['type']}" + ("?" if p_.get("optional") else "") for p, p_ in skill["params"].items()
        )
        return ToolSpec(
            name=name,
            module="skills",
            description=f"{skill['description']} Параметры: {params_brief or '—'}",
            args_model=model,
            handler=handler,
            label=f"Скилл {name}",
        )


class RunSkillArgs(BaseModel):
    """Аргументы run_skill."""

    name: str
    kwargs: dict[str, Any] = {}


class _EmptyArgs(BaseModel):
    """Скилл без параметров."""
