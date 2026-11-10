"""Точка входа FastAPI: create_app(), REST, MCP (/mcp и /mcp/<module>), lifespan."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .bootstrap import MODULES, build_container
from .kernel.clock import now_iso
from .kernel.errors import AppError, NotFound
from .kernel.tools.mcp_adapter import build_mcp_server

log = logging.getLogger("learnos.main")

_CONTAINER = None


def get_container():
    """Текущий контейнер приложения (создаётся при первом обращении)."""
    global _CONTAINER
    if _CONTAINER is None:
        _CONTAINER = build_container()
    return _CONTAINER


def _backup_sqlite(container) -> Path | None:
    """Консистентный бэкап БД перед миграцией (sqlite3 .backup, R-21/G аудита).

    Копия файла без -wal может быть неконсистентной — используем API бэкапа.
    """
    url = container.settings.db_url
    if not url.startswith("sqlite:///"):
        return None
    db_path = Path(url.removeprefix("sqlite:///"))
    if not db_path.exists():
        return None
    backup_dir = Path(container.settings.data_dir) / "db-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = now_iso(container.clock)[:19].replace(":", "").replace("-", "")
    target = backup_dir / f"learnos-{stamp}-pre-migrate.db"
    import sqlite3

    src = sqlite3.connect(db_path)
    try:
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    # ротация: последние 10
    old = sorted(backup_dir.glob("learnos-*-pre-migrate.db"))[:-10]
    for stale in old:
        stale.unlink(missing_ok=True)
    log.info("бэкап БД перед миграцией: %s", target.name)
    return target


def migrate_db(container) -> None:
    """Миграции Alembic (fail-fast, R-21/G): перед прогоном — бэкап БД.

    Тихий fallback на create_all раньше прятал дрейф схемы: таблицы не
    меняются у существующих колонок, падения вылезали позже и страннее.
    Первая схема (БД нет) создаётся миграцией 0001 — fallback не нужен.
    """
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    from .kernel.config import SERVER_DIR

    alembic_cfg = Config(str(SERVER_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(SERVER_DIR / "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", container.settings.db_url)

    engine = create_engine(container.settings.db_url)
    try:
        has_version = inspect(engine).has_table("alembic_version")
        has_schema = inspect(engine).has_table("blocks")
    finally:
        engine.dispose()
    if not has_version and has_schema:
        # схема создана из метаданных (dev/тесты) — помечаем head без прогона;
        # источник схемы тот же код, расхождения нет
        command.stamp(alembic_cfg, "head")
        return

    _backup_sqlite(container)
    command.upgrade(alembic_cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Старт: миграции, FTS, категории по умолчанию, кастомные агенты, воркер jobs, MCP-сессии."""
    container = app.state.container
    migrate_db(container)

    # генерации прошлого процесса погибли вместе с ним: зависшие running честно
    # помечаем interrupted — клиент видит баннер «генерация прервана» и может продолжить
    if container.run_recorder is not None:
        stale = container.run_recorder.interrupt_stale_running()
        if stale:
            log.info("зависших running-запусков помечено interrupted: %d", stale)

    from .modules.search.infra.fts import ensure_fts

    with container.uow() as uow:
        uow.session.execute(text("SELECT 1"))
        ensure_fts(uow.session)
    container.knowledge.ensure_categories_default()
    if container.tuning is not None:
        loaded = container.tuning.load_custom_agents()
        if loaded:
            log.info("кастомных агентов загружено: %d", loaded)
    if container.mcpext is not None:
        loaded = container.mcpext.load_on_start()
        if loaded:
            log.info("внешних MCP с инструментами: %d", loaded)

    worker = container.job_worker
    if worker is not None:
        await worker.start()

    managers = []
    for server in app.state.mcp_servers.values():
        cm = server.session_manager.run()
        await cm.__aenter__()
        managers.append(cm)
    try:
        yield
    finally:
        if worker is not None:
            await worker.stop()
        for cm in managers:
            try:
                await cm.__aexit__(None, None, None)
            except Exception:  # noqa: BLE001
                log.debug("session_manager close", exc_info=True)


