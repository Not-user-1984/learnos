"""Composition root: контейнер зависимостей и список модулей."""

import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import sessionmaker

from .agent.registry import AgentRegistry
from .agent.runtime import AgentRuntime
from .kernel.clock import SystemClock
from .kernel.config import Settings, get_settings
from .kernel.db import UnitOfWorkFactory, make_engine, metadata
from .kernel.events import EventBus
from .kernel.ids import UuidHexGenerator
from .kernel.logging import setup_logging
from .kernel.tools.registry import ToolRegistry
from .llm.router import LLMConfig, ModelRouter
from .modules.chat import ChatModule
from .modules.courses import CoursesModule
from .modules.export import ExportModule
from .modules.knowledge import KnowledgeModule
from .modules.learning import LearningModule
from .modules.library import LibraryModule
from .modules.mcpext import McpExtModule
from .modules.messenger import MessengerModule
from .modules.profile import ProfileModule
from .modules.research import ResearchModule
from .modules.review import ReviewModule
from .modules.revision import RevisionModule
from .modules.search import SearchModule
from .modules.skills import SkillsModule
from .modules.tuning import TuningModule

log = logging.getLogger("learnos.bootstrap")

# порядок = порядок зависимостей (profile → research → skills → knowledge → learning → chat → …)
MODULES = [
    ProfileModule(),
    ResearchModule(),
    SkillsModule(),
    KnowledgeModule(),
    LibraryModule(),
    LearningModule(),
    ChatModule(),
    CoursesModule(),
    SearchModule(),
    ExportModule(),
    ReviewModule(),
    MessengerModule(),
    TuningModule(),
    McpExtModule(),
    RevisionModule(),
]


@dataclass
class Container:
    """Типизированный реестр сервисов; без DI-фреймворков."""

    settings: Settings
    uow: UnitOfWorkFactory
    bus: EventBus
    tools: ToolRegistry
    agent_registry: AgentRegistry
    llm_router: ModelRouter
    agent_runtime: AgentRuntime
    run_recorder: object | None = None  # трейсы agent_runs: старт-хук и состояние запусков
    ids: UuidHexGenerator = field(default_factory=UuidHexGenerator)
    clock: SystemClock = field(default_factory=SystemClock)
    # сервисы модулей (заполняются в wire):
    profile: object | None = None
    research: object | None = None
    skills: object | None = None
    skills_service: object | None = None
    knowledge: object | None = None
    library: object | None = None
    job_worker: object | None = None
    learning: object | None = None
    chat: object | None = None
    courses: object | None = None
    search: object | None = None
    export: object | None = None
    review: object | None = None
    messenger: object | None = None
    tuning: object | None = None
    mcpext: object | None = None
    revision: object | None = None


def build_container(settings: Settings | None = None, *, fake_llm=None) -> Container:
    """Собрать приложение: движок, реестры, модули. В тестах — свои настройки и FakeLLM."""
    settings = settings or get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.kb_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(settings.log_format)

    engine = make_engine(settings.db_url, echo=settings.db_echo)
    session_factory = sessionmaker(bind=engine, future=True)
    bus = EventBus()
    uow = UnitOfWorkFactory(session_factory, bus, publisher="app")

    llm_config = LLMConfig.load(settings.llm_config)
    router = (
        ModelRouter(llm_config, force_provider=fake_llm)
        if fake_llm
        else ModelRouter(llm_config, key_cooldown_seconds=settings.llm_key_cooldown)
    )

    container = Container(
        settings=settings,
        uow=uow,
        bus=bus,
        tools=ToolRegistry(max_result_chars=settings.tool_result_max_chars),
        agent_registry=AgentRegistry(),
        llm_router=router,
        agent_runtime=None,  # заменяется ниже (нужен реестр инструментов)
    )
    from .agent.recorder import DbRunRecorder

    recorder = DbRunRecorder(uow)
    container.run_recorder = recorder
    container.agent_runtime = AgentRuntime(router, container.tools, recorder, container.agent_registry)

    for module in MODULES:
        module.wire(container)
    for module in MODULES:
        for spec in module.tools(container):
            container.tools.register(spec)
    for module in MODULES:
        module.subscribe(bus, container)

    # связки, которые нельзя сделать в wire (циклические зависимости сервисов)
    if container.library is not None and container.knowledge is not None:
        container.library.bind(container.knowledge)
    if container.library is not None:
        container.library.bind_runtime(container.learning, container.chat)
    if container.knowledge is not None and container.courses is not None:
        container.knowledge.bind_courses(container.courses)
    if container.learning is not None and container.chat is not None:
        container.learning.bind_chat(container.chat)
    log.info("container готов: модулей=%d, инструментов=%d", len(MODULES), len(container.tools.all()))
    return container


def create_all_tables(engine) -> None:
    """Создать все таблицы из метаданных (для тестов и дев-старта)."""
    metadata.create_all(engine)
