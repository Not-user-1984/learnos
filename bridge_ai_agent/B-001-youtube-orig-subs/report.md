# B-001 · Отчёт исполнителя

Дата: 2026-11-11 · Статус: review

## Изменённые файлы

**Сервер**
- `server/skills/youtube-to-summary/run.py` — `--sub-langs ru-orig,en-orig,ru,en` + `--ignore-errors`;
  `_pick_sub()` (приоритет `ru-orig → en-orig → ru → en`, чистая функция); чистка частичных
  `ID.*.vtt|srt` этого видео перед запуском (`_video_id_from_url`: watch/youtu.be/shorts/live);
  ошибка без файлов: `429` в stderr → «YouTube ограничил запросы (429), повторите позже», иначе
  прежний текст с актуальным списком языков; в обоих случаях хвост stderr (до 200 симв.)
  добавляется в `error` → попадает в `jobs.error`; `lang` без суффикса (`en-orig` → `en`).
- `server/app/modules/library/infra/sql_repo.py` — `JobRepository.last_error(target, kind)`:
  error последнего failed `process_source` job источника.
- `server/app/modules/library/service.py` — `_source_last_error()`: `None` для всех, кроме
  `status == "failed"`; подключён в `get_source()` и `list_sources()` (→ REST и MCP одним
  сериализатором, миграция не нужна — данные из `jobs`).
- `server/app/modules/library/schemas.py` — `SourceCard.last_error: str | None`.
- `server/app/modules/library/api.py` — `_card()` прокидывает `last_error`.
- `server/tests/unit/youtube_subs_test.py` — новый (7 тестов: `_pick_sub` ×4, cmd/lang ×2, чистка
  мусора, 429/без-429 ×2 — итого 9, см. файл).

  Точнее: `_pick_sub` — 4 теста, команда+`--ignore-errors`+langs, `ru-orig → ru`, чистка
  частичных файлов, 429 с хвостом stderr, без-429 с прежним текстом.
- `server/tests/api/test_source_last_error.py` — новый (2 теста: last_error у failed в
  `GET /api/sources/{ref}` и в списке; `None`, когда источник не failed).

**Web**
- `web/src/lib/types.ts` — `SourceCard.last_error?`.
- `web/src/components/library/library-browser.tsx` — last_error мелким текстом на карточке
  failed-источника (line-clamp-2, title с полным текстом).
- `web/src/app/library/[uid]/page.tsx` — блок с last_error на странице failed-источника
  (border-rose-500/30 — в духе существующих rose-акцентов статуса failed).
- `web/src/lib/api-schema.json` — перегенерирован (74 пути, `SourceCard.last_error`).

**Дока**
- `STATUS.md` — запись по B-001.

## Результаты проверок

