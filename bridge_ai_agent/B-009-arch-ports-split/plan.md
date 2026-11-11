# B-009 · Архитектура: порты вместо ленивых импортов, разрез god-сервисов, контракты линтера

Цель: модули связаны только событиями и явными портами; ни один сервис не больше ~500 строк; новые фичи
добавляются новым модулем без правки chat/service. Поведение системы не меняется (чистый рефакторинг).
Делать после B-003 и B-004 (те же файлы). Контекст: `docs/system-review-2026-11.md` §1, §5.

## Готово, когда
- [ ] В `server/app/modules/*/` нет импортов чужих модулей внутри тел функций
      (`grep -rnE "^\s+from \.\.[a-z]+\." server/app/modules` пусто, кроме `..kernel`).
- [ ] Межмодульные синхронные зависимости — через `modules/<x>/ports.py` (Protocol) и/или публичный фасад
      `modules/<x>/public.py`; import-linter контракт: модуль может импортировать у другого только `public`/`events`.
- [ ] `chat/service.py`, `library/service.py`, `knowledge/service.py` ≤ 500 строк каждый; логика вынесена в
      `usecases/`-классы с одной ответственностью.
- [ ] `knowledge/infra/sql_repo.py` разрезан по агрегатам (blocks / versions / links / categories).
- [ ] Web: `chat-view.tsx` ≤ 400 строк (вынести SessionPanel — один компонент вместо двух копий aside/диалог,
      StatusBars, Composer); общие хелперы — YouTube-URL→источник (×3), навигация глав (×3).
- [ ] Все тесты зелёные без правки их ожиданий (правка импортов в тестах допустима).

## Контекст в коде
- Ленивые импорты: `learning/service.py:~502` (`knowledge.schemas`), `chat/service.py:~856` (`knowledge.agents`,
  `knowledge.service`) — найти все: `grep -rnE "^\s+from \.\.(?!kernel)" server/app/modules` (через `rg -P`).
- Контракты: `server/pyproject.toml:71-95`.
- ChatService ответственности (методы ~303, ~596, ~649, ~681, ~809, ~847): SSE-стрим, компактизация истории,
  титулы, интенты/сценарии, драфты блоков, review-прогресс.
- Web-дубли: `library/upload-dialog.tsx:7`, `share/page.tsx:21`, `chat/study-flow.tsx:144-160`;
  `library/reader.tsx:282-329`, `library/pdf-reader.tsx:176-209`; `chat-view.tsx:600-618` vs `683-712`.

## Изменения
1. Для каждого межмодульного использования: событие (если это реакция) или порт (если нужен ответ).
   Порты регистрируются в контейнере в `bootstrap.py`; потребитель получает реализацию через конструктор.
2. ChatService → `chat/usecases/{stream.py, history_compaction.py, titles.py, intents.py, block_drafts.py}`;
   `service.py` — тонкий фасад.
3. library: отделить конвейер обработки (`usecases/processing.py`) от CRUD источников.
4. knowledge: генерация блоков агентами (`usecases/generation.py`) отдельно от хранения.
5. Новый контракт import-linter (layers/forbidden): `app.modules.X` → `app.modules.Y` разрешено только
   `app.modules.Y.public` и `app.modules.Y.events`.
6. Web: вынести компоненты/хелперы, перечисленные в «Готово, когда».
7. Обновить `ARCHITECTURE.md`: раздел «Как добавить модуль» (events, ports, public, tools, api).

## Тесты
- Существующий набор целиком; плюс тест на bootstrap: контейнер собирается, все порты разрешены.

## Проверки
- `cd server && uv run ruff check . && uv run ruff format --check . && uv run lint-imports && uv run pytest`
- `cd web && npm run lint && npx tsc --noEmit && npm run build`
- `wc -l server/app/modules/{chat,library,knowledge}/service.py web/src/components/chat/chat-view.tsx`

## Риски
- Большой дифф: коммитить по шагам (один модуль = один коммит), после каждого — полный pytest.
- Циклические зависимости портов при сборке контейнера — ленивое разрешение через фабрики в bootstrap.
