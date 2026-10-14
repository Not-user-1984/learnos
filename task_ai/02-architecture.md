# 02 — Архитектура

Цель — **модульный монолит со слоистой архитектурой**, готовый к росту до прод-версии: модули добавляются без правки соседей, каждый модуль сам публикует свои REST-роуты и MCP-инструменты, LLM-провайдер и агенты подключаемые, всё покрывается тестами без сети.

## Текущее состояние (на 2026-10-13)

| Часть | Есть | Проблема |
|---|---|---|
| `server/app/core.py` | курсы, источники, главы, сессии (стейт-машина), блоки | один файл на всё; SQL, файлы и правила вперемешку; всё привязано к `course_id` |
| `server/app/mcp_server.py` | 17 MCP-инструментов + авто-регистрация скиллов | инструменты описаны вручную, веб-чату не переиспользовать |
| `server/app/api.py` | REST поверх `core` | нет чата, загрузки файлов, категорий, фильтров |
| `server/app/kb.py` | запись блока в `kb/*.md` | frontmatter склеивается строками, нет категорий/версий/обратного чтения |
| `server/skills/` | `book-splitter`, `youtube-to-summary`, `web-search` | ок, оставить формат |
| LLM | — | нет клиента |
| Поиск | подстрока по файлам глав | медленно, нет поиска по блокам |
| Тесты | — | нет |
| `web/` | Next.js 16, React 19, Tailwind v4, react-markdown, mermaid | нет навигации, чата, библиотеки, категорий, дизайн-системы |

Переписываем `server/app/` в новую структуру (этап 1). Внешние контракты (MCP-имена, REST-роуты) сохраняются — см. [04-api-and-mcp.md](04-api-and-mcp.md).

## Общая картина

```
 opencode ─── MCP /mcp, /mcp/<module> ─┐
 web (Next) ─ REST /api/*, SSE ────────┤
                                       ▼
 ┌──────────────── presentation: api.py (роуты) · tools.py (инструменты) ────────────────┐
 │                         ToolRegistry ──▶ MCP-адаптер / LLM-адаптер                    │
 ├──────────────── application: service.py (use-cases, транзакции, события) ─────────────┤
 ├──────────────── domain: domain.py (сущности, правила, стейт-машина) — чистый Python ───┤
 └──────────────── infrastructure: infra/* (SQLAlchemy, MD-файлы, скиллы, провайдеры LLM)┘
        модули: library · knowledge · learning · chat · courses · profile · search · export · skills
 сквозные слои (не зависят от модулей): kernel · llm · agent
```

## Слои и правило зависимостей

| Слой | Где | Что делает | Может импортировать |
|---|---|---|---|
| **domain** | `modules/<m>/domain.py` | сущности (dataclass), value objects, правила, ошибки домена; стейт-машина сессии | только stdlib и `kernel.errors` |
| **ports** | `modules/<m>/ports.py` | интерфейсы (`typing.Protocol`) того, что нужно сервису от внешнего мира: репозитории, файловое хранилище | domain |
| **application** | `modules/<m>/service.py` | use-cases: «завершить сессию», «сохранить блок»; транзакция (UnitOfWork), публикация событий, вызов агентов | domain, ports, `kernel`, `llm`, `agent`, **публичные** сервисы других модулей |
| **infrastructure** | `modules/<m>/infra/` | реализация портов: SQLAlchemy-репозитории, MD-хранилище, вызов скиллов | ports, domain, kernel |
| **presentation** | `modules/<m>/api.py`, `tools.py`, `schemas.py` | FastAPI-роуты и инструменты реестра; pydantic DTO; маппинг ошибок | application, schemas |

Правило: зависимости направлены только вниз (presentation → application → domain). Инфраструктура реализует порты, а связывает всё composition root (`bootstrap.py`). Правило проверяется автоматически через `import-linter` (контракты в `pyproject.toml`) — нарушение валит `make check`.

## Структура сервера

