# 05 — LLM-слой, агентный рантайм, агенты LearnOS

Три уровня, каждый не знает о вышележащих:

1. **`app/llm/`** — «поговорить с любой моделью»: единые типы, протокол провайдера, адаптеры, маршрутизация по ролям.
2. **`app/agent/`** — «агент = модель + промпт + инструменты + цикл»: декларативный `AgentSpec`, `AgentRuntime`, события, трейсинг. Под будущую мультиагентность.
3. **Агенты модулей** (`modules/<m>/agents/`) — конкретные агенты LearnOS: тьюторы чата, writer блоков, summarizer глав и т.д.

---

## 1. LLM-слой (`app/llm/`)

### Принцип

Бизнес-код никогда не знает имени провайдера и модели. Он просит **роль** (`chat`, `fast`, `structured`, `vision`), а `ModelRouter` по конфигу выдаёт провайдера и модель. Сменить GLM на другую модель — правка `llm.yaml`, без кода.

### Типы (`llm/types.py`)

```python
@dataclass(frozen=True, slots=True)
class Message:
    """Сообщение диалога в нейтральном формате (не привязано к API провайдера)."""
    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None
    name: str | None = None

@dataclass(frozen=True, slots=True)
class ToolCall:
    """Вызов инструмента, запрошенный моделью."""
    id: str
    name: str
    arguments: dict[str, Any]

@dataclass(frozen=True, slots=True)
class ToolSchema:
    """Описание инструмента для модели: имя, описание, JSON Schema аргументов."""
    name: str
    description: str
    parameters: dict[str, Any]

@dataclass(frozen=True, slots=True)
class LLMRequest:
    """Запрос к модели; провайдер переводит его в свой формат."""
    messages: tuple[Message, ...]
    tools: tuple[ToolSchema, ...] = ()
    temperature: float | None = None
    max_tokens: int | None = None
    response_schema: dict[str, Any] | None = None   # структурированный ответ (JSON Schema)

# Потоковые события провайдера:
TextDelta(text) | ToolCallReady(call: ToolCall) | Usage(input_tokens, output_tokens) | Finish(reason)

@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Итог нестримингового вызова."""
    text: str
    tool_calls: tuple[ToolCall, ...]
    usage: Usage | None
    finish_reason: str
```

### Протокол провайдера (`llm/provider.py`)

```python
class LLMProvider(Protocol):
    """Адаптер к API конкретного провайдера моделей."""

    name: str
    capabilities: ProviderCapabilities  # tools, streaming, json_schema, vision

    async def complete(self, model: str, request: LLMRequest) -> LLMResponse:
        """Один ответ целиком."""

    def stream(self, model: str, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        """Ответ потоком: текст по кускам, вызовы инструментов — целиком, когда собраны."""
```

Ошибки провайдера нормализуются в `LLMError` с кодом: `not_configured`, `auth`, `rate_limit`, `timeout`, `bad_request`, `unavailable`. Ретраи (2 попытки, экспоненциальная пауза) — только для `rate_limit`/`timeout`/`unavailable`, внутри адаптера.

Если провайдер не поддерживает `json_schema`, адаптер добавляет схему в системное сообщение и валидирует ответ сам (см. `structured_output` ниже).

### Адаптеры (`llm/providers/`)

| Адаптер | Покрывает | Этап |
|---|---|---|
| `openai_compat.py` | z.ai GLM, OpenAI, OpenRouter, DeepSeek, Groq, Ollama, LM Studio, vLLM — всё с OpenAI-совместимым `/chat/completions` | 1 |
| `fake.py` | тесты: сценарий ответов и tool calls, запись запросов | 1 |
| `anthropic.py` | Claude (свой формат tools) | бэклог — при необходимости |

Новый провайдер = новый файл, реализующий `LLMProvider`, + регистрация типа в фабрике `llm/factory.py`. LiteLLM не используем: свой тонкий протокол проще тестировать и не тянет сотню зависимостей; при желании LiteLLM можно подключить как ещё один адаптер.

### Конфиг (`server/config/llm.yaml`, без секретов)

