"""Общие фикстуры тестов LearnOS: tmp-каталоги, контейнер с FakeLLM, REST-клиент.

Контейнер строится напрямую build_container(settings) — без create_app и
get_settings, чтобы тесты не зависели от кэша настроек и реальных каталогов.
"""

from pathlib import Path

import pytest

from app.bootstrap import build_container, create_all_tables
from app.kernel.config import Settings, get_settings
from app.llm.providers.fake import FakeLLMProvider

SERVER_DIR = Path(__file__).resolve().parent.parent
SKILLS_DIR = SERVER_DIR / "skills"


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Env на временные каталоги + сброс кэша get_settings между тестами.

    Наследственные LEARNOS_* (например REPO_ROOT прода) вычищаем: тесты строят
    свои Settings и не должны зависеть от окружения, где запущен pytest (B-011).
    """
    data_dir = tmp_path / "data"
    kb_dir = tmp_path / "kb"
    monkeypatch.setenv("LEARNOS_DATA_DIR", str(data_dir))
    monkeypatch.setenv("LEARNOS_KB_DIR", str(kb_dir))
    monkeypatch.delenv("LEARNOS_REPO_ROOT", raising=False)
    monkeypatch.delenv("LEARNOS_GITHUB_TOKEN", raising=False)
    get_settings.cache_clear()
    yield {"tmp_path": tmp_path, "data_dir": data_dir, "kb_dir": kb_dir}
    get_settings.cache_clear()


@pytest.fixture
def fake_llm():
    """Провайдер LLM с очередью заготовленных ответов."""
    return FakeLLMProvider()


@pytest.fixture
def container(env, fake_llm):
    """Полный контейнер на tmp-каталогах: схема, FTS-таблицы, дерево категорий.

    llm_config указывает на отсутствующий файл: роли не настроены,
    /api/health честно показывает llm_configured=False, а resolve() работает
    через force_provider=fake_llm.
    """
    from app.modules.search.infra.fts import ensure_fts

    settings = Settings(
        data_dir=env["data_dir"],
        kb_dir=env["kb_dir"],
        skills_dir=SKILLS_DIR,
        llm_config=env["tmp_path"] / "llm-missing.yaml",
    )
    c = build_container(settings, fake_llm=fake_llm)
    with c.uow() as uow:
        engine = uow.session.get_bind()
        create_all_tables(engine)
        ensure_fts(uow.session)
    c.knowledge.ensure_categories_default()
    yield c
    engine.dispose()


@pytest.fixture
def rest_app(container, monkeypatch):
    """Настоящее приложение из create_app() с тестовым контейнером.

    app.main при первом импорте строит контейнер по умолчанию (побочный эффект
    уровня модуля); мы подменяем _CONTAINER до вызова create_app, поэтому
    роуты, health и обработчик ошибок работают с тестовым контейнером.

    MCP-менеджеры сессий выкидываем: Starlette TestClient выполняет startup и
    shutdown lifespan в разных задачах anyio, а StreamableHTTPSessionManager
    не позволяет покидать свой cancel-scope из чужой задачи (в uvicorn lifespan
    живёт в одной задаче, прод не затронут). REST-тесты до /mcp не доходят.
    """
    import app.main as main_mod

    monkeypatch.setattr(main_mod, "_CONTAINER", container)
    app = main_mod.create_app()
    app.state.mcp_servers = {}
    return app


@pytest.fixture
def client(rest_app):
    """REST-клиент с полным lifespan (миграции/FTS/категории/воркер)."""
    from fastapi.testclient import TestClient

    with TestClient(rest_app) as tc:
        yield tc


@pytest.fixture
def token_client(container, monkeypatch):
    """Приложение с включённым LEARNOS_API_TOKEN (R-07)."""
    from fastapi.testclient import TestClient

    container.settings.api_token = "secret-token-123"
    import app.main as main_mod

    monkeypatch.setattr(main_mod, "_CONTAINER", container)
    app = main_mod.create_app()
    app.state.mcp_servers = {}
    with TestClient(app) as tc:
        yield tc
