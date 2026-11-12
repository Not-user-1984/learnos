# B-011 · отчёт исполнителя

Раунд 1 (§1–6 плана) — см. «Факты раунда 1» ниже; основной объём закоммичен в main
(F: f6cc90c, 03fbe08, 0b2e746, 8d84183, c08058e, 69945dd, b074a6d). Раунд 2 —
фиксы пяти находок ревью от 2026-11-12.

## Раунд 2 · фиксы находок ревью

### 1 [высокая] /repo снова read-only
- `docker-compose.yml`: `./:/repo:ro` + отдельный rw-маунт `./.git:/repo/.git`
  (push/worktree пишут только в `.git`; чекаут воркдрив — в `data/git-worktrees` через маунт `/data`).
  Маски `.env` и `repo-mask/data` остались.
- Прод (CT 132, после деплоя cf42d26): см. «Смоук на проде».

### 2 [средняя] Креды в ошибках git push маскируются
- `server/app/modules/proposals/service.py`: `_mask_creds()` — URL-креды
  (`user:pass@host`, `token@host`), `token=…`/`Authorization: …`/`password=…`,
  префиксы `ghp_/gho_/ghu_/ghs_/ghr_/github_pat_`. Применяется к хвосту stderr
  до попадания в текст ValidationFailed.
- Тест: `test_push_error_masks_credentials` (маски напрямую + через decide).

### 3 [низкая] Причина неудачи PR возвращается в ответ
- `_pr_via_api` → `tuple[url | None, причина | None]`: нет токена / origin не GitHub /
  401-403 / другой код / 422 без ссылки / сеть-прокси. `_accept_branch` отдаёт `pr_note`,
  UI (`web/src/app/proposals/page.tsx`) показывает тост с причиной рядом с PR/compare.
- Тест: `test_pr_via_api_returns_reason`.

### 4 [низкая] Этот report.md
- Написан, включая прод-факты обоих раундов.

### 5 [низкая] Dev-оверлей «2 Issues» на /chat
Воспроизведено на локальном стенде (next dev :3000, viewport 375×812, /chat/<разговор с карточками>).
Оба issue — одна первопричина:
- **Hydration text mismatch** в `theme-toggle.tsx`: на сервере `resolvedTheme` нет → глиф
  `dark_mode`, на клиенте первый рендер уже знает тему из localStorage (напр. `parchment`
  → `auto_stories`), текст `<span>` не совпадает → React перерождает поддерево.
- Следом **«Encountered a script tag…»** — при перерождении создаётся `<script>` next-themes
  (React 19.2 предупреждает о скриптах в клиент-рендере).
- Фикс: `useSyncExternalStore`-гейт `useMounted()` (идиома кодовой базы, без setState-в-эффекте,
  который запрещает eslint-правило React Compiler). Иконка до монтирования детерминирована.
- Бонус: `next.config.ts` — бессрочный immutable-кэш `/_next/static/*` только при
  `NODE_ENV=production` (устраняет дев-варнинг «Custom Cache-Control headers detected»,
  в деве статику кэширует сам Next; BUG-004 не затронут — `no-cache` документов остался).
- Проверка: оверлей 0 issues, клик переключателя меняет класс `html` (parchment → light),
  `localStorage.theme` обновляется. Решающий прогон — **свежий браузерный профиль** (без
  localStorage/SW/старых вкладок), холодный `next dev`: ошибки консоли = 0 на `/chat`,
  `/chat/<uid>` (карточки), `/today`; прод `192.168.0.132:3000/chat` — тоже 0. Ошибки в логе
  дев-сервера во время сессии — мусор от постоянного профиля пилота (рестарт старой вкладки
  с бандлом до фикса поверх свежего HTML + service worker-кэш), на свежем профиле не
  воспроизводятся (счётчик «Hydration failed» в логе сервера не растёт).

