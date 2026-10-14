---
name: telegram-bridge
description: "Двунаправленный мост между любой сессией opencode и Telegram-ботом: отправка текста, фото и файлов (send/send-photo/send-file) и чтение входящих из локальной SQLite-базы, которую наполняет постоянно работающий LaunchAgent-демон com.radmipa.telegram-bridge. Запускать, когда пользователь просит отправить или проверить Telegram («проверь телегу», «что нового в тг»), пришёл входящий файл/фото или нужно ответить в чат — по умолчанию через alias dmitry, другие чаты добавляются через bind. Агент только читает из базы (latest/unread/fetch); сам listen/live не запускать — это делает демон, второй поллер даст 409."
evolution: true
version: 1.0
status: active
created: 2026-08-12
---

# Telegram Bridge (global)

Bidirectional bridge between any opencode session and Telegram bot `@demon_ai_1984_bot`.

## What it does

- **Send** messages / files / results to Telegram.
- **Receive** incoming messages into a **SQLite store** (7-day retention), polled by an **always-on LaunchAgent**.
- Agent reads from the local DB only — **never** runs `listen`/`live` itself (the daemon does it; concurrent polls → Telegram 409 conflict).

## Architecture

```
message → Telegram → [LaunchAgent: telegram_bridge.py listen, always running]
                         ├─ downloads file immediately (before file_id expires)
                         └─ writes row to SQLite (~/.config/opencode/telegram.db), TTL 7 days
Agent reads locally:
   latest      ← newest message + file path (use this FIRST)
   unread      ← all unread
```
The LaunchAgent (`com.radmipa.telegram-bridge`) is KeepAlive + RunAtLoad → survives sleep/reboot. Telegram buffers updates ~24h, so after wake the daemon catches up — **nothing is lost**.

## Tool

```bash
python3 ~/.config/opencode/tools/telegram_bridge.py <command>
```

## Sending

```bash
# text
python3 ~/.config/opencode/tools/telegram_bridge.py send --to dmitry "Текст"
# from file (use for long / formatted messages)
python3 ~/.config/opencode/tools/telegram_bridge.py send --to dmitry --file /tmp/msg.txt
# stdin
echo "hi" | python3 ~/.config/opencode/tools/telegram_bridge.py send --to dmitry --stdin
# HTML formatting (Markdown breaks URLs with underscores — prefer HTML for links)
python3 ~/.config/opencode/tools/telegram_bridge.py send --to dmitry --parse-mode HTML --no-preview --file msg.html
# photo with in-chat preview (not a document)
python3 ~/.config/opencode/tools/telegram_bridge.py send-photo --to dmitry --caption "подпись" shot.jpg
```

After sending, report `message_id` and `chat_id` to the user.

## Sending files (any document)

`send` is for **text only**. To send an actual **file** (GPX, image, PDF, archive, log, etc.) as a downloadable document, use `send-file`:

```bash
# send a file as a document
python3 ~/.config/opencode/tools/telegram_bridge.py send-file --to dmitry /path/to/route.gpx
# with a caption
python3 ~/.config/opencode/tools/telegram_bridge.py send-file --to dmitry --caption "🚲 23 км gravel" /path/to/route.gpx
```

- Any file type works; MIME is guessed from the extension (falls back to `application/octet-stream`).
- The Telegram file name shown to the recipient is the file's basename.
- Limit ~20 MB (Bot API `getFile`/upload constraint).
- SOCKS5 proxy (`TELEGRAM_PROXY_URL`) is honored automatically, same as for `send`.
- Photos sent this way arrive as **documents** (no preview thumbnail). For a photo with preview, that's not supported here — send it as a document.
- `--caption` supports the same Unicode/emoji text as `send` (plain text only, no parse-mode).
- Like `send`, after success it prints `message_id` and `chat_id` — report them to the user.

Common use case: a finished GPX (e.g. from `velo-routes`) → `send-file` to the user, who then loads it onto their watch.

## Receiving — `latest` FIRST

The daemon is always running and writing to the DB. To read, use these **read-only** commands (they never conflict with the daemon):

```bash
# ★ самое свежее сообщение + путь к файлу — ВЫЗЫВАЙ ПЕРВЫМ
python3 ~/.config/opencode/tools/telegram_bridge.py latest
python3 ~/.config/opencode/tools/telegram_bridge.py latest --file   # гарантированно скачать файл
# все непрочитанные (из базы)
python3 ~/.config/opencode/tools/telegram_bridge.py unread --consume
# докачать файлы для записей без file_path
python3 ~/.config/opencode/tools/telegram_bridge.py fetch
```

`latest` output is self-describing — when a message has a file, the path is shown as `📎 /abs/path/to/file.jpg`. **Grab that path** and process it.

When the user says "проверь телегу / что нового в тг / есть входящие" **без имени чата**:
1. Run **`latest`** first — usually that's all they want (the newest thing).
2. If they want the whole queue — `unread` (все алиасы) и `pending`.
3. Reply in that chat via `send --to <alias>` — default alias is `dmitry`.

Имя чата/группы («проверь группу X», «inbox <alias>») → inbox ниже с `--to <alias>`.

## Aliases — любые люди и группы

Реестр: `~/.config/opencode/telegram_targets.json`. Один alias = один chat_id (личка или group/supergroup).

```bash
python3 ~/.config/opencode/tools/telegram_bridge.py targets
python3 ~/.config/opencode/tools/telegram_bridge.py pending
python3 ~/.config/opencode/tools/telegram_bridge.py bind --alias <имя> --chat-id <id>
python3 ~/.config/opencode/tools/telegram_bridge.py unread --to <имя>
python3 ~/.config/opencode/tools/telegram_bridge.py send --to <имя> --reply-to <message_id> "…"
python3 ~/.config/opencode/tools/telegram_bridge.py ack <update_id>
```