```
server/
├── pyproject.toml            # зависимости, ruff, mypy, pytest, import-linter
├── alembic.ini
├── config/
│   └── llm.yaml              # провайдеры и роли моделей (без секретов) — см. 05
├── migrations/               # Alembic
├── skills/                   # drop-in скиллы (формат не меняется)
├── app/
│   ├── main.py               # create_app(): FastAPI + монтирование MCP
│   ├── bootstrap.py          # composition root: Container, список модулей
│   ├── cli.py                # migrate | reindex | smoke-llm
│   ├── kernel/               # общее ядро без бизнес-логики
│   │   ├── config.py         # Settings (pydantic-settings), единственное место чтения env
│   │   ├── db.py             # engine, session factory, UnitOfWork
│   │   ├── errors.py         # AppError → NotFound, Conflict, InvalidState, ValidationFailed, ExternalServiceError
│   │   ├── events.py         # EventBus (in-process), базовый DomainEvent
│   │   ├── ids.py            # IdGenerator (порт + реализация): uid с префиксами
│   │   ├── clock.py          # Clock (порт + реализация)
│   │   ├── logging.py        # структурные логи (JSON в проде, текст локально)
│   │   ├── module.py         # базовый класс Module
│   │   └── tools/
│   │       ├── spec.py       # ToolSpec, ToolContext, ToolResult
│   │       ├── registry.py   # ToolRegistry
│   │       ├── mcp_adapter.py  # реестр → MCP (общий /mcp и /mcp/<module>)
│   │       └── llm_adapter.py  # реестр → описания инструментов для LLM
│   ├── llm/                  # слой моделей (см. 05): типы, LLMProvider, провайдеры, ModelRouter
│   ├── agent/                # агентный рантайм (см. 05): AgentSpec, AgentRuntime, трейсинг
│   └── modules/
│       ├── library/          # источники, главы, обработка (jobs), агент chapter_summarizer
│       ├── knowledge/        # блоки, категории, версии, MD-хранилище, агенты block_writer, categorizer
│       ├── learning/         # активности, сессии (стейт-машина), практика
│       ├── chat/             # разговоры, сообщения, SSE, агенты-тьюторы (free/quick/session)
│       ├── courses/          # курсы, элементы, прогресс, агент course_planner
│       ├── profile/          # профиль: машины, предпочтения
│       ├── search/           # FTS5 (позже sqlite-vec); обновляется по событиям
│       ├── export/           # MD/ZIP
│       └── skills/           # загрузка server/skills/* в реестр инструментов
└── tests/
    ├── unit/                 # domain + service с фейковыми портами
    ├── integration/          # репозитории на tmp SQLite, MD-хранилище на tmp_path
    ├── api/                  # httpx/TestClient по REST и SSE
    └── contract/             # схемы MCP-инструментов, снапшоты OpenAPI
```

### Устройство модуля

```
modules/knowledge/
├── __init__.py       # KnowledgeModule + публичный экспорт: KnowledgeService, DTO
├── domain.py         # Block, BlockDraft, Category, BlockKind, правила версии
├── ports.py          # BlockRepository, BlockFileStore, CategoryStore (Protocol)
├── service.py        # KnowledgeService: save_block, update_block, restore, set_category …
├── events.py         # BlockSaved, BlockUpdated, CategoryConfirmed
├── schemas.py        # pydantic DTO для REST и инструментов
├── api.py            # APIRouter — тонкие обработчики
├── tools.py          # ToolSpec-и модуля (MCP + агент)
├── agents/           # AgentSpec-и модуля + prompt.md (block_writer, categorizer)
└── infra/
    ├── tables.py     # SQLAlchemy-таблицы модуля
    ├── sql_repo.py   # реализация BlockRepository
    └── md_store.py   # чтение/запись kb/blocks/*.md, kb/categories.yaml
```

Маленький модуль (profile, export) может не иметь `ports.py`/`infra/` — заводи слой, когда он появляется, а не заранее.

### Контракт модуля

```python
class Module(ABC):
    """Модуль приложения: сам связывает свои зависимости и публикует роуты, инструменты и подписки."""

    name: str

    @abstractmethod
    def wire(self, c: Container) -> None:
        """Создаёт сервисы модуля и кладёт их в контейнер."""

    def routers(self, c: Container) -> list[APIRouter]:
        """REST-роуты модуля (монтируются под /api)."""
        return []

    def tools(self, c: Container) -> list[ToolSpec]:
        """Инструменты модуля для MCP и встроенных агентов."""
        return []

    def subscribe(self, bus: EventBus, c: Container) -> None:
        """Подписки на доменные события других модулей."""
```

`bootstrap.py` держит список `MODULES = [ProfileModule(), LibraryModule(), KnowledgeModule(), …]`: вызывает `wire` в порядке зависимостей, затем собирает роуты, инструменты и подписки. **Новый модуль = новая папка + одна строка в списке.**

`Container` — простой типизированный dataclass/реестр сервисов, без DI-фреймворков. В тестах собирается с фейками (`FakeLLMProvider`, in-memory репозитории, `FixedClock`).

### Связи между модулями

```
profile ◀── learning ◀── chat
library ◀── learning      │
knowledge ◀── learning ◀──┘
courses ──▶ library, knowledge, learning (только чтение прогресса)
search  ◀── события BlockSaved/BlockUpdated/SourceProcessed
export  ──▶ knowledge, library, courses
```

- Модуль вызывает другой модуль **только через его публичный сервис** из `modules/<m>/__init__.py`. Таблицы, репозитории и `infra` чужого модуля не импортируются (контракт import-linter).
- Циклы запрещены. Если модулю нужна реакция на чужое действие — **доменное событие** через `EventBus` (публикуется после коммита транзакции). Пример: `knowledge` публикует `BlockSaved` → `search` переиндексирует, `courses` пересчитает прогресс.

### Инструменты и MCP по модулям

