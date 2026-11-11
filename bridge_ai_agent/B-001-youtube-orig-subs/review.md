# B-001 · Ревью

## Раунд 1 — 2026-11-11 · вердикт: **done**

Коммиты: `23d85e0`, `092ac7d`, `3f3432c`, `768a718`. Прод CT 132 на `768a718`.

### Проверки
- server: ruff, format, lint-imports, pytest — зелёные; web: eslint, tsc — зелёные.
- Прод: `src_4425608e` → `status=processed`, `last_error=null`, 1 глава. Цель достигнута.

### По плану
- Шаги 1–3 (`run.py`): выполнены точно. `--ignore-errors`, `_pick_sub` с приоритетом `-orig`, очистка частичных
  файлов, честная ошибка 429 с хвостом stderr, `lang` без `-orig`.
- Шаг 4: `last_error` берётся из последнего failed job, только у failed-источников; REST и MCP — один
  сериализатор. Миграции нет.
- Шаг 5: тесты на все ветки из плана есть.

### Находки
- **minor** `web/src/app/library/[uid]/page.tsx:92`, `library-browser.tsx` — хардкод `rose-500`.
  Правило дизайн-системы — семантические токены; в проекте есть `destructive`
  (`web/src/app/globals.css:33`). Правильно: `border-destructive/30 bg-destructive/5`. Смягчающее
  обстоятельство: в файле статус failed уже раньше красился `text-rose-500` (`library-browser.tsx:27`). Не блокирует.
  Исправить при следующей правке библиотеки вместе со старыми rose-акцентами.
- **note** `list_sources` делает по запросу к `jobs` на каждый failed-источник (N+1), но failed-источников мало.
  Приемлемо.
- **note** в AGENTS.md упомянут `/var/log/learnos-deploy.log`, на CT его нет — логи только в
  `journalctl -u learnos-deploy.service`. Доку поправить при случае.

## Раунд 2 — 2026-11-11 · вердикт: **fix** (по просьбе пользователя добить minor)

Сделать:
1. `web/src/app/library/[uid]/page.tsx` (плашка last_error) и `web/src/components/library/library-browser.tsx`
   (last_error, статус failed `:27`, hover удаления `:119`): `rose-500` → семантический токен `destructive`
   (`text-destructive`, `border-destructive/30 bg-destructive/5`, `hover:text-destructive`). Градиент карточки
   видео (`:91`) — декоративный, не трогать.
2. `AGENTS.md` (и `README.md`, если там то же): убрать `/var/log/learnos-deploy.log`, оставить
   `journalctl -u learnos-deploy.service`.
3. Закоммитить всё, включая `bridge_ai_agent/` (review.md, BOARD, docs). `task_ai/bah-bah-report.md` — чужая
   правка пользователя, **не коммитить**. Push → дождаться автодеплоя на CT 132 → проверить health и что
   CT на новом коммите. Статус B-001 → review, отчёт дописать в report.md.

Проверки: `cd web && npm run lint && npx tsc --noEmit && npm run build`.