`--consume` без `--to` помечает **все** new. Одно сообщение — `ack`. `chat_id` не выдумывать.

Чат вне реестра → `pending` (и группы, и лички). Bind поднимает его в `new`.

**Bind нового чата:** бот в чате → человек пишет боту / reply / команду (Group Privacy ON режет болтовню группы до обращений) → `pending` → `bind --alias <имя>`. Без `--chat-id` bind берёт свежий pending.

## Двухуровневая архитектура (контракт с проектными скиллами)

**Этот скилл = HOW** (механика, без знания предметки): транспорт, реестр alias,
bind/pending/unread/ack, inbox-процесс, черновики, «отправь»-гейт.

**Проектный скилл = WHAT** (лежит в workspace проекта, не здесь): какие alias'ы
использует проект, голос сообщений, домен-роутинг обращений (куда нести разбор),
правила автоответа/мониторинга конкретных групп.

Проектный скилл фиксирует alias и домен у себя (реестр чатов — физический,
`telegram_targets.json`, но его наполнение диктует проект). Inbox-процесс живёт
здесь. Запрещено: упоминать конкретные проекты/группы в этом файле тащить их
механику в проектные скиллы.

## Inbox

1. `targets`. Нет нужного alias → `pending` → bind или «ждём первое сообщение».
2. `unread --to <alias>` (или `unread` для всех). `--consume` не ставить.
3. Каждое `#update_id` — обращение. Сервисные join/leave без текста — сразу `ack`.
4. Разобрать. Черновик человеку. В Telegram **не писать**, пока не сказали «отправь» / «шли».
5. После «отправь»: `send --to <alias> --reply-to <message_id>` (группы — с reply; личка — можно без). Потом `ack <update_id>`.

Черновик:

```
#<update_id> · @автор · alias=<имя> · msg=<message_id>
Суть: …
Черновик:
<текст>
Дальше: «отправь», если публикуем.
```

Без секретов, HTML для ссылок. `/loop 5m проверь телегу` — тикер шагов 1–4.

**Do NOT run `listen`/`live`** — the LaunchAgent daemon already polls; a second poller gets a 409. (Only for manual debugging after stopping the daemon.)

## Photos and files (auto-download)

When the user sends a photo or any file to the bot, `listen`/`live` **download it automatically** to `~/.config/opencode/telegram_files/`. The inbox record gets a `file_path` field.

- Photos: downloaded as `.jpg`, ready to analyze.
- Any document (PDF, image, archive, etc.): downloaded with its original name.
- Telegram bot API limit: files up to ~20 MB.

```bash
# If a message arrived but the file failed to download — retry
python3 ~/.config/opencode/tools/telegram_bridge.py fetch
```

### Analyzing a received photo
When `unread` shows a message with `📎 /path/to/file.jpg`, run the image-to-text skill on it:
```bash
# OCR (text on the photo) — auto picks OpenAI or z.ai
python3 ~/.config/opencode/tools/image_to_text.py <file_path> --stdout
# Full description of what's in the photo
python3 ~/.config/opencode/tools/image_to_text.py <file_path> --describe --stdout
# Custom question
python3 ~/.config/opencode/tools/image_to_text.py <file_path> --prompt "Что тут не так?" --stdout
```
Then send the analysis back to the user via `send`.

### Files download instantly
The LaunchAgent daemon downloads files **the moment a message arrives**, so the path is usually already in the DB by the time you run `latest`. If `latest` shows `📎 файл не скачан`, just run `latest --file` (or `fetch`) to retry. Files via `file_id` stay downloadable for ~1h after the message.

## Config (keys)

- Token: `MY_BOT_TG_demon_ai_1984_bot` (and proxy `TELEGRAM_PROXY_URL`) auto-loaded from
  `~/.config/opencode/.env` or the current project's `.env`.
- Aliases: `~/.config/opencode/telegram_targets.json` (or project `data/telegram_targets.json`).
- Never write the token into markdown / git.

## State files (global)

- **DB (messages + files, 7-day TTL):** `~/.config/opencode/telegram.db`
- Offset: `~/.config/opencode/telegram_state.json`
- Daemon log: `~/.config/opencode/telegram_listen.log`
- Downloaded files: `~/.config/opencode/telegram_files/`
- (Legacy JSONL inbox auto-migrated into the DB on first run.)

## Managing the daemon

```bash
launchctl load   ~/Library/LaunchAgents/com.radmipa.telegram-bridge.plist   # старт
launchctl unload ~/Library/LaunchAgents/com.radmipa.telegram-bridge.plist   # стоп
tail -f ~/.config/opencode/telegram_listen.log                              # лог
```
The plist source lives in the repo: `radmipa-skills/launchagent/com.radmipa.telegram-bridge.plist`.

## Notes

- `Markdown` parse-mode corrupts URLs containing `_`; use `HTML` with inline `<a href>` for links.
- Telegram stores undelivered updates ~24h; the offset ensures nothing is read twice.
- Agent reads only (`latest`/`unread`/`fetch`); the daemon is the single poller.
- Works in any project — no project-specific setup required.

---

## 🔁 Эволюция этого скилла (не удалять — протокол жизненного цикла)

- **Сработал** → `python3 ~/my_dev/radmipa-skills/sync.py used telegram-bridge`
- **Наврал/сломался** → почини прямо сейчас в этой же сессии, затем
  `sync.py used telegram-bridge --fail "что случилось"`, подними `version` на 0.1
- **Паттерн устарел** → предложи архивацию в draft-заметке куратору
- Куратор (ночной аудит) сверяет этот блок с usage-логом и чинит мелочи сам
