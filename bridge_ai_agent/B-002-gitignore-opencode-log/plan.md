# B-002 · Логи OpenCode не попадают в git + коммит bridge

## Цель
`opencode.log`, который обёртка `glm exec` пишет в папку задачи, игнорируется git. Незакоммиченные файлы bridge
(финальное ревью B-001, BOARD) закоммичены.

## Шаги
1. В корневой `.gitignore` проекта добавить строку `bridge_ai_agent/**/opencode.log` с комментарием
   «# логи исполнителя glm exec».
2. Удалить из рабочей копии `bridge_ai_agent/B-001-youtube-orig-subs/opencode.log` (untracked, не нужен).
3. Закоммитить `.gitignore` и всё изменённое в `bridge_ai_agent/` (review.md B-001, BOARD.md, папку B-002).
   `task_ai/bah-bah-report.md` — правка пользователя, **не коммитить**.
4. Push в main. Кода сервера и веба нет — ждать деплой и проверять прод не нужно.
5. Статус B-002 → review, коротко записать в `report.md`.

## Критерии готовности
- [ ] `git status --short` после работы показывает только `M task_ai/bah-bah-report.md`.
- [ ] `git check-ignore bridge_ai_agent/B-002-gitignore-opencode-log/opencode.log` выдаёт путь, то есть файл игнорируется.
- [ ] `origin/main` = локальный HEAD.