```yaml
providers:
  zai:
    type: openai_compat
    base_url: https://api.z.ai/api/coding/paas/v4
    api_key_env: ZAI_API_KEY
    capabilities: {tools: true, streaming: true, json_schema: false, vision: false}
  ollama:                       # пример локальной модели, выключен
    type: openai_compat
    base_url: http://localhost:11434/v1
    api_key_env: null
    enabled: false

roles:
  chat:       {provider: zai, model: glm-5.3}            # чат, сессии
  structured: {provider: zai, model: glm-5.3}            # генерация блоков, планов (JSON)
  fast:       {provider: zai, model: glm-5.3-highspeed}  # summary глав, заголовки, категоризация
  vision:     {provider: zai, model: glm-4.6v}           # на будущее
```

`ModelRouter.resolve(role) -> (LLMProvider, model)`. Переопределение роли для конкретного агента — поле `model_role` в `AgentSpec`; переопределение модели на лету — `AgentSpec.model_override` (для экспериментов). В Настройках UI показывает роли и модели (только чтение в v1) и кнопку «Проверить соединение».

### Структурированный вывод (`llm/structured.py`)

`structured_output(router, role, messages, model: type[BaseModel]) -> BaseModel` — просит JSON по схеме pydantic-модели, валидирует, при ошибке делает до 2 повторов с текстом ошибки валидации. Используется writer'ом блоков, summarizer'ом, планировщиком курсов.

---

## 2. Агентный рантайм (`app/agent/`)

### AgentSpec — декларативное описание агента

```python
@dataclass(frozen=True, slots=True)
class AgentSpec:
    """Описание агента: роль модели, системный промпт, доступные инструменты и лимиты."""
    name: str                          # session_tutor
    description: str                   # для людей и для делегирования
    model_role: str = "chat"
    prompt_path: Path                  # prompt.md рядом с агентом (Jinja-подстановки)
    tools: frozenset[str] = frozenset()  # имена инструментов из ToolRegistry
    max_steps: int = 12                # итераций «модель → инструменты»
    temperature: float | None = None
    output_model: type[BaseModel] | None = None  # если агент обязан вернуть структуру
```

Промпты — Markdown-файлы рядом со спеком (`modules/chat/agents/session_tutor/prompt.md`), правятся без кода. Подстановки (`{{ profile }}`, `{{ chapter_summary }}`) — Jinja2 со `StrictUndefined`.

### AgentRuntime — цикл

```python
class AgentRuntime:
    """Исполняет агента: собирает запрос, стримит ответ модели, вызывает инструменты, повторяет до финала."""

    async def run(self, spec: AgentSpec, ctx: AgentContext, history: Sequence[Message]) -> AsyncIterator[AgentEvent]:
        ...
```

Алгоритм:

1. `ContextBuilder` модуля-владельца даёт системный промпт + контекстные сообщения (профиль, глава, состояние сессии, сжатая история).
2. Запрос в провайдер через `ModelRouter` (стрим).
3. `TextDelta` → событие `text`; `ToolCallReady` → проверка, что инструмент есть в `spec.tools` → вызов через `ToolRegistry` с `ToolContext(channel="agent", …)` → события `tool_start` / `tool_end` (+ `card`, если инструмент вернул `_card`).
4. Результаты инструментов добавляются в историю, шаг повторяется, пока модель не ответит без вызовов или не исчерпан `max_steps` (тогда событие `error: max_steps`).
5. Отмена: `CancellationToken` (кнопка «Стоп» в UI) — прерывает стрим и не начинает новых вызовов.
6. Трейсинг: в конце — запись в `agent_runs`.

События `AgentEvent`: `text`, `tool_start`, `tool_end`, `card`, `final`, `error`. Модуль `chat` маппит их в SSE-события из [04-api-and-mcp.md](04-api-and-mcp.md); рантайм про SSE не знает.

### Задел под мультиагентность

Делаем сейчас (дёшево и не мешает):

- `AgentRegistry` — все `AgentSpec` приложения по имени (модули регистрируют своих агентов в `Module.wire`).
- `run_structured(spec, input) -> output_model` — запуск агента как функции (без чата). Так `learning` вызывает `block_writer`, `library` — `chapter_summarizer`.
- `AgentContext` несёт `parent_run_id` — трейсы вложенных запусков связаны.