def create_app() -> FastAPI:
    """Собрать приложение: роуты модулей + health + MCP-серверы."""
    container = get_container()
    app = FastAPI(title="learnos", version="0.2.0", lifespan=lifespan)
    app.state.container = container
    app.state.mcp_servers = {}

    from fastapi.middleware.cors import CORSMiddleware

    settings = container.settings

    # локальный сервис: веб-чат ходит через Next-прокси (same-origin); CORS открыт
    # для перечисленных источников (LEARNOS_CORS_ORIGINS), по умолчанию — как раньше
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()] or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["mcp-session-id"],
    )

    if settings.api_token:

        @app.middleware("http")
        async def require_bearer_token(request: Request, call_next):  # noqa: ANN202
            """R-07: без токена /api и /mcp открыты всей LAN и DNS-rebinding'у.

            /api/health остаётся открытым (мониторинг деплоя), preflight — тоже.
            """
            open_paths = ("/api/health",)
            if request.method != "OPTIONS" and not request.url.path.startswith(open_paths):
                expected = f"Bearer {settings.api_token}"
                if request.headers.get("authorization") != expected:
                    return JSONResponse(
                        status_code=401,
                        content={"error": "unauthorized", "message": "нужен Authorization: Bearer <токен>"},
                    )
            return await call_next(request)

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content={"error": exc.code, "message": exc.message})

    @app.get("/api/health", tags=["system"])
    def health():
        llm = container.llm_router.status()
        return {
            "ok": True,
            "llm_configured": llm["configured"],
            "llm_keys": llm["keys"],
            "model": llm["model"],
            "provider": llm["provider"],
            "llm_reason": llm.get("reason"),
            "worker_running": container.job_worker.running if container.job_worker else False,
            "tools": len(container.tools.all()),
            # счётчики для доков (R-28): единственный источник правды о размерах
            "modules": len({t.module for t in container.tools.all()}),
        }

    @app.get("/api/llm/status", tags=["system"])
    def llm_status():
        """Детальный статус LLM: роли → модель/провайдер/params, цепочки ключей с cooldown.

        health открыт без токена — детализацию (ключи, cooldown) отдаёт только
        этот эндпоинт под bearer (BB-004). Значения ключей не отдаются нигде.
        """
        return container.llm_router.detailed_status()

    @app.get("/api/runs", tags=["system"])
    def runs(limit: int = 50, agent: str | None = None, status: str | None = None):
        """Трейсы запусков агентов (агрегаты): что, когда, сколько токенов (R-24)."""
        from sqlalchemy import select

        from .agent.infra_tables import agent_runs_table

        stmt = select(agent_runs_table).order_by(agent_runs_table.c.id.desc()).limit(min(limit, 200))
        if agent:
            stmt = stmt.where(agent_runs_table.c.agent == agent)
        if status:
            stmt = stmt.where(agent_runs_table.c.status == status)
        with container.uow() as uow:
            rows = uow.session.execute(stmt).mappings().all()
        return [dict(r) for r in rows]

    @app.get("/api/runs/{run_id}", tags=["system"])
    def run_detail(run_id: int):
        """Запуск целиком: агрегаты + трасса шагов + дочерние запуски субагентов (R-24)."""
        from sqlalchemy import select

        from .agent.infra_tables import agent_runs_table, agent_steps_table

        with container.uow() as uow:
            run = (
                uow.session.execute(select(agent_runs_table).where(agent_runs_table.c.id == run_id))
                .mappings()
                .first()
            )
            if run is None:
                raise NotFound(f"запуск {run_id} не найден")
            steps = (
                uow.session.execute(
                    select(agent_steps_table)
                    .where(agent_steps_table.c.run_id == run_id)
                    .order_by(agent_steps_table.c.id)
                )
                .mappings()
                .all()
            )
            children = (
                uow.session.execute(
                    select(agent_runs_table).where(agent_runs_table.c.parent_run_id == run_id)
                )
                .mappings()
                .all()
            )
        return {
            "run": dict(run),
            "steps": [dict(st) for st in steps],
            "children": [dict(ch) for ch in children],
        }

    for module in MODULES:
        for router in module.routers(container):
            app.include_router(router, prefix="/api")

    # MCP: общий сервер + узкие по модулям (роуты с абсолютными путями, без mount-префиксов)
    app.state.mcp_servers["/mcp"] = build_mcp_server("learnos", container.tools, container.tools.all())
    for name in (
        "knowledge",
        "library",
        "learning",
        "chat",
        "courses",
        "profile",
        "search",
        "export",
        "skills",
        "revision",
    ):
        module_tools = container.tools.by_module(name)
        if module_tools:
            app.state.mcp_servers[f"/mcp/{name}"] = build_mcp_server(
                f"learnos-{name}", container.tools, module_tools
            )
    for path, server in app.state.mcp_servers.items():
        # MCP по LAN (192.168.0.132) и из compose-сети (server) — иначе SDK-защита от
        # DNS-rebind отвечает «Invalid Host header» на всё, кроме localhost
        from mcp.server.transport_security import TransportSecuritySettings

        sub = server.streamable_http_app(
            streamable_http_path=path,
            transport_security=TransportSecuritySettings(
                allowed_hosts=[
                    "localhost:*",
                    "127.0.0.1:*",
                    "[::1]:*",
                    "192.168.0.132:*",
                    "server:*",
                ]
            ),
        )
        app.router.routes.extend(sub.routes)

    return app


app = create_app()
