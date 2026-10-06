# LearnOS — архитектура (v1)

Дополнение к [PLAN.md](PLAN.md). Здесь — технические детали.

---

## 1. Компоненты

```
                    ┌─────────────────────────────────────────────┐
                    │                 Хомлаб (Proxmox)            │
                    │                                             │
  мак (opencode) ───┤  MCP (streamable HTTP)                      │
                    │        │                                    │
  мобилка ──────────┤  Web UI + REST/WS      learnos (FastAPI)    │
  (Tailscale/       │        │                  │        │        │
   NPM)             │        │               SQLite   files      │
                    │        │               (state)  (books,    │
                    │     LLM API                      chunks,   │
                    │   (z.ai / OpenAI-compat)        kb/*.md)   │
                    │                                             │
                    │   Ингест: pdf-splitter / yt-dlp / whisper   │
                    │   Практика: LXC-sandbox (+ code-server)     │
                    │   via Proxmox API (pve.py логика)           │
                    └─────────────────────────────────────────────┘
```

Один процесс/стек: `learnos` = API + MCP + ингест + скиллы + UI-статика. UI — отдельный фронт (Next.js), собирается в образ.

Monorepo:

```
learnos/
├── server/              # FastAPI: REST + MCP + ингест + скиллы
│   ├── app/
│   └── skills/          # drop-in скиллы: <name>/SKILL.md + run.py
├── web/                 # Next.js + TS strict — UI базы знаний
├── kb/                  # блоки знаний: markdown + frontmatter (в git)
├── data/                # SQLite, книги, чанки, транскрипты (не в git)
├── PLAN.md / ARCHITECTURE.md / AGENTS.md
```

### Три лица системы

1. **MCP-лицо** — любой агент (opencode, OpenClaw, облачные обвязки) работает одинаковыми MCP-инструментами. Harness — всегда клиент, не фундамент.
2. **Человеческое лицо** — веб-UI: рендерер над `kb/*.md` (карточки, mermaid, граф).
3. **Лицо агента** (фаза 2) — сервис сам зовёт LLM (OpenAI-совместимый API) и ведёт сессии из веб-чата.

Все три лица ходят в одно ядро и делят одни инструменты — в т.ч. скиллы.

## 2. Модель данных (SQLite)

```sql
courses   (id, topic, status, plan_json, created_at)
sources   (id, course_id, kind: book|video|web|course, title, url,
           local_path, status: found|chosen|downloaded|processed, meta_json)
chapters  (id, source_id, idx, title, path, tokens_est, summary)
sessions  (id, course_id, idx, status, state, started_at, ended_at,
           transcript_json)   -- вся беседа: теория, вопросы, мои ответы
blocks    (id, course_id, session_id, title, path, tags_json,
           sources_json, review_json, created_at)
sandboxes (id, course_id, vmid, code_server_url, status, created_at)
```

Блок KB — markdown-файл + frontmatter, сервис его генерит и владеет:

```markdown
---
id: blk_a1b2
course: kubernetes
title: Сетевая модель подов
tags: [net, k8s]
sources: [book:k8s-in-action#ch3, yt:abc123]
review: {ease: 2.5, interval: 1, due: 2026-10-08}
---
## Тезисы
- ...

## Как я это понял
- мой пример: ...

## Схема
mermaid-диаграмма

## Связи
- [[blk_c3d4]]
```

## 3. Стейт-машина сессии

`idle → theory(i) → check(i) → theory(i+1) ... → practice → debrief → done(block committed)`

- Сессию **водит LLM-агент** (opencode через MCP, или встроенный агент из веб-чата).
- Сервис — источник истины: хранит стейт, валидирует переходы, пишет транскрипт.
- `check` — фейнман-этап: агент обязан задать ≥N вопросов на блок и получить мои ответы своими словами; слабые ответы → пометки «дозакрепить» попадают в блок и в будущие review.
- `practice` — задачи из источника (если книга — упражнения; иначе LLM их придумывает под песочницу/мак).
- `done` — сервис из транскрипта генерит блок (LLM-вызов с жёсткой схемой: тезисы ≤7, мои примеры, mermaid, связи) и коммитит в KB. До этого блока не существует.

## 4. MCP-инструменты (v1)

**Ингест:**
- `research_sources(topic)` → кандидаты (web-search логика)
- `add_source(kind, url|path)` / `download_source(id)`
- `process_source(id)` — PDF: извлечь TOC → главы → чанки-файлы (+ краткое summary на главу); видео: транскрипт
- `read_chapter(source_id, chapter)` — вернуть текст главы (агент читает по главам, весь PDF в контекст не грузим)
- `search_chunks(query)` — семантический поиск по чанкам (sqlite-vec)

**Курс:**
- `create_course(topic, source_ids)` → план (какие главы/видео в какие сессии, ~40 мин каждая)
- `get_course(id)` / `next_session(course_id)`

