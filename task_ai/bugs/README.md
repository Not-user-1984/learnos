# task_ai/bugs — реестр багов

Найденные проблемы продукта. Один баг — один файл `BUG-<ннн>-<slug>.md`.
Статусы: `open` (нашёл, не чиню) → `tasked` (заведена задача) → `fixed`.
Файлы правятся по мере расследования; при починке — ссылка на задачу/коммит.

| ID | Симптом | Статус |
|---|---|---|
| [BUG-001](BUG-001-action-offer-no-feedback.md) | «Да» карточки без отклика; повторы создают дубли сообщений | fixed → [T-044](../archive/2026-10-28-T-044-chat-incident-fixes.md) |
| [BUG-002](BUG-002-link-navigates-away.md) | Клик по ссылке уводит со страницы; меню спрятано в шевроне 18px | fixed → [T-044](../archive/2026-10-28-T-044-chat-incident-fixes.md) |
| [BUG-003](BUG-003-long-run-invisible.md) | Часовой запуск без понятного прогресса и управления из UI | fixed → [T-044](../archive/2026-10-28-T-044-chat-incident-fixes.md) (стрим в БД и лимит длительности — отложено) |
| [BUG-004](BUG-004-stale-browser-cache.md) | После деплоя вкладка сидит на старой сборке («всё исчезло») | fixed → [T-044](../archive/2026-10-28-T-044-chat-incident-fixes.md) |
| [BUG-005](BUG-005-active-runs-window.md) | Подозрение: окно 2ч в active_runs не фильтрует старые запуски | fixed → [T-044](../archive/2026-10-28-T-044-chat-incident-fixes.md) |
| [BUG-006](BUG-006-research-autoadds-sources.md) | Research сам добавляет источники в Библиотеку; нужно: список кандидатов на редактирование и апрув | fixed → [T-048](../tasks/T-048-research-profile-fixes.md) (карточка с чекбоксами — T-014 Э3) |
| [BUG-007](BUG-007-profile-about-ignored.md) | «О себе» не влияет на ответы (девопс-аналогии при профиле Python-разработчика) | fixed → [T-048](../tasks/T-048-research-profile-fixes.md) |
