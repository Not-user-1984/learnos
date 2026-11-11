# B-010 — отчёт исполнителя

## Изменённые файлы

**Планировщик (новый модуль `modules/scheduler/`):**
- `domain.py` — минимальный cron-парсер (`m h dom mon dow` со `*`, списками, диапазонами, шагами), `cron_due(expr, last_run, now)` поминутным проходом (сон хомлаба → catch-up ровно один раз; окно ограничено 2 сутками)
- `infra/tables.py` + `infra/sql_repo.py` — таблица `schedules(name, cron, action, args_json, enabled, last_run_at, last_status)`; атомарный захват запуска (`try_acquire`: UPDATE … WHERE last_status != 'running')
- `service.py` — `tick()` (лок на задачу), `run_now()`, дефолты **выключены**: `auditor` (пн 05:00, agent:auditor), `repo_scout` (пт 06:00, agent:repo_scout), `review_digest` (ежедневно 09:00 → Telegram при due_today > 0); запуск агента — через agent runtime с меткой `trigger=schedule`
- `api.py` — `GET /api/schedules`, `POST /api/schedules/{name}/enable`, `POST /api/schedules/{name}/run`
- `main.py` — `_scheduler_loop` в lifespan (тик раз в минуту через to_thread, ошибки не роняют цикл), `ensure_defaults()` после миграций
- `migrations/versions/0020_schedules.py`

**repo_scout:** `chat/agents.py` — инструмент `create_task_file`; `agents/repo_scout/prompt.md` — правило «вердикт "брать" → create_task_file (статус idea)».

**Предложения (новый модуль `modules/proposals/`):**
- `service.py` — агрегация: задачи `task_ai/tasks/*.md` со статусом idea + ветки `agent/*` (revision.prepared_branches) + pending-правки промптов (tuning.changes); `decide()`: решения в БД (`proposal_decisions`, миграция `0021`) — task_ai на проде read-only; accept ветки = `git push origin agent/*` (guard префикса) + `gh pr create --fill` (нет gh — push есть, PR человек создаст по ссылке); мердж остаётся за человеком
- `api.py` — `GET /api/proposals`, `POST /api/proposals/{kind}/{ref}/decide`

**Web:**
- `app/proposals/page.tsx` — «Предложения агентов»: задачи-идеи («Взять в работу»/«Отклонить»), ветки («Push + PR»/«Удалить»), правки промптов; навигация: пункт «Предложения»
- `components/settings/schedules.tsx` — блок «Расписания самоулучшения» в настройках: вкл/выкл/запустить сейчас, cron и last_status
- `lib/api-schema.json` — regen (87 путей)

**Тесты:** `tests/unit/self_improve_test.py` — cron-формы (`*/15`, недельный, never-run), catch-up после сна; тик с локом (повторный тик — 0 запусков); run_now; предложения: список идей (done-задачи не видны), reject скрывает, accept ветки → git push (subprocess замокан, guard agent/*).

## Результаты проверок

- `cd server`: ruff ✅ · format ✅ · lint-imports ✅ (7/7) · pytest ✅ (весь suite; миграции до 0021 зелёные; кроме 4 предсуществующих сетевых test_from_url)
- `cd web`: gen:api ✅ (87 путей) · lint ✅ · tsc ✅ · build ✅ (/proposals в сборке)

## Отклонения и решения

1. **Решения по предложениям — в БД, а не в файлах**: task_ai смонтирован на проде read-only; решения в `proposal_decisions` переживают перезапуск и скрывают принятое/отклонённое из списка.
2. **PR через `gh`** если CLI есть; иначе только push — ссылку compare человек откроет сам (наличие gh на CT не проверял, пуша не было по правилам задачи).
3. **Тик раз в минуту через to_thread** — не блокирует event loop; агентные запуски идут в том же тике последовательно (квота GLM защищена дефолтным «выключено» и бюджетом веток 3/день из revision).
4. **review_digest шлёт только при due_today > 0** — молчит, когда повторять нечего.
5. Живой прогон расписаний на проде (включить auditor, дождаться тика) — не выполнял: пуша нет; покрыт тик-тестом с моком Telegram.

## Вопросы

- Нет блокеров.
