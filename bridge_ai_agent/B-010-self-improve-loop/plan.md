# B-010 · Самоулучшение: планировщик, идеи → задачи, предложения агентов в UI, напоминания

Цель: система сама по расписанию ищет проблемы и идеи, превращает их в задачи и ветки с зелёными
проверками, а человек видит всё в одном месте и одним кликом принимает/отклоняет. Плюс напоминания о
повторениях. Мердж в main — по-прежнему только человек.
Зависит от: B-004 (review), желательно B-009. Контекст: `docs/system-review-2026-11.md` §6.

## Готово, когда
- [ ] Встроенный планировщик (без внешних зависимостей): таблица `schedules(name, cron, agent|job, args, enabled,
      last_run_at, last_status)`, тик раз в минуту в lifespan; один запуск одновременно на задачу.
- [ ] Расписания по умолчанию (выключены, включаются в UI): `auditor` раз в неделю, `repo_scout` раз в неделю,
      `review_digest` ежедневно 09:00 (Telegram: сколько повторений, ссылки).
- [ ] У `repo_scout` есть `create_task_file`; каждая идея с вердиктом «брать» → задача `task_ai/tasks/T-NNN` статус `idea`.
- [ ] Страница «Предложения» (`/settings` вкладка или `/proposals`): задачи-идеи от агентов, ветки `agent/*`
      (дифф, результат run_checks), правки промптов — с кнопками «Принять»/«Отклонить»; статус хранится на сервере.
- [ ] «Принять» ветку = push ветки в GitHub и создание PR (токен уже на CT), не мердж.
- [ ] Учёт сна хомлаба 19:00–08:30: пропущенный запуск выполняется при следующем тике после пробуждения (catch-up один раз).
- [ ] Проверки зелёные.

## Контекст в коде
- `server/app/modules/revision/service.py` — repo/tasks/git (`create_task_file` ~169, `git_prepare_change` ~223,
  guard-лист ~48-58, бюджет `kernel/config.py:41`), REST `revision/__init__.py:30-38`.
- `server/app/modules/chat/agents.py:155-173` — спека repo_scout; `research/tools.py` — `save_idea_report`.
- `server/app/modules/library/worker.py:32` — единственный фоновый воркер (пример lifespan-задачи).
- `server/app/modules/messenger/tools.py` — Telegram.
- `server/app/modules/tuning/api.py:36-46` — апрув правок промптов.

## Изменения
1. Модуль `modules/scheduler/`: domain (cron-парсер минимальный: `m h dom mon dow` с `*`, списками, шагами),
   infra-таблица + миграция, service (тик, лок через UPDATE … WHERE running=0), api (list/enable/run-now).
   Запуск агента — через существующий `run_agent` рантайм с `parent_run_id=None` и меткой `trigger=schedule`.
2. repo_scout: добавить `create_task_file` в его инструменты; промпт — правило «брать» → таска.
3. `modules/proposals/` (только service+api): агрегирует задачи со статусом idea и `from: agent`, ветки
   `agent/*` (через revision public), pending-правки промптов (через tuning public). Accept/reject проксирует в
   соответствующий модуль. Accept ветки: `git push origin agent/<slug>` + `gh pr create` (или GitHub REST)
   с описанием из коммита и результатом run_checks.
4. `review_digest`: job, берёт `GET review stats` и шлёт в Telegram, если `due_today > 0`.
5. Web: страница предложений + блок расписаний в настройках (включить/выключить/запустить сейчас, last_status).

## Тесты
- cron-парсер; тик не запускает дубль; catch-up после пропуска; accept ветки зовёт push+PR (замокать git/gh).

## Проверки
- `cd server && uv run ruff check . && uv run ruff format --check . && uv run lint-imports && uv run pytest`
- `cd web && npm run gen:api && npm run lint && npx tsc --noEmit && npm run build`

## Риски
- Агенты по расписанию тратят квоту GLM: дефолт — выключено, бюджет веток 3/день сохраняется.
- Push из CT: ветки `agent/*` не должны триггерить деплой (таймер следит только за main) — проверить.
- Guard-лист git_prepare_change не ослаблять.
