# B-013 · Ревью, раунд 1 (2026-11-17) — fix

Ок: блок только через `finish_session` (verified, block_sources, SessionFinished); стейт-машина урока не тронута;
text-layer, редирект `?mode=pdf`, место в activity работают. Правки вне плана (`verified` в `_meta_dict`, `block_kind`) принимаются.

## Исправить
1. **major** `chat/service.py:129` `chapter_conversation` + commit-роут — `chapter_idx` не валидируется.
   Глава 9999 создаёт сессию, финиш уводит курсор за total, книга становится «done».
   Нужно: проверять существование главы в `src.chapters`, иначе 404 (как `mark_read`, `learning/service.py:~425`).
2. **major** `learning/service.py:487` `start_chapter_session` — возвращает любую активную сессию разговора без проверки kind.
   Нужно: проверять `config.kind=="chapter"`, иначе `InvalidState`.
   Чип «Записать в базу» (`web/src/components/chat/next-steps.tsx:64`) показывать только для chapter-сессии.
3. **major** повторное «Записать в базу» после завершённой главы — `find_by_conversation` (`learning/infra/sql_repo.py:38`) ищет только active.
   Создаётся вторая сессия и дубль блока. Нужно: если по главе уже есть finished chapter-сессия с блоком —
   вернуть этот блок (или обновить его новой версией), второй блок не создавать.
4. **major** позиция чтения:
   - финиш главы-сессии (`learning/service.py:306`) двигает курсор без синхронизации position;
   - `_advance_cursor` (`~574`) затирает страницу, даже если курсор не сдвинулся.
   Нужно: position меняется, только когда курсор реально ушёл вперёд — тогда на начало новой главы. Иначе не трогать.
5. **minor** `set_position` (`learning/service.py:367`, `learning/api.py:65`) — нет верхней границы. Нужно: chapter ≤ total, page ≥ 1, иначе 422.
6. **minor** `web/src/components/library/pdf-reader.tsx:163` — авто-«прочитано» срабатывает только через `goToChapter`.
   Нужно: также при переходе currentChapter вперёд листанием или скроллом (с предыдущей главы на следующую по порядку), по одному разу на главу.
7. **minor** быстрый разбор главы книги из /chat (`knowledge/agents.py:121`, preview_note/save_note) пишет неверифицированный блок мимо SessionFinished.
   Нужно: для источника-книги с главой сценарий quick ведёт в тот же chapter-путь (`commit_chapter`); для заметок без источника save_note остаётся.
8. Тесты на п.1–5 (глава вне диапазона → 404; чужая сессия → InvalidState; повторный commit → тот же block_uid; позиция не затирается).
9. **e2e с живой LLM**: если `sec exec ZAI_API_KEY` доступен, прогнать чат главы → ответы → commit → verified-блок
   (`uv run python -m app.cli smoke-llm` + сценарий). Результат записать в report; если ключ недоступен — так и написать.

## Готово, когда
Пункты 1–8 закрыты тестами, проверки зелёные, п.9 отражён в report.md.

# Раунд 2 (2026-11-17) — done
Пункты 1–9 закрыты; e2e с живой glm-5.3: чат главы → вопросы → commit_chapter → verified-блок с block_sources.
Мелочи в бэклог: мёртвый `ActivityRepository.all_for_conversation` (`learning/infra/sql_repo.py:130`);
`save_note` с source+chapter сервером не запрещён (гард только в промпте); `set_position` при total=0 → 422.
