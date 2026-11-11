# B-003 — отчёт исполнителя

## Изменённые файлы

**Сервер:**
- `server/app/modules/chat/cards.py` — новый: `DECISION_TYPES`, `build_options`, `merge_decision`, `ensure_card_ids`, класс `CardState` (resolve/mark — статус в JSON карточки сообщения)
- `server/app/modules/chat/service.py` — слияние decision-карточек в `_reply_stream` (одна группа решений на ход, SSE-событие `card` несёт `index` для замены); `card_id` присваивается при сохранении ответа; `get_conversation` отдаёт карточки с id (детерминированно `m{id}c{i}` для старых)
- `server/app/modules/chat/infra/sql_repo.py` — `MessageRepository.find_card` (по card_id, с генерацией id старым карточкам) и `update_cards`
- `server/app/modules/chat/api.py` — `POST /conversations/{uid}/cards/{card_id}/resolve` (идемпотентен; другой choice → 409)
- `server/app/modules/chat/schemas.py` — `CardResolveIn`
- `server/app/modules/chat/__init__.py` — `c.chat_cards = CardState(...)` в wire, роутер получает её
- `server/app/modules/tuning/api.py`, `tuning/__init__.py` — approve/reject принимают опциональные `conversation_uid`+`card_id`, помечают карточку `applied`/`rejected`
- `server/app/modules/revision/__init__.py` — `branch/reject` принимает `conversation_uid`+`card_id`, помечает карточку `rejected`

**Веб:**
- `web/src/components/chat/cards.tsx` → удалён; разнесён в `web/src/components/chat/cards/`: `shared.ts` (CardProps, useCardState, resolveCard, decisionOptions), `decisions.tsx` (action_offer + quick_replies одним компонентом), `command.tsx` (+`stripCommandFences`), `simple.tsx` (question/evaluation/chapter_review), `blocks.tsx` (block_saved/note_draft), `changes.tsx` (prompt_change/git_change), `index.tsx` (реестр type → компонент)
- `web/src/components/chat/next-steps.tsx` — новый: один контекстный ряд 0–3 действий; скрыт при стриме и при неотвеченных решениях; в сессии — одно действие фазы
- `web/src/lib/scenarios.ts` — новый: единые сценарии для стартового экрана и NextSteps (одна надпись = одно поведение)
- `web/src/components/chat/chat-view.tsx` — чипы (2 ряда) → NextSteps; кнопка сессии из `fixed bottom-24` → в шапку; toggle кота в ряд композера; `pb-14` ленте при видимом коте; liveCards по `index` (замена при слиянии); note_draft → «Записано → Открыть блок» по ближайшему block_saved; fenced-дубль команды гасится; buildCourse-чип удалён (сценарий «Собрать курс» = prefill, как на старте)
- `web/src/components/chat/chat-cat.tsx` — toggle вынесен в `CatToggle`, экспортирован `useCatVisible`
- `web/src/components/chat/chat-start.tsx` — сценарии из `scenarios.ts`, CatToggle в ряду сценариев
- `web/src/lib/types.ts` — Card: `card_id`, `choice`, `options`; SseEvent card: `index`
- `web/src/lib/api-schema.json` — regen

**Тесты:** `server/tests/api/test_cards_resolve.py` — 4 теста: слияние двух решений в один ход (SSE index + сохранённая карточка), resolve идемпотентен/409/статус в истории, 404 на неизвестную карточку, resolve старой карточки без card_id.

## Результаты проверок

- `cd server`: ruff check ✅ · ruff format ✅ (2 файла переформатированы) · lint-imports ✅ (3/3 contracts) · pytest ✅ — все, кроме 4 предсуществующих фейлов `tests/api/test_from_url.py` (сеть: падают и на чистом HEAD без моих изменений, проверено через git stash; на CI зелёные)
- `cd web`: gen:api ✅ (59 путей) · lint ✅ · tsc ✅ · build ✅

## Отклонения и решения

1. **Слияние решений — replace, не append**: SSE-событие `card` получило поле `index` (позиция карточки в сообщении); вторая decision-карточка приходит как замена первой с расширенными `options` — клиент не плодит вторую группу и не дёргает высоту.
2. **Универсальные options**: карточки-решения нормализуются на сервере в `options: [{label, text}]` (у action_offer это Да/Нет с готовыми текстами ответа, у quick_replies — сами варианты); веб имеет тот же fallback для старых карточек.
3. **liveCards во время стрима** рендерятся disabled-кнопками той же высоты (не span-заглушками) — «без прыжка»; done-сообщение создаётся с настоящим message_id → refresh не пересоздаёт DOM.
4. **«Собрать курс» в разговоре** теперь prefill (как на старте), API-версия buildCourse из чипов удалена — план требовал одно поведение для одной надписи.
5. **prompt_change/git_change**: эндпоинты tuning/revision принимают опциональные `conversation_uid`+`card_id` (обратная совместимость), статус пишется карточке в сообщении.
6. **Ручная проверка в preview (desktop+375px) не выполнялась в этой сессии** (нет живого LLM-стенда под рукой без затрат квоты): покрытие — автотесты resolve-цикла + статическая сборка; перекрытия устранены конструктивно (fixed-кнопка удалена, toggle в потоке). Прошу ревьюера глянуть `/chat` на 375px.

## Вопросы

- Нет блокеров.