**Сессия:**
- `start_session(course_id)` / `get_session_state()`
- `advance(event)` — теория/вопрос/ответ/практика; всё логируется
- `finish_session()` → генерация и коммит блока

**База знаний:**
- `search_kb(query)` / `get_block(id)` / `list_blocks(course?)`

**Практика:**
- `create_sandbox(course_id)` → клон LXC-шаблона, code-server URL, креды
- `sandbox_exec(id, cmd)` / `destroy_sandbox(id)`

### Drop-in скиллы

Скилл = папка `server/skills/<name>/`:

- `SKILL.md` — frontmatter (`name`, `description`, `params`) + инструкции для агента (формат совместим с opencode-скиллами — портирование копированием)
- `run.py` — entrypoint, вызывается сервисом (не агентом напрямую)

Сервис сканирует каталог на старте и регистрирует каждый скилл как MCP-инструмент + внутренний вызов. Закинул папку — инструмент появился во всех каналах (opencode MCP / веб-чат / встроенный агент). Первые портируемые: `youtube-to-summary` (yt-dlp субтитры, Whisper-fallback, автодетект SOCKS5), `web-search` (fallback-цепочка движков), `book-splitter`.

## 5. Веб-UI базы знаний

Стек: **Next.js + TypeScript strict + shadcn/ui + React Flow (граф) + Mermaid + react-markdown**.

- Типы API генерируются из OpenAPI FastAPI (`openapi-typescript`), валидация — zod. Меньше ручных типов → LLM меньше косячит при кодогенерации.
- UI пишем с фазы 0 (каркас) и наращиваем параллельно петле: read-only карточки блоков уже в фазе 1; граф, прогресс, чат — фаза 2.
- «Obsidian под нас»: `kb/*.md` — источник истины (git-бэкап, портабельность), UI — наш рендерер с семантикой блоков (закрыт/пройден/дозакрепить, связи, SM-2).

Экраны:
1. **Карта курса** — прогресс, дерево сессий, следующий шаг
2. **Блок-карточка** — раскрывается: тезисы → мои примеры → схема → связи → источник и дата сессии
3. **Граф знаний** — узлы-блоки, рёбра-связи, цвет по курсу/свежести, zoom/click → карточка
4. **Сессия-чат** — разговор с встроенным агентом (то же, что MCP-сессия, только из браузера/мобилки)
5. **Review** — «расскажи по памяти» по подзревшим блокам (SM-2)

Почему свой: семантика «блок виден только после сессии», раскрытие карточек по нашей схеме, граф — ядро, а не плагин. Markdown под капотом → в любой момент уносим в Obsidian/Quartz, если что.

## 6. PDF-пайплайн (главное — не захламлять контекст)

1. `pymupdf`: вытянуть TOC (закладки). Нет закладок → эвристика по заголовкам (размер шрифта) + LLM-глаз на первые страницы.
2. Главы → отдельные `.md` файлы (`pandoc`-подобная вычитка: код-блоки сохраняем).
3. На каждый чанк — эмбеддинг (sqlite-vec, модель локально или API) + короткое summary.
4. Агент работает так: TOC → выбрал главы под цель → `read_chapter` по одной → вопросы мне.
5. Большие главы режутся на «порции» ~6–8k токенов с перекрытием.

## 7. Практика-песочницы

- Шаблон: LXC `learn-sandbox-tpl` (Ubuntu + docker + python + code-server + ttyd), docker-image или pct-шаблон.
- `create_sandbox` → клон шаблона через Proxmox API (токен, уже есть практика в `pve.py`), статический IP из пула, NPM/Tailscale-роут только для меня.
- С мобилки: code-server (VS Code в браузере) или ttyd (голый терминал) — практика без мака.
- Жизненный цикл: sandbox на курс, уничтожение по завершении курса; снапшот перед «опасной» практикой.
- Мак-альтернатива: практические задачи локально (opencode сам создаёт файлы/запускает команды) — для фазы 1.
- GPU-темы: генерим `.ipynb`, пользователь гоняет в Colab (при желании — Colab подключить как UI к local runtime на песочнице).

## 8. Хостинг и доступ

- Docker-compose на хомлабе (host-docker или отдельный LXC; данные `/SSD256/learnos`, бэкап KB-папки в приватный git).
- NPM-роут `learn.not-user-1984.duckdns.org` + запись в `services.json` (`sync-all` подхватит Dashy/health).
- С мобилки — через Tailscale (уже в tailnet), публично не светим; MCP — по bearer-токену.
- Секреты: LLM-ключ и Proxmox-токен — через `sec` на маке → env при деплое, в git не попадают.
- ⚠️ Сон хомлаба 19:00–08:30 — решить (PLAN.md §6.3): сдвиг сна / облачная VM / фаза-1 на маке.

## 9. Безопасность

- MCP/REST — токен; UI — за Tailscale (без публичного Funnel).
- В git — только `kb/*.md`, метаданные и код; книги/транскрипты — только на сервере.
- `sandbox_exec` — только внутри песочницы курса, не в хост-систему.
