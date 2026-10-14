"""Точка входа FastAPI: create_app(), REST, MCP (/mcp и /mcp/<module>), lifespan."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text

from .bootstrap import MODULES, build_container
from .kernel.errors import AppError
from .kernel.tools.mcp_adapter import build_mcp_server

log = logging.getLogger("learnos.main")

_CONTAINER = None


def get_container():
    """Текущий контейнер приложения (создаётся при первом обращении)."""
    global _CONTAINER
    if _CONTAINER is None:
        _CONTAINER = build_container()
    return _CONTAINER


def migrate_db(container) -> None:
    """Применить миграции Alembic; при ошибке — схема из метаданных (дев/тесты)."""
    try:
        from alembic import command
        from alembic.config import Config

        from .kernel.config import SERVER_DIR

        alembic_cfg = Config(str(SERVER_DIR / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(SERVER_DIR / "migrations"))
        alembic_cfg.set_main_option("sqlalchemy.url", container.settings.db_url)
        command.upgrade(alembic_cfg, "head")
    except Exception:  # noqa: BLE001 — миграций нет/ошибка: честная схема из метаданных
        log.warning("alembic upgrade не удался, создаю схему из метаданных", exc_info=True)
        from .kernel.db import metadata

        engine = create_engine(container.settings.db_url)
        metadata.create_all(bind=engine)
        engine.dispose()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Старт: миграции, FTS, категории по умолчанию, воркер jobs, MCP-сессии."""
    container = app.state.container
    migrate_db(container)

    from .modules.search.infra.fts import ensure_fts

    with container.uow() as uow:
        uow.session.execute(text("SELECT 1"))
        ensure_fts(uow.session)
    container.knowledge.ensure_categories_default()

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

    # локальный сервис: веб-чат ходит напрямую, CORS открыт для локальных источников
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["mcp-session-id"],
    )

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content={"error": exc.code, "message": exc.message})

    @app.get("/api/health", tags=["system"])
    def health():
        llm = container.llm_router.status()
        return {
            "ok": True,
            "llm_configured": llm["configured"],
            "model": llm["model"],
            "provider": llm["provider"],
            "llm_reason": llm.get("reason"),
            "worker_running": container.job_worker.running if container.job_worker else False,
            "tools": len(container.tools.all()),
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
    ):
        module_tools = container.tools.by_module(name)
        if module_tools:
            app.state.mcp_servers[f"/mcp/{name}"] = build_mcp_server(
                f"learnos-{name}", container.tools, module_tools
            )
    for path, server in app.state.mcp_servers.items():
        sub = server.streamable_http_app(streamable_http_path=path)
        app.router.routes.extend(sub.routes)

    return app


app = create_app()
