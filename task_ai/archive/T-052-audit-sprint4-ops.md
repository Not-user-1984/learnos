---
id: T-052
title: "Аудит 2026-11-01, спринт 4: эксплуатация и чистка (R-16, R-21, R-23, R-25..R-31, D, G)"
status: done
priority: medium
from: внешний аудит [task_ai/reference/audit-2026-11-01.md](../reference/audit-2026-11-01.md), спринт 4 + разделы «Архитектура D/G»
created: 2026-11-01
---

## Что нужно

Эксплуатация и чистка из аудита:

- **D. Единое ядро знания без расхождения MD ↔ БД**: канонический JSON-драфт + рендер в MD
  (правки над структурой, reindex без потерь, версии по структуре); `kb/` — отдельный
  приватный git-репо с авто-коммитами (бэкап и история), из основного репо — в .gitignore.
- **G. Эксплуатация**: CI (GitHub Actions: ruff/pytest/import-linter/tsc/build), деплой только
  по зелёному; healthcheck в compose + depends_on condition; откат на предыдущий образ;
  бэкапы SQLite `sqlite3 .backup` перед миграцией и по расписанию + копия kb/; миграции
  fail-fast (убрать тихий create_all-fallback); пин версий образов (uv, xray), регулярный
  `yt-dlp -U`, сервер не от root.
- **R-16** 500 вместо 409 при удалении курса/источника с зависимостями (IntegrityError) →
  явные проверки → Conflict.
- **R-21** (часть D/G): `kb/` в git + `reset --hard` прода откатывает правки; дубли конспектов
  по source+chapter (искать перед save_note, предлагать update/слияние); save_note не резолвит
  заголовок источника и не передаёт activity_uid.
- **R-23 LLM-слой**: сборка tool-call в стриме по `tc.id` (дельты идут с index) — ключ index;
  коллизии фолбэк-id `call_<name>`; `run_coro_sync` создаёт и не закрывает AsyncOpenAI-клиенты
  (утечка) → выделенный фоновый loop; роль fast = та же модель → привязать лёгкую модель;
  проверить условия тарифа coding-endpoint; ModelRouter.status проверяет только chat.
- **R-25 Веб**: share не запускает process для kind=web, PDF-ссылки не поддержаны →
  `/sources/from-url` во всех 4 местах («Добавить источник», StudyFlowDialog, share, ActionLink);
  pickLibrary без catch → 409 без тоста; поллинг summarize 60с мало; chat-view бесконечный
  опрос при зависшем последнем сообщении; машины в профиле нельзя добавлять/удалять;
  apiUpload теряет текст ошибки; AppShell дергает /conversations и /kb/inbox на каждый переход;
  violet-500 в GitChangeCardView против DESIGN.md; lucide-react в зависимостях; `npm run
  gen:api` отсутствует.
- **R-26 Конфигурация**: os.environ мимо Settings (agent/runtime, research/*, review/service,
  skills, connectivity), apply_to_settings пишет в os.environ и не сбрасывает ключ при смене
  провайдера, telegram_proxy не сбрасывается при очистке → Settings + RuntimeConfig
  (thread-safe, событие «изменилось», подписчики httpx/Telegram).
- **R-27 N+1**: get_activity → list_activities() по 2 запроса на активность; вызывается из
  get_conversation каждые 5с и каждого tool_end; _with_progress двойной list_blocks →
  точечные запросы с join, GROUP BY.
- **R-28 Доки и мёртвый код**: счётчики модулей/инструментов/тестов из одного источника
  (/api/health → скрипт в доки); ToolSpec.modes не применяется; хардкод head-ревизии в
  test_migrations → ScriptDirectory.get_current_head(); дубли заголовков AGENTS.md.
- **R-30 Курсы**: create_from_plan падает на выдуманном uid (валидировать план, отбрасывать
  мусор); plan_course через легаси-DDG скилл → ResearchService.search; веб-источники плана
  не обрабатываются автоматически.
- **R-31 Категории и связи**: categorizer создаёт новые корни (валидировать корень ∈ существующих,
  глубина ≤3, нормальные titles); links не проверяются на существование; _rootColor на три
  корня; lucide-иконки в default_categories при Material Symbols; «Принять» на блоке без
  категории подтверждает null.

## Критерии готовности

- [x] CI зелёный на push, деплой только по зелёному, откат работает
- [x] Бэкапы SQLite+kb по расписанию и перед миграцией; миграция fail-fast
- [x] Удаление курса/источника с зависимостями → 409 с понятным текстом
- [x] Дубли конспектов предотвращаются; история kb в отдельном репо
- [x] LLM-стрим с tool-call дельтами по index проходит на мок-провайдере
- [x] Веб: один механизм добавления источника по URL, тосты на 409, DESIGN.md чист
- [x] Счётчики в доках генерируются; os.environ вне Settings перечислены и устранены

## Заметки

- Можно дробить и брать пункты независимо; R-16/R-27/R-28 — быстрые победы, начать с них.

## Итог (закрыта 2026-11-01, спринт одним заходом)

- К1 `d023349`+`257939a` (G/D): миграции fail-fast с бэкапом sqlite .backup перед прогоном
  (ротация 10), healthcheck в compose + web ждёт service_healthy, uv запинен, kb/ выведен
  из основного репо (.gitignore)
- К2 `337a87a` (R-16/R-27/R-30/R-31): удаление курса/источника с зависимостями — Conflict
  вместо 500; get_activity точечным запросом; create_from_plan валидирует uid планировщика
  (skipped_invalid_uids); plan_course на цепочке провайдеров; categorizer не плодит корни
- К3 `2d35ce0` (R-23): сборка tool-call в стриме по tc.index (призрачные вызовы исчезли),
  уникальные фолбэк-id, единая фоновая петля (клиенты LLM не плодятся), status() по всем
  ролям с reason
- К4 `ebb8275` (R-26/R-28): смена провайдера сбрасывает чужой ключ, очистка прокси —
  и telegram_proxy; modules/tools в /api/health; мёртвые ToolSpec.modes удалены
- К5 `bce301b`..`ad6ad72` (R-25): addSourceFromUrl — единая точка /sources/from-url
  (share чинен), тосты ошибок pickLibrary, поллинг summary 180с, violet→токены, стоп
  пустого опроса чата, машины профиля add/remove, apiUpload с текстом ошибки, gen:api
- К6 (proxmox `0b9858c`): ensure_backups в learnos-deploy.sh — kb/ git-репо с авто-коммитами
  + ежедневный бэкап (sqlite .backup + kb tar, ротация 14, timer 09:15 Persistent)

CI (GitHub Actions + гейт на проде) закрыт ранее (см. ci-cd-architecture.md).
Тесты 417 (стабильно), ruff/import-linter/tsc/build зелёные.

## Ручной хвост (5 минут утром)

Хомлаб уснул 19:00 (расписание) до окончания К6: на CT нужно обновить
/usr/local/bin/learnos-deploy.sh до версии из proxmox-репо (0b9858c) — затем
первый же деплой сам поставит kb-git и learnos-backup.timer. Последние веб-коммиты
(ad6ad72) доедут таймером при пробуждении автоматически.
