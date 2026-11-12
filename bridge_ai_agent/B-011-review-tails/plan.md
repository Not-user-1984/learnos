# B-011 · Хвосты ревью B-003…B-010

Цель: закрыть недоделки, найденные на ревью и прод-смоуке 2026-11-12. Без новых фич.
Контекст: `B-008…B-010/review.md`, `B-009/report.md` §1, `docs/system-review-2026-11.md`.

## Готово, когда
- [ ] «Предложения» показывают только задачи, созданные агентами, а не весь бэклог человека.
- [ ] Задачи от агентов создаются и на проде (где `task_ai` смонтирован read-only).
- [ ] Принять ветку `agent/*` на проде можно: push однозначный, права и `gh` проверены, ошибка понятная.
- [ ] Роль `embed` включена с подтверждённой моделью z.ai, прод проиндексирован, гибридный поиск работает.
- [ ] `chat-view.tsx` ≤ 400 строк, SSE-цикл в хуке, поведение чата не изменилось.
- [ ] Мобильная вёрстка 375px проверена скриншотами: `/today`, `/chat` (с карточкой-решением), курс, глава со split-view.
- [ ] Проверки зелёные.

## 1. Фильтр «Предложений»
- Сейчас: `server/app/modules/proposals/service.py` `_idea_tasks` (~60) берёт все `status: idea` → на проде
  видны T-003, T-004… из бэклога человека.
- Сделать: метка автора в frontmatter задачи — `author: agent` (ставит `create_task_file`,
  `revision/service.py:~169-192`); `_idea_tasks` берёт только `author: agent`. Старые задачи агентов
  (если есть, `from:` начинается с «ревизия кода») — тоже считать агентскими.

## 2. Задачи агентов на проде
- В report B-010 сказано, что `task_ai` на проде read-only. Проверить на CT (`docker compose exec` / mount в
  compose-файле): работает ли `create_task_file`.
- Если read-only: `create_task_file` пишет в `data/proposals/tasks/T-AGENT-<дата>-<slug>.md` (data — rw),
  `_idea_tasks` читает обе папки. «Принять» такую задачу = отметка в БД + текст задачи показан для копирования
  в бэклог (человек переносит сам). Не давать сервису писать в git-дерево прода.

## 3. Принятие веток
- `proposals/service.py:~105`: `git push origin agent/x` → `git push origin refs/heads/agent/x:refs/heads/agent/x`
  (без неоднозначности с тегом).
- Проверить на CT: откуда берётся ветка (worktree в `data/git-worktrees/`), есть ли у этого репозитория remote
  с правом записи и токен, есть ли `gh`. Если `gh` нет — добавить в Docker-образ ИЛИ создавать PR через GitHub REST
  с тем же токеном (без печати токена). Ошибка push/PR — понятный текст в UI.
- Тест: команда push формируется с полным refspec (мок subprocess).
- Прод-смоук: сделать тестовую ветку через `git_prepare_change` (бюджет 3/день) → accept → PR создан → закрыть PR
  и удалить ветку вручную через `gh`. Записать результат в report.md.

## 4. Эмбеддинги
- Найти в документации z.ai (open.bigmodel / docs.z.ai) имя модели эмбеддингов и размерность для
  OpenAI-совместимого `/embeddings`. Проверить живым вызовом:
  `sec exec ZAI_API_KEY -- uv run python -m app.cli smoke-llm` (если smoke не умеет embed — добавить ветку `--embed`).
- Раскомментировать роль `embed` в `server/config/llm.yaml`. Пуш → деплой → на CT
  `uv run python -m app.cli reindex --embeddings` (в контейнере), проверить `GET /api/health`
  (`embed_configured: true`, `embed_pending_blocks: 0`) и `GET /api/search?q=…&mode=hybrid` по 3 запросам по смыслу.
- Если у z.ai нет совместимой модели эмбеддингов — не включать, записать в report.md, вопрос архитектору.
- **Решение (2026-11-12): у z.ai модели нет → эмбеддинги через OpenAI.**
  - Модель `text-embedding-3-small` (1536). Ключ уже в Keychain: `LEARNOS_OPENAI_API_KEY` (проверен, 200 на `/v1/embeddings`).
    Значение не печатать, только `sec exec LEARNOS_OPENAI_API_KEY -- …`.
  - Роль `embed` в `llm.yaml` — свой провайдер/base_url `https://api.openai.com/v1` и `api_key_envs: [OPENAI_API_KEY]`
    (провайдер ролей chat/fast/structured не трогать; если роутер не умеет провайдера на роль — добавить это
    в `app/llm/`, а не хардкодить OpenAI).
  - Прод: дописать `OPENAI_API_KEY=` в `/opt/learnos/.env` на CT 132 через `sec exec` + `pve.py exec/push`
    (как делал `deploy-learnos-container.sh`), проброс в compose-сервис; ключ не в git и не в логах.
  - Риск: OpenAI может быть недоступен с CT напрямую (регион) → запросы embed через прокси из настроек
    (xray socks5), как research. Проверить живым вызовом из контейнера.
  - Дальше — как выше: деплой, `reindex --embeddings`, health, 3 смысловых запроса hybrid.

## 5. chat-view.tsx
- Сейчас 588 строк (`web/src/components/chat/chat-view.tsx`). Вынести SSE-цикл в `web/src/components/chat/use-chat-stream.ts`:
  `useChatStream({conversationUid, onCard, onSession, onReviewProgress, onDone, onError})` → `{send, stop, streaming, liveText, liveCards}`.
  Состояние страницы (сессия, review-progress) обновляется через колбэки — то, на чём сломался прошлый вынос.
- Ручная проверка в preview на локальном стенде (сервер + web локально, живой LLM через `sec exec ZAI_API_KEY`):
  обычный ответ, ответ с карточкой-решением, сессия (смена фазы в панели), стоп, ошибка/повтор, панель главы (B-006).

## 6. Мобила 375px
- Локальный стенд, preview, viewport 375×812: скриншоты `/today`, `/chat` (ответ с action_offer, открыт кот),
  `/courses/<uid>`, `/library/<uid>/<chapter>` (книга и видео). Проверить: нет горизонтального скролла, кнопки не
  перекрыты. Найденное — чинить в этой же задаче. Скриншоты сохранить в `bridge_ai_agent/B-011-review-tails/shots/`.

## Проверки
- `cd server && uv run ruff check . && uv run ruff format --check . && uv run lint-imports && uv run pytest`
- `cd web && npm run gen:api && npm run lint && npx tsc --noEmit && npm run build`
- `wc -l web/src/components/chat/chat-view.tsx`

## Коммит / деплой
- Локальные коммиты по пунктам. Пункт 4 (эмбеддинги) и пункт 3 (прод-смоук accept) требуют прода: для них —
  push в main после зелёных проверок разрешён (это часть задачи), дальше смоук на CT. Остальное — без пуша, ревью у меня.

## Риски
- Квота GLM на эмбеддинги при бэкфилле книг — батчи, при исчерпании ключей job продолжит позже.
- Не ослаблять guard-лист `git_prepare_change` и бюджет 3/день.