Позже (бэклог, без переделки рантайма):

- **Агент как инструмент:** `as_tool(spec)` превращает агента в `ToolSpec` (`delegate_<name>`), и тьютор может поручить подзадачу (ресерч источников, разбор практики) другому агенту.
- **Оркестратор:** агент-планировщик, который строит курс, раздавая шаги специализированным агентам.
- Подключение внешних MCP-серверов как источников инструментов для агентов (клиентский MCP-адаптер → `ToolSpec`).

---

## 3. Агенты LearnOS

| Агент | Модуль | Роль модели | Инструменты | Выход |
|---|---|---|---|---|
| `free_chat` | chat | chat | search, get_block, list_blocks, update_block, save_note, list_sources, get_source, read_chapter, get_profile, research_sources | текст |
| `quick_reviewer` | chat | chat | get_source, list_chapters, read_chapter, search, save_note, update_block, get_profile | текст + конспект |
| `session_tutor` | chat | chat | get_session_state, advance, read_chapter, list_chapters, practice_step, finish_session, search, get_block, get_profile | текст + карточки + урок |
| `block_writer` | knowledge | structured | — | `BlockDraft` |
| `categorizer` | knowledge | fast | — (дерево категорий передаётся в контекст) | `{path, new_category?: {path,title}}` |
| `chapter_summarizer` | library | fast | — | `{summary, key_points[], has_exercises}` |
| `course_planner` | courses | structured | list_sources, get_source, list_blocks, research_sources | `CoursePlan` (этап 5) |
| `title_maker` | chat | fast | — | заголовок разговора ≤ 60 символов |

### Контекст тьюторов (собирает `chat`)

Порядок сообщений в запросе:

1. Системный промпт агента (`prompt.md`).
2. Системный блок «Контекст»: профиль (машины + learning, компактно), источник (название, обзор, оглавление: номер + заголовок + 1 строка summary), текущая глава (summary + key_points), состояние сессии (state, allowed_events, прогресс), блок в фокусе (если «обсудить блок»).
3. `conversation.summary` — сжатие старой истории (если есть).
4. Последние сообщения разговора, пока влезают в бюджет (по умолчанию ~24k токенов; оценка `len(text) / 3.5`).

Когда история превышает бюджет — `title_maker`-подобный быстрый вызов роли `fast` сжимает старую половину в `conversation.summary`.

### Режим `quick` — быстрый разбор (`quick_reviewer`)

Суть промпта:

- Начни с `get_source`; работай по summary глав; полный текст главы читай `read_chapter` только когда нужна конкретика.
- Отвечай: «Главное за 30 секунд» (3–5 пунктов) → ключевые понятия (термин — определение) → что из этого применимо Дмитрию (с учётом профиля) → 1–2 вопроса «на подумать».
- «Пошли по учебнику» = иди по главам с курсора активности, по одной; после каждой предложи: дальше / подробнее / сессия по этой главе.
- Когда пользователь говорит «сохрани»/«в базу» или разбор главы закончен и пользователь подтвердил — вызови `save_note` (сервер сгенерирует конспект через `block_writer`, kind `note`).

### Режим `session` — урок (`session_tutor`)

Стейт-машина (уже есть в `core.py`, переносится в `learning/domain.py` без изменения переходов):

```
theory --theory_done--> check --next_block--> theory
                        check --go_practice--> practice --practice_done--> debrief --finish_session--> done
лог-события в любом состоянии: ask, answer, note, practice_log
```

Конфиг сессии (`config_json`, дефолты из профиля): `theory_concepts` (5, можно до 10), `questions_per_concept` (1), `practice` (true), `minutes` (30). Пользователь может менять их в начале сессии («давай 10 понятий без практики»).

Поведение тьютора (суть промпта):