## Изменённые файлы (раунд 2)
- `docker-compose.yml` — маунты /repo ro + .git rw
- `server/app/modules/proposals/service.py` — _mask_creds, pr_note
- `server/tests/unit/self_improve_test.py` — +2 теста, правка _pr_via_api-контракта
- `web/src/app/proposals/page.tsx` — тост с pr_note
- `web/src/components/theme-toggle.tsx` — useMounted-гейт гидратации
- `web/next.config.ts` — immutable-кэш статики только в проде

Коммиты: 84df709 (fix1), 1131441 (fix2-3), cf42d26 (fix5) — запушены в main (GitHub + GitVerse).

## Проверки (раунд 2)
- `cd server`: ruff ✅ · ruff format ✅ · lint-imports 7/7 ✅ · pytest 506 ✅
- `cd web`: gen:api ✅ · lint ✅ · tsc --noEmit ✅ · build ✅
- Dev-оверлей и консоль браузера — чистые (см. п.5)

## Факты раунда 1 (прод, 2026-11-12)
- **§3 смоук accept**: ветка `agent/b011-accept-smoke` подготовлена (`git_prepare_change`),
  accept → push + PR созданы, PR закрыт и ветка удалена вручную через `gh` (ревью это подтвердило).
- **§4 эмбеддинги**: у z.ai модели эмбеддингов нет → OpenAI `text-embedding-3-small` (1536),
  ключ `LEARNOS_OPENAI_API_KEY`/`OPENAI_API_KEY`. OpenAI блокирует регион CT прямым
  запросом (403 unsupported country) → флаг `use_proxy`: запросы провайдера эмбеддингов идут
  через socks5 из настроек связи (xray-sidecar). Прод: `embed_configured=true`,
  reindex --embeddings → 11 элементов, `embed_pending_blocks=0`.
- **Гибридный поиск на проде**: `mode=hybrid` возвращает векторные совпадения
  (`matched_by: vector`) по главам источника — проверено запросами «архитектура»,
  «архитектура сервисов» и др. (ответ: поле `chunks`).
- **§2 задачи на проде**: `create_task_file` при read-only git-дереве уходит в
  `data/proposals/tasks/T-AGENT-<дата>-<slug>.md`, «Предложения» читают обе папки,
  accept отдаёт текст для копирования (тесты + смоук round-1).

## Смоук на проде (раунд 2 — после деплоя cf42d26, CT 132)
- Маунты контейнера: `/opt/learnos → /repo [ro]`, `/opt/learnos/.git → /repo/.git [rw]`,
  маски `.env`/`repo-mask/data` на месте.
- `docker exec … touch /repo/x` → «Read-only file system» ✅; `touch /repo/.git/probe` → ok ✅;
  `touch /data/probe` → ok ✅. `GET /api/health` → ok, `embed_configured=true`, 11 в индексе.
- Полный цикл ветки: MCP `git_prepare_change` → ветка `agent/b011-ro-smoke` (коммит 402fba1,
  проверки зелёные в worktree `/data/git-worktrees` — запись шла в rw-`.git`, чекаут в rw-`/data`);
  REST `decide accepted` → `pushed=true`, PR создан REST-ом
  (github.com/Not-user-1984/learnos/pull/2), `pr_note=null` (нет причины-ошибки).
  Уборка: PR #2 закрыт, remote-ветка удалена (`gh pr close --delete-branch`), worktree и
  локальная ветка на проде удалены, запись журнала снята. Бюджет дня: 2 из 3 использовано.

## Отклонения и решения
- Ревью предлагало маскировать строки с «token/Authorization» целиком — сделано точнее:
  маскируется значение (строка остаётся читаемой для диагностики).
- `pve.py exec` ломает кавычки на ssh-хопе mac→proxmox→pct: команды с редиректами
  молча выполняются не в CT. Для смоука использован прямой ssh-вызов с корректной
  вложенностью кавычек (двойные снаружи, одинарные в bash -c). Инфра-баг вне этого репо,
  записан здесь как предупреждение будущим задачам.
- Скриншоты 375px из раунда 1 не пере-делал (вёрстка не менялась; консольные проверки — текстом).

## Вопросы архитектору
- Нет блокеров.
