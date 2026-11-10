---
id: T-056
title: Роли LLM на лёгкую модель + статус цепочки ключей (BB-003/004/005)
status: active
priority: high
from: Бах-бах группа B (BB-003, BB-004, BB-005) / task_ai/bah-bah-report.md
created: 2026-11-10
---

## Что нужно

Бах-бах-исправление, группа B — три записи из `task_ai/bah-bah-report.md`:

**BB-003 — модели по ролям + thinking-контроль + провайдер-независимость** (без этапа 10-B):

1. `server/config/llm.yaml`: `fast` и `structured` → `glm-5.3-flash` (быстрая/дешёвая), `chat`
   остаётся `glm-5.3` (думающая — диалог обучения, разбор, фейнман), `vision` — `glm-4.6v`.
2. Per-role `params` в llm.yaml (например `thinking: disabled`, `max_tokens`, `temperature`),
   прокинутые через RoleBinding → провайдер → wire-запрос. Параметр уходит в запрос ТОЛЬКО
   если явно задан в конфиге; bad_request на него не должен зацикливать ретраи
   (после первой bad_request параметр дропается и больше не шлётся) — тесты обязательны.
3. Сначала живой smoke: принимает ли z.ai coding endpoint модель `glm-5.3-flash`
   и параметр `thinking`; конфигурируй по факту (механизм оставить даже если thinking не зашёл в конфиг).
4. Провайдер-независимость: закомментированные пресеты-примеры (OpenRouter, OpenAI, DeepSeek)
   в llm.yaml; z.ai-специфика только внутри адаптера openai_compat.
5. Полный этап 10-B НЕ делать — вместо него постановка новой задачи (T-057).

**BB-004 — панель LLM в настройках:**

1. `OpenAICompatProvider`: метод статуса цепочки ключей (сколько, sticky-индекс,
   cooldown-карта). Значения ключей не выдавать нигде.
2. `ModelRouter.status()` расширить, но `/api/health` открыт без токена — детализацию
   туда не выкладывать; отдельный эндпоинт под bearer, `GET /api/llm/status`:
   роли → провайдер/модель/params, по провайдеру — ключи (номер, статус, cooldown),
   configured-причины.
3. Веб: Настройки → блок «LLM» рядом с «Прокси и поиск»: карточки ролей, цепочка ключей
   с индикаторами и обратным отсчётом cooldown (кнопка обновления или раз в 30 с).
   `npm run gen:api`, дизайн — только семантические токены web/DESIGN.md.
4. `cd web && npm run lint && npx tsc --noEmit && npm run build` зелёные.

**BB-005 — тул агенту llm_status:**

1. Новый инструмент `llm_status` в ToolRegistry (read-only, виден root-агенту, как
   search_providers): роли → модели/провайдер, состояние цепочки ключей (номера, sticky,
   cooldown — без значений).
2. Сброс cooldown: параметр тула `reset_cooldown: true` — очистить карту cooldown
   провайдера (безопасно), чтобы агент мог «переключить ключ» и продолжить.
3. Тесты: статус-структура, сброс, регистрация тула.

## Ограничения

- `server/app/modules/research/` не трогать (группа A закрыта T-055).
- Существующее поведение LLM не сломать: ретраи, ротация ключей, стриминг — тесты на месте.
- Секреты только env/sec, значения не печатать.

## Критерии готовности

- [x] smoke z.ai: факт по glm-5.3-flash и thinking зафиксирован в «Заметках»
- [x] fast/structured на flash-модели, chat на думающей; params-механизм с тестами
- [x] bad_request на extra-параметр: дроп + один ретрай, без зацикливания (тест)
- [x] `GET /api/llm/status` под bearer; health без детализации
- [x] тул llm_status с reset_cooldown, виден root; тесты
- [x] блок «LLM» в настройках: роли, цепочка ключей, отсчёт cooldown
- [x] постановка T-057 (этап 10-B из UI) создана
- [x] server ruff/format/lint-imports/pytest + web lint/tsc/build зелёные
- [x] деплой, самопроверка прода

## Заметки

**Smoke z.ai (2026-11-10, живые запросы к coding endpoint):**
- `glm-5.3-flash` принимается; tool calls с ней работают (в т.ч. со стримингом);
- `thinking: {"type": "disabled"}` работает на обеих моделях: reasoning_content
  исчезает, completion_tokens на тривиальном вопросе падают 157 → 5;
- строковый `thinking: "disabled"` провайдер НЕ принимает (400, JSON parse error) —
  шорткат из llm.yaml нормализуем в адаптере `_normalize_param`;
- поэтому конфиг: fast/structured = glm-5.3-flash + thinking disabled, chat = glm-5.3
  (думает), vision без изменений.

**Решения:**
- `resolve()` стал возвращать тройку (provider, model, params) — 4 точки вызова
  обновлены (runtime x2, chat/_make_title, cli). Явные поля запроса (temperature/
  max_tokens) приоритетнее params роли; служебные ключи wire не пробрасываются.
- bad_request на extra-параметр: дроп всех extra этого запроса + один немедленный
  ретрай; параметр закрепляется в `_unsupported_extra` провайдера до рестарта.
  Максимум вызовов на запрос: `_ATTEMPTS + 1` (2+1) — зацикливания нет.
- health не раздуваем: `ModelRouter.status()` получил только `params` в roles,
  наружу `/api/health` отдаёт прежний набор полей; детализация (цепочки ключей,
  cooldown, причины) — `detailed_status()` → `GET /api/llm/status` под bearer.
- Тул `llm_status` зарегистрирован из ядра (bootstrap, module="llm") — LLM-слой
  не модуль; в `/mcp` общий, узкого `/mcp/llm` нет (список main.py не меняли);
  контракту реестра добавлен модуль "llm".
- Веб: секция «Модели» (health-строка) заменена блоком «LLM» рядом с «Прокси и
  поиск» — дубль убран; мёртвый тип `Health` из types.ts удалён.
- Фикстура `token_client` перенесена из test_auth_token.py в conftest (переиспользование).

**Сделано:** сервер + тесты (443), веб (lint/tsc/build зелёные), gen:api (74 пути).

## Результат

Коммиты `33e6b6c` (сервер: роли/params/статус/тул) и `dba474b` (веб: панель LLM).
Проверки: ruff/format/lint-imports чистые, pytest 450 passed (было 436),
web lint/tsc/build зелёные. Прод CT 132: деплой дошёл (health ok, tools 78,
modules 16), `GET /api/llm/status` — 401 без токена / 200 с bearer и через
веб-прокси `:3000` (роли с flash-моделями, 4 ключа, значений нет), блок «LLM»
рендерится на /settings; живой smoke-llm (chat, glm-5.3): complete/stream/tool call.
Постановка T-057 (полный этап 10-B из UI) — в tasks/.