1. **Теория.** Объясняй понятия по одному: определение → аналогия (стиль из профиля) → пример → при необходимости mermaid. Опирайся на текст главы (`read_chapter`), не выдумывай то, чего нет в источнике, — если дополняешь от себя, помечай «вне книги». После порции понятий — `advance(theory_done)`.
2. **Проверка (фейнман).** По одному вопросу за раз (`advance(ask)` → карточка `question`), жди ответ. Ответ пользователя логируй `advance(answer)`. Оцени: `understood | partial | missed`, коротко поправь, слабое место — в `note` с `weak_spot` (карточка `evaluation`). Не задавай следующий вопрос, пока не получен ответ на текущий.
3. **Практика.** Если в главе есть упражнения (`has_exercises`) — адаптируй их. Иначе придумай практику под профиль (какую машину использовать и почему). Каждый шаг — `practice_step` (карточка `command`): команда, разбор каждой части, ожидаемый результат, риск. Ждёшь вывод от пользователя, объясняешь его. `risk: high` (удаление, изменения хоста) — явное предупреждение и безопасная альтернатива (dry-run, отдельный namespace, снапшот). Нет смысла в практике (тема без рук) — короткое упражнение «объясни на своём примере». Затем `practice_done`.
4. **Разбор.** Итог в 5 строк: что понял хорошо, что дозакрепить. Затем `finish_session` без `block_json` — блок соберёт `block_writer`. Сообщи, что блок сохранён, и предложи категорию (карточка `block_saved`).
5. Таймбокс: следи за `minutes`; если время вышло — предложи сократить практику.

### Режим `free` — свободный чат (`free_chat`)

- Отвечает на вопросы, ищет по базе знаний (`search`) и опирается на найденные блоки, указывая их.
- Правка блоков: если пользователь просит улучшить/дополнить блок («добавь в омлет, что соль в конце») — найди блок, вызови `update_block` с `reason`. Правка применяется сразу (карточка `block_updated` с кнопкой «Откатить»).
- По просьбе «запомни это»/«сохрани» — `save_note`.

### `block_writer` — генерация блока

Вход: транскрипт сессии или сообщения разговора (без tool-шума), источники, профиль, режим (`lesson|note`), список существующих блоков категории (uid + title) для связей.

Выход — `BlockDraft` (pydantic, валидация строгая):

```python
class Concept(BaseModel):
    term: str = Field(max_length=80)
    definition: str = Field(max_length=300)

class PracticeStep(BaseModel):
    machine: str
    command: str
    explanation: str
    result: str | None = None

class BlockDraft(BaseModel):
    """Черновик блока знаний, из которого собирается MD-файл."""
    title: str = Field(max_length=100)
    summary: str = Field(max_length=280)
    concepts: list[Concept] = Field(default_factory=list, max_length=12)
    theses: list[str] = Field(min_length=1, max_length=7)
    my_examples: list[str] = Field(default_factory=list)   # формулировки пользователя из его ответов
    mermaid: str | None = None
    practice: list[PracticeStep] = Field(default_factory=list)
    weak_spots: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)  # для note: «вопросы на потом»
    links: list[str] = Field(default_factory=list)          # block_uid существующих блоков
    tags: list[str] = Field(default_factory=list, max_length=8)
    category_suggestion: str | None = None
```

Правила промпта: «Как я это понял» — из реальных ответов пользователя (перефраз, не выдумка); `weak_spots` — из оценок `partial|missed`; mermaid — только если схема помогает (`graph`, `sequenceDiagram`, `classDiagram`, `flowchart`), ≤ 15 узлов, подписи без спецсимволов, ломающих синтаксис; `links` — только из переданного списка.

После генерации: `categorizer` подбирает категорию из `kb/categories.yaml` (или предлагает новый узел) → `knowledge.save_block(draft, category_status="suggested")`.

### `chapter_summarizer`

Запускается job'ом после обработки источника, по главе за вызов: первые ~12k символов главы → `{summary (3–5 предложений), key_points (3–7), has_exercises}`. После всех глав — обзор источника (`sources.summary`) из summary глав. Прогресс → `jobs.progress`.

### Профиль в практике

В контекст тьютора передаётся список машин: `id`, `name`, `kind`, `specs`, `tools`, `notes`. Тьютор обязан выбрать машину для каждого шага (`practice_step.machine` — `id` из профиля) и учитывать заметки (например, «хомлаб спит 19:00–08:30» → вечером предложить мак).
