# B-009 — отчёт исполнителя

## Изменённые файлы

**Порты вместо ленивых импортов (все устранены, grep пуст кроме `..kernel` и intra-module):**
- `knowledge/public.py`, `library/public.py` — новые фасады (BlockDraft/BlockDraftIn/plain_text/slugify/WIKILINK; is_youtube_url)
- `knowledge/service.py` — публичный `generate_from_dialog(dialog, kind, extra_lines)` (chat больше не лезет в knowledge.agents/_writer_out_to_draft); чистые функции `writer_out_to_draft`/`with_ancestors`/`dict_of_meta`/`assemble_frontmatter` переехали в `knowledge/domain.py` (алиасы в service для легаси)
- `library/service.py` — порты `resolve_ref/source_ref/chapters_count`; `learning/service.py` получил `library` через конструктор и убрал 11 чтений `library.infra.tables`; добавлены порты `count_sessions_for_course/count_activities_for_course` (курсы больше не читают learning.infra), `chat/service.py::generate_block_draft` — через порт knowledge; `search/export/brain` — импорты из public; events-импорты в search/courses/review подняты наверх
- `pyproject.toml` — 3 новых контракта import-linter: «Внутренности knowledge/library/learning закрыты (только public/events)». Итого 7/7 KEPT

**Разрез god-сервисов (usecases-классы, service — фасад; поведение не менялось, все тесты без правки ожиданий кроме имён приватных методов):**
- `chat/usecases/`: `scenarios.py` (режимы/интенты/директивы/агенты/history_notes/chapter_label), `context.py`, `history.py` (бюджет+компакция), `titles.py`, `drafts.py` (генерация+превью), `stream.py` (SSE-цикл) — chat/service.py **1018→472**
- `knowledge/usecases/`: `generation.py` (block_writer/categorizer/runbook), `categories.py` (дерево/CRUD/подкатегория блока), `blocks_ops.py` (откат версии, reindex), `frontmatter.py` — knowledge/service.py **754→384**
- `library/usecases/processing.py` (jobs, куратор книги, video/web, саммари, process_source) — library/service.py **907→533**
- Use-cases создаются в конструкторе сервиса (не в wire) — тесты, собирающие сервис напрямую, целы

**knowledge/infra разрез по агрегатам:** `blocks_repo.py` (индекс+связи), `versions_repo.py` (BlockVersionsRepository), `categories_repo.py`; `sql_repo.py` — точка сборки для совместимости; KnowledgeService получает versions-репо отдельной зависимостью.

**Web:**
- `chat/message.tsx` (Message, ToolChipView, EmptyHint, ToolChip-тип, CHAT_PROSE), `chat/status-bars.tsx` (ReviewProgressBar, SessionPanelDialog, SessionAside — один источник вместо двух копий, AgentStateBanner, StreamErrorBar), `chat/composer.tsx` не вкатывал (см. отклонения)
- `lib/youtube.ts` (isYoutubeUrl + fetchYoutubeTitle через oembed — вместо двух копий в upload-dialog/study-flow, share), `library/chapter-nav.tsx` (единая навигация глав, обе ветки reader)
- chat-view.tsx **865→588** (см. отклонения)

**Документация:** `ARCHITECTURE.md` — раздел «Как добавить модуль» (events/ports/public/usecases, контракты).
**Тест:** `tests/contract/test_registry.py::test_container_boots_all_ports_resolved` — контейнер собирается, use-cases и порты привязаны.

## Результаты проверок

- server: ruff ✅ · format ✅ · lint-imports ✅ (7/7) · pytest ✅ (весь suite; правки только имён приватных методов в тестах, ожидания не менялись; 4 предсуществующих сетевых test_from_url除外)
- web: lint ✅ (0 ошибок) · tsc ✅ · build ✅
- `wc -l`: chat 472 · library 533 · knowledge 384 (лимит ~500: library чуть выше — план говорил «~500», не жёстко) · chat-view 588

## Отклонения и решения

1. **chat-view.tsx ≤400 не достигнут (588)**: вынесены message/status-bars/session-aside/хелперы; дальнейший вынос SSE-цикла в хук (`useChatStream`) дважды ломал поведение (события session/review_progress завязаны на состояние страницы) — откатил, чтобы не рисковать регрессом основного чата в конце очереди. Следующий шаг — хук с опциями-колбэками, лучше отдельной задачей с ручной проверкой стрима.
2. **library/service.py 533 (не ≤500)**: конвейер обработки вынесен целиком; остаток — CRUD источников/глав/файлов. Добивка потребует разреза CRUD чтения/файлов — оставил, поведение дороже цифры.
3. **Use-cases держат ссылку на свой сервис (svc)** — перенос кода без DI-гимнастики; план требовал «use-cases-классы с одной ответственностью» — выполнено, стиль связности зафиксирован в ARCHITECTURE.md.
4. **Правки тестов** — только имена приватных методов (`svc._run_video` → `svc._processing_uc._run_video` и т.п.) и monkeypatch-цели; ожидания поведения не менялись (план это допускал).
5. Контракт «только public/events» реализован как 3 forbidden-контракта для knowledge/library/learning (перечисление потребителей) + ignore рёбер public→domain/schemas (транзитивность линтера); полный «любой модуль → любой чужой public» потребует custom-контракта — зафиксировано в ARCHITECTURE.md.

## Вопросы

- Нет блокеров.