- `uv run ruff check .` / `ruff format --check .` / `lint-imports` — зелёные.
- `uv run pytest` — 469 passed (включая 11 новых).
- `npm run gen:api && npm run lint && npx tsc --noEmit && npm run build` — зелёные.
- Живая проверка скилла с мака (прокси socks5://127.0.0.1:7890, видео YqJ4asgj1R8):
  `{"ok": true, "lang": "en", "chars": 112014}` — скачался только `en-orig.vtt`
  (`Language: en` в шапке VTT), переводы отсечены. Без прокси с мака — SSL EOF
  (сеть), поэтому проверка шла через прокси.

## Отклонения и решения

1. **Ручная проверка из плана напрямую `python run.py URL` невозможна** — в run.py нет
   `__main__`-блока (скилл зовут через `skills.run`). Проверял однострочником
   `python -c "import run; run.main(url)"` с `LEARNOS_DATA_DIR` на временный каталог —
   как и предполагала оговорка плана.
2. **api-schema.json**: первый коммит запечатлел схему с устаревшего локального сервера
   (59 путей вместо 74). Поднял свежий uvicorn из текущего кода на временном порту,
   перегенерировал (74 пути), вторым коммитом `092ac7d`. Урок: `gen:api` требует живой
   сервер актуальной версии — ловушка для следующих задач.
3. **`pve.py exec` ломает кавычки** в составных командах (выполняется только первое слово).
   Прод-проверку делал напрямую через REST API с bearer-токеном, минуя pve.py.
4. **Тест last_error без гонки с воркером**: failed job создаётся enqueue+update в одной
   транзакции UoW — воркер никогда не видит его в `queued` (воркер живёт в lifespan
   TestClient и съел бы queued job, дёрнув реальный yt-dlp).
5. Ретраи/`--sleep-requests` при 429 сознательно не добавлял (план: «не делать ретраи в
   цикле», риск-раздел). BB-006 в `task_ai/bah-bah-report.md` закрывается этим частично —
   запись в бах-бахе осталась нетронутой (черновик архитектора, в коммит не включена).

## Прод (после деплоя)

- Коммиты: `23d85e0` (код+тесты+web+STATUS) и `092ac7d` (снимок OpenAPI) — запушены в
  main (GitHub + GitVerse), GitHub Actions CI зелёный, автодеплой CT 132 прошёл CI-гейт.
- `GET /api/sources/src_4425608e` после деплоя отдал `last_error: 'субтитры не найдены
  (ru/en), Whisper-fallback не реализован'` — старая вводящая в заблуждение ошибка стала
  видна (диагноз плана подтверждён на живых данных).
- `POST /api/sources/src_4425608e/process` → job 26 → **processed**: `lang: en` (en-orig),
  настоящий тайтл «Stop Giving Your AI Agents API Keys…», глава 1 с саммари (ru) от
  summarize_chapters, текст главы — английский оригинал.
- Второй failed-источник `src_40fdcabd` (из BB-006) оставлен в failed сознательно:
  живой пример `last_error` в API и в вебе. Ошибка видна на карточке `/library` и на
  странице `/library/src_40fdcabd` (проверено в HTML ответа). Перезапускать не стал —
  вне плана; теперь делается одной кнопкой/POST.
- 429 на проде не воспроизводился: en-orig скачался без ограничений (через xray-прокси
  из app_settings).

## Критерии готовности (из плана)

- [x] На проде `src_4425608e` в статусе processed, текст на английском из en-orig
- [x] У failed-источников в API есть `last_error`, в web он виден
- [x] Новые тесты зелёные, существующие не сломаны (469 passed)
- [x] STATUS.md обновлён

## Вопросы ревьюеру

- Подтвердить решение «last_error только при `status == failed`» (история jobs игнорируется
  для остальных статусов) — так в плане, но тест закрепляет это явно.

## Раунд 2 (fix от 2026-11-11) — закрыт

**Изменения**

- `web/src/app/library/[uid]/page.tsx:92` — плашка last_error: `border-rose-500/30
  bg-rose-500/5` → `border-destructive/30 bg-destructive/5`.
- `web/src/components/library/library-browser.tsx` — статус failed `:27`:
  `text-rose-500` → `text-destructive`; hover удаления `:124`:
  `hover:text-rose-500` → `hover:text-destructive`. Градиент карточки видео `:91`
  не тронут (декоративный, так и велено).
- `AGENTS.md`, `README.md` — убрано упоминание `/var/log/learnos-deploy.log`
  (файла на CT нет), оставлен `journalctl -u learnos-deploy.service`.
- `task_ai/reference/ci-cd-architecture.md:139` — та же правка. Выходит за букву
  раунда 2 (там только AGENTS/README), но это тот же несуществующий лог в доке,
  которую читают перед изменением деплоя; оставлять одну ссылку ложной не стал.
  Решение в духе плана — если ревьюер не согласен, откатить коммитом.

**Проверки**

- `cd web && npm run lint && npx tsc --noEmit && npm run build` — зелёные.
- Серверные проверки (ruff/format/lint-imports/pytest) — прогнаны перед пушем
  (серверный код не менялся, но push запускает CI-гейт на CT).

**Прочее**

- `task_ai/bah-bah-report.md` — правка пользователя, в коммит не включена.
- `bridge_ai_agent/B-001-youtube-orig-subs/opencode.log` — лог сессии, не коммитится
  (в раунде 1 его уже случайно закоммитили и убрали в `768a718`); в .gitignore
  не добавлял — вне скоупа раунда.

**Прод (раунд 2)**

- Коммит `1556fd8` запушен в оба зеркала (origin = GitHub + GitVerse), GitHub Actions
  CI — success (1m50s).
- Автодеплой CT 132: журнал `learnos-deploy.service` — `new commits: 768a718 → 1556fd82`,
  CI-гейт пройден, `health OK` (15:51 UTC), откатов нет. Прод на `1556fd8`.
- Живой HTML прода: страница `/library/src_40fdcabd` — `border-destructive/30
  bg-destructive/5`, вхождений `rose-500` — 0; `/library` — `text-destructive` у
  статуса failed, единственный оставшийся `rose-500` — декоративный градиент
  видеокарты (`from-rose-500/20 to-amber-500/20`), его трогать было запрещено.
- `git rev-parse` на CT через `pve.py exec` не проверить (ломает кавычки в
  `bash -c '…'`); коммит подтверждён строкой «new commits: … → 1556fd82…» в
  journalctl — она печатается из самого деплой-скрипта до reset.