- Каждый модуль объявляет свои инструменты в `tools.py` (`ToolSpec`: имя, описание, pydantic-модель аргументов, обработчик, `channels`, `modes`, `module`).
- `ToolRegistry` собирает все инструменты. Из него строятся:
  - общий MCP-сервер `/mcp` — все инструменты (для opencode, как сейчас);
  - узкие MCP-серверы `/mcp/<module>` (например `/mcp/knowledge` — только база знаний), чтобы подключать к внешним клиентам ровно нужную часть;
  - описания инструментов для встроенных агентов (фильтр по `modes` и списку в `AgentSpec`).
- Обработчик получает `ToolContext` (канал `mcp|agent`, `conversation_uid`, `session_uid`, `agent_name`) — так `save_note` из веб-чата сам знает, из какого разговора он вызван.
- Обработчик инструмента — 3–10 строк: распарсить аргументы → вызвать сервис → вернуть DTO. Ошибки `AppError` адаптер превращает в `{"error": code, "message": …}`.

## Хранение данных

| Данные | Источник истины | Где | В git |
|---|---|---|---|
| Блоки знаний | **MD-файл** | `kb/blocks/<uid>_<slug>.md` | да |
| Дерево категорий | **YAML-файл** | `kb/categories.yaml` | да |
| Индекс блоков, теги, связи, FTS | SQLite (пересобирается `reindex` из `kb/`) | `data/learnos.db` | нет |
| Версии блоков | SQLite `block_versions` | `data/learnos.db` | нет |
| Источники, главы, активности, курсы, разговоры, сессии, профиль, jobs, agent_runs | SQLite | `data/learnos.db` | нет |
| Файлы книг, тексты глав, транскрипты | диск | `data/sources/<uid>/…` | нет |

- **Доступ к БД:** SQLAlchemy 2.0 (Core-таблицы в `infra/tables.py` каждого модуля, общий `MetaData` в `kernel/db.py`), синхронные сессии. Async-код (агент, SSE) вызывает сервисы через `anyio.to_thread.run_sync`. Миграции — Alembic.
- **UnitOfWork:** один use-case = одна транзакция; события копятся в UoW и публикуются после успешного коммита.
- **Запись блока:** сначала MD-файл (атомарно: временный файл + `os.replace`), затем индекс в той же операции сервиса. Если индекс упал — файл остаётся, `reindex` восстановит.
- **`reindex`** (`uv run python -m app.cli reindex` и `POST /api/kb/reindex`) читает `kb/` и пересобирает индекс знаний. Ручная правка MD в редакторе → reindex → видна в UI.
- Frontmatter — только через `yaml.safe_dump(allow_unicode=True, sort_keys=False)` / `yaml.safe_load`.

## Фоновые задачи

`library` ставит `jobs` (обработка PDF/видео, summary глав). Воркер — `asyncio`-задача в lifespan приложения, читает очередь из таблицы `jobs`, одна задача за раз (локальный сервис). Интерфейс `JobQueue` (порт) позволит позже заменить на внешнюю очередь без правки модулей.

## Конфигурация

Все настройки — `kernel/config.py` (`pydantic-settings`, префикс `LEARNOS_`). `os.environ` в других местах не читается.

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `LEARNOS_DATA_DIR` | `<repo>/data` | БД, книги, главы (тесты — tmp) |
| `LEARNOS_KB_DIR` | `<repo>/kb` | база знаний (тесты — tmp) |
| `LEARNOS_LLM_CONFIG` | `server/config/llm.yaml` | провайдеры и роли моделей |
| `LEARNOS_LOG_FORMAT` | `text` | `text` / `json` |
| `LEARNOS_TOOL_RESULT_MAX_CHARS` | `8000` | обрезка результатов инструментов для LLM |
| `ZAI_API_KEY` и др. ключи | — (из `sec`) | имена переменных задаются в `llm.yaml` (`api_key_env`) |

Запуск сервера с ключом:

```bash
cd server && sec exec ZAI_API_KEY -- uv run uvicorn app.main:app --port 8765 --reload
```

Без ключа сервер стартует; LLM-функции отвечают ошибкой `llm_not_configured`, UI показывает баннер.

## Наблюдаемость

- Логи структурные (`logging` + JSON-форматтер в проде): `module`, `use_case`, `conversation_uid`, `duration_ms`. Секреты и полные тексты книг в логи не пишутся.
- Каждый запуск агента пишется в `agent_runs` (агент, модель, провайдер, токены, шаги, длительность, ошибка) — см. [05-llm-and-agents.md](05-llm-and-agents.md).
- `GET /api/health` — состояние БД, LLM, воркера jobs.

## Зависимости (добавятся)

Сервер: `sqlalchemy>=2`, `alembic`, `pydantic-settings`, `openai` (адаптер OpenAI-совместимых провайдеров), `python-multipart`, `anyio`; dev: `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`, `mypy`, `import-linter`, `respx` (мок HTTP).
Веб: см. [06-ui.md](06-ui.md).

Правила кода и тестов — [07-code-standards.md](07-code-standards.md).
