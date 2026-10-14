#!/usr/bin/env python3
"""Глобальный Telegram-мост для opencode (send + receive в одном скрипте).

Самодостаточный: токен/прокси ищутся в нескольких .env (глобальный → проектный),
алиасы — в ~/.config/opencode/telegram_targets.json или ./data/telegram_targets.json.
Inbox/state хранятся в ~/.config/opencode/.

КОМАНДЫ
-------
  verify                         — проверить токен (getMe)
  send --to <alias|chat_id> TXT  — отправить сообщение
  send --to dmitry --file f.txt  — из файла (текст сообщения из файла)
  echo TXT | send --to dmitry --stdin
  send-file --to dmitry f.gpx    — отправить ЛЮБОЙ файл документом
  send-file --to dmitry f.png --caption "подпись"
  send-photo --to dmitry shot.png --caption "подпись" — фото с превью (не документ)
  latest [--file] [--to alias]   — ★ последнее сообщение (+ файл), read-only
  unread [--consume] [--to alias] — непрочитанные (опц. один чат)
  pending                        — чаты вне алиасов (группы и лички)
  bind --alias NAME [--chat-id ID] — привязать любой чат (без --chat-id — свежий pending)
  targets                        — список алиасов
  ack UPDATE_ID                  — пометить одно сообщение прочитанным
  fetch                          — докачать файлы для записей без file_path
  listen [--once]                — вечный poller → БД (запускать как LaunchAgent)
  live [СЕК]                     — живое окно на СЕК секунд (по умолч. 180)

ПРИМЕРЫ
-------
  python3 ~/.config/opencode/tools/telegram_bridge.py send --to dmitry "Привет"
  python3 ~/.config/opencode/tools/telegram_bridge.py unread --consume
  nohup python3 ~/.config/opencode/tools/telegram_bridge.py listen > /tmp/tg.log 2>&1 &
"""
import argparse
import http.client
import json
import mimetypes
import os
import socket
import sqlite3
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta
from pathlib import Path

HOME = Path.home()
CFG_DIR = HOME / ".config" / "opencode"
ENV_CANDIDATES = [CFG_DIR / ".env", Path.cwd() / ".env", Path.cwd() / "data" / ".env"]
TARGETS_CANDIDATES = [CFG_DIR / "telegram_targets.json", Path.cwd() / "data" / "telegram_targets.json"]
INBOX = CFG_DIR / "telegram_inbox.jsonl"
STATE = CFG_DIR / "telegram_state.json"
FILES_DIR = CFG_DIR / "telegram_files"
DB_PATH = CFG_DIR / "telegram.db"
RETENTION_DAYS = 7
API_BASE = "https://api.telegram.org"
DEFAULT_ALIAS = "dmitry"
MAX_FILE_BYTES = 20 * 1024 * 1024  # Telegram bot getFile limit ~20MB


class TgError(RuntimeError):
    pass


# ---------- env / secrets ----------

def _parse_val(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in {"'", '"'}:
        return v[1:-1]
    return v


def load_env():
    for path in ENV_CANDIDATES:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, _, v = s.partition("=")
            k = k.strip()
            if k and k not in os.environ:
                os.environ[k] = _parse_val(v)


def get_token():
    t = (
        os.getenv("MY_BOT_TG_demon_ai_1984_bot") or os.getenv("MY_BOT_TG_test_aiHunter_bot")
        or os.getenv("TELEGRAM_BOT_TOKEN")
        or os.getenv("TELEGRAM_TOKEN")
    )
    if not t:
        raise TgError("MY_BOT_TG_test_aiHunter_bot не задан. Положи в ~/.config/opencode/.env или проектный .env")
    return t.strip()


def get_proxy():
    return os.getenv("TELEGRAM_PROXY_URL")


def load_targets():
    for path in TARGETS_CANDIDATES:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


def targets_path():
    for path in TARGETS_CANDIDATES:
        if path.exists():
            return path
    return CFG_DIR / "telegram_targets.json"


def _target_chat_id(item):
    if isinstance(item, dict):
        return item.get("chat_id")
    return item


def allowed_chat_ids():
    ids = set()
    for v in load_targets().values():
        cid = _target_chat_id(v)
        if cid is None or cid == "":
            continue
        ids.add(str(cid))
    return ids


def resolve_chat(target):
    targets = load_targets()
    if target in targets:
        cid = _target_chat_id(targets[target])
        if cid is None or cid == "":
            raise TgError(f"алиас {target!r} ещё не привязан (нет chat_id). Сначала bind")
        return cid
    return target


def first_chat_id():
    for cid in allowed_chat_ids():
        return cid
    return None


def save_target(alias, chat_id, chat_type=None, title=None):
    path = targets_path()
    data = load_targets()
    item = data.get(alias, {})
    if not isinstance(item, dict):
        item = {"chat_id": item}
    raw = str(chat_id)
    item["chat_id"] = int(raw) if raw.lstrip("-").isdigit() else chat_id
    if chat_type:
        item["type"] = chat_type
    if title:
        item["title"] = title
    data[alias] = item
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


# ---------- network (SOCKS5 support) ----------

def _read_exact(sock, size):
    buf = b""
    while len(buf) < size:
        chunk = sock.recv(size - len(buf))
        if not chunk:
            raise TgError("Proxy closed connection")
        buf += chunk
    return buf


def socks5_connect(proxy_url, host, port, timeout):
    pr = urllib.parse.urlsplit(proxy_url)
    if pr.scheme not in {"socks5", "socks5h"}:
        raise TgError("Only socks5:// proxy supported")
    user = urllib.parse.unquote(pr.username or "")
    pw = urllib.parse.unquote(pr.password or "")
    methods = [0x00] + ([0x02] if (user or pw) else [])
    sock = socket.create_connection((pr.hostname, pr.port), timeout=timeout)
    try:
        sock.settimeout(timeout)
        sock.sendall(bytes([0x05, len(methods), *methods]))
        v, m = _read_exact(sock, 2)
        if v != 0x05 or m == 0xFF:
            raise TgError("SOCKS5 auth failed")
        if m == 0x02:
            ub, pb = user.encode(), pw.encode()
            sock.sendall(bytes([0x01, len(ub)]) + ub + bytes([len(pb)]) + pb)
            if _read_exact(sock, 2)[1] != 0x00:
                raise TgError("SOCKS5 user/pass rejected")
        hb = host.encode("idna")
        sock.sendall(bytes([0x05, 0x01, 0x00, 0x03, len(hb)]) + hb + int(port).to_bytes(2, "big"))
        resp = _read_exact(sock, 4)
        if resp[1] != 0x00:
            raise TgError(f"SOCKS5 connect failed code {resp[1]}")
        atyp = resp[3]
        if atyp == 0x01:
            _read_exact(sock, 4)
        elif atyp == 0x03:
            _read_exact(sock, _read_exact(sock, 1)[0])
        elif atyp == 0x06:
            _read_exact(sock, 16)
        _read_exact(sock, 2)
        return sock
    except Exception:
        sock.close()
        raise


class SocksConn(http.client.HTTPSConnection):
    def __init__(self, host, port, proxy_url, timeout, context):
        super().__init__(host, port=port, timeout=timeout, context=context)
        self.proxy_url = proxy_url

    def connect(self):
        self.sock = self._context.wrap_socket(
            socks5_connect(self.proxy_url, self.host, self.port, self.timeout),
            server_hostname=self.host,
        )


def request_json(method, payload=None, timeout=30):
    token = get_token()
    proxy = get_proxy()
    url = f"{API_BASE}/bot{token}/{method}"
    headers = {"User-Agent": "telegram-bridge/1.0"}
    data = None
    if payload is not None:
        data = urllib.parse.urlencode(payload).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    insecure = True  # tolerate local proxies / cert issues

    try:
        if proxy:
            parsed = urllib.parse.urlsplit(url)
            path = urllib.parse.urlunsplit(("", "", parsed.path, parsed.query, ""))
            ctx = ssl._create_unverified_context()
            conn = SocksConn(parsed.hostname, parsed.port or 443, proxy, timeout, ctx)
            try:
                conn.request("POST" if data else "GET", path, body=data, headers=headers)
                r = conn.getresponse()
                body = r.read().decode("utf-8", "replace")
                if r.status >= 400:
                    raise TgError(f"HTTP {r.status}: {body}")
            finally:
                conn.close()
        else:
            ctx = ssl._create_unverified_context() if insecure else None
            req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                body = r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise TgError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')}") from e
    except urllib.error.URLError as e:
        raise TgError(f"network: {e.reason}") from e

    parsed = json.loads(body)
    if not parsed.get("ok"):
        raise TgError(f"{parsed.get('error_code')}: {parsed.get('description')}")
    return parsed["result"]


# ---------- file download ----------

def _http_get_bytes(url, timeout=60):
    """Скачать байты по https (напрямую или через SOCKS5-прокси)."""
    proxy = get_proxy()
    if proxy:
        p = urllib.parse.urlsplit(url)
        path = urllib.parse.urlunsplit(("", "", p.path, p.query, ""))
        ctx = ssl._create_unverified_context()
        conn = SocksConn(p.hostname, p.port or 443, proxy, timeout, ctx)
        try:
            conn.request("GET", path)
            r = conn.getresponse()
            data = r.read()
            if r.status >= 400:
                raise TgError(f"HTTP {r.status} при скачивании файла")
            return data
        finally:
            conn.close()
    req = urllib.request.Request(url, headers={"User-Agent": "telegram-bridge/1.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=ssl._create_unverified_context()) as r:
        return r.read()


def save_tg_file(file_id, suggested_name):
    """Скачать файл через getFile + file API. Возвращает путь или None."""
    info = request_json("getFile", payload={"file_id": file_id}, timeout=30)
    fp = info.get("file_path")
    size = info.get("file_size", 0)
    if size and size > MAX_FILE_BYTES:
        print(f"[file] слишком большой: {size} байт (лимит {MAX_FILE_BYTES})", file=sys.stderr)
        return None
    if not fp:
        return None
    url = f"{API_BASE}/file/bot{get_token()}/{fp}"
    data = _http_get_bytes(url)
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = suggested_name or fp.replace("/", "_")
    # префикс времени чтобы не конфликтовали одинаковые имена
    dest = FILES_DIR / f"{ts}_{name}"
    dest.write_bytes(data)
    return str(dest)


# ---------- send ----------

def read_text(args):
    parts = []
    if args.message:
        parts.append(args.message)
    if args.file:
        parts.append(Path(args.file).read_text(encoding="utf-8"))
    if args.stdin:
        parts.append(sys.stdin.read())
    text = "\n".join(p.rstrip("\n") for p in parts if p).strip()
    if not text:
        raise TgError("Пустое сообщение")
    return text


def cmd_send(args):
    target = args.to or DEFAULT_ALIAS
    payload = {"chat_id": resolve_chat(target), "text": read_text(args),
               "disable_web_page_preview": "true" if args.no_preview else "false"}
    if args.parse_mode:
        payload["parse_mode"] = args.parse_mode
    if getattr(args, "reply_to", None):
        payload["reply_to_message_id"] = str(args.reply_to)
    res = request_json("sendMessage", payload)
    print(f"Sent message_id={res.get('message_id')} chat_id={res.get('chat', {}).get('id')}")


def _http_post_bytes(url, body, headers, timeout=60):
    """POST сырых байт (multipart) напрямую или через SOCKS5-прокси. Возвращает текст ответа."""
    proxy = get_proxy()
    insecure = True
    try:
        if proxy:
            p = urllib.parse.urlsplit(url)
            pathurl = urllib.parse.urlunsplit(("", "", p.path, p.query, ""))
            ctx = ssl._create_unverified_context()
            conn = SocksConn(p.hostname, p.port or 443, proxy, timeout, ctx)
            try:
                conn.request("POST", pathurl, body=body, headers=headers)
                r = conn.getresponse()
                data = r.read().decode("utf-8", "replace")
                if r.status >= 400:
                    raise TgError(f"HTTP {r.status}: {data}")
            finally:
                conn.close()
        else:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            ctx = ssl._create_unverified_context() if insecure else None
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                data = r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise TgError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')}") from e
    except urllib.error.URLError as e:
        raise TgError(f"network: {e.reason}") from e
    return data


def _send_multipart(chat_id, file_path, *, api_method, file_field, caption=None, parse_mode=None, timeout=120):
    path = Path(file_path)
    if not path.exists():
        raise TgError(f"файл не найден: {file_path}")
    data = path.read_bytes()
    if len(data) > MAX_FILE_BYTES:
        raise TgError(f"файл слишком большой: {len(data)} байт (лимит {MAX_FILE_BYTES})")

    token = get_token()
    boundary = "----tgbridge" + uuid.uuid4().hex

    def field(name, value):
        head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n").encode("utf-8")
        return head + value.encode("utf-8") + b"\r\n"

    def file_part(name, filename, blob):
        ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\n"
                f"Content-Type: {ctype}\r\n\r\n").encode("utf-8")
        return head + blob + b"\r\n"

    body = field("chat_id", str(chat_id))
    if caption:
        body += field("caption", caption)
    if parse_mode:
        body += field("parse_mode", parse_mode)
    body += file_part(file_field, path.name, data)
    body += f"--{boundary}--\r\n".encode("utf-8")

    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
        "User-Agent": "telegram-bridge/1.0",
    }
    url = f"{API_BASE}/bot{token}/{api_method}"
    parsed = json.loads(_http_post_bytes(url, body, headers, timeout=timeout))
    if not parsed.get("ok"):
        raise TgError(f"{parsed.get('error_code')}: {parsed.get('description')}")
    return parsed["result"]


def send_document(chat_id, file_path, caption=None, timeout=120):
    """Отправить произвольный файл документом (sendDocument, multipart)."""
    return _send_multipart(chat_id, file_path, api_method="sendDocument",
                           file_field="document", caption=caption, timeout=timeout)


def send_photo(chat_id, file_path, caption=None, parse_mode=None, timeout=120):
    """Отправить картинку как фото с превью (sendPhoto)."""
    return _send_multipart(chat_id, file_path, api_method="sendPhoto",
                           file_field="photo", caption=caption, parse_mode=parse_mode,
                           timeout=timeout)


def cmd_send_file(args):
    target = args.to or DEFAULT_ALIAS
    res = send_document(resolve_chat(target), args.path, caption=args.caption)
    doc = res.get("document", {})
    print(f"Sent document message_id={res.get('message_id')} chat_id={res.get('chat', {}).get('id')} "
          f"file={doc.get('file_name')} ({doc.get('file_size')} байт)")


def cmd_send_photo(args):
    target = args.to or DEFAULT_ALIAS
    res = send_photo(resolve_chat(target), args.path, caption=args.caption,
                     parse_mode=getattr(args, "parse_mode", None))
    print(f"Sent photo message_id={res.get('message_id')} chat_id={res.get('chat', {}).get('id')}")


def cmd_verify(args):
    bot = request_json("getMe")
    print(f"OK: @{bot.get('username')} (id={bot.get('id')})")


# ---------- receive ----------

def load_offset():
    if STATE.exists():
        return json.loads(STATE.read_text()).get("offset")
    return None


def save_offset(offset):
    STATE.write_text(json.dumps({"offset": offset}))


def append_inbox(rec):
    """Legacy JSONL — используется только как источник для однократной миграции в базу."""
    INBOX.parent.mkdir(parents=True, exist_ok=True)
    with INBOX.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ---------- sqlite store ----------

def db_conn():
    CFG_DIR.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH), timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=5000")
    return c


def db_init():
    with db_conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS messages(
            update_id INTEGER PRIMARY KEY,
            ts TEXT,
            from_user TEXT,
            chat_id TEXT,
            text TEXT,
            file_id TEXT,
            file_name TEXT,
            file_type TEXT,
            file_path TEXT,
            status TEXT DEFAULT 'new')""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(ts)")
    _db_migrate_columns()


def _db_migrate_columns():
    extras = (
        ("message_id", "TEXT"),
        ("chat_title", "TEXT"),
        ("chat_type", "TEXT"),
        ("from_username", "TEXT"),
        ("reply_to", "TEXT"),
    )
    with db_conn() as c:
        cols = {r[1] for r in c.execute("PRAGMA table_info(messages)")}
        for col, typ in extras:
            if col not in cols:
                c.execute(f"ALTER TABLE messages ADD COLUMN {col} {typ}")


def db_insert(rec):
    db_init()
    with db_conn() as c:
        c.execute("""INSERT OR REPLACE INTO messages
            (update_id, ts, from_user, chat_id, text, file_id, file_name, file_type, file_path, status,
             message_id, chat_title, chat_type, from_username, reply_to)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (rec.get("update_id"), rec.get("ts"), rec.get("from"), str(rec.get("chat_id") or ""),
                   rec.get("text") or "", rec.get("file_id"), rec.get("file_name"), rec.get("file_type"),
                   rec.get("file_path"), rec.get("status", "new"),
                   str(rec.get("message_id") or ""), rec.get("chat_title") or "",
                   rec.get("chat_type") or "", rec.get("from_username") or "",
                   str(rec.get("reply_to") or "")))


def _db_set_file(update_id, file_path):
    with db_conn() as c:
        c.execute("UPDATE messages SET file_path=? WHERE update_id=?", (file_path, update_id))


def db_set_status(update_id, status):
    with db_conn() as c:
        c.execute("UPDATE messages SET status=? WHERE update_id=?", (status, update_id))


def db_prune(days=RETENTION_DAYS):
    """Удалить сообщения старше days. Возвращает сколько удалил."""
    db_init()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    with db_conn() as c:
        n = c.execute("DELETE FROM messages WHERE ts < ?", (cutoff,)).rowcount
    return n


def db_migrate_jsonl():
    """Разово перенести старый JSONL-инбокс в базу. INBOX переименовывается."""
    if not INBOX.exists():
        return 0
    db_init()
    n = 0
    for line in INBOX.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("update_id") is None:
            continue
        db_insert(r)
        n += 1
    if n:
        INBOX.rename(str(INBOX) + ".migrated")
        print(f"[migrate] перенесено из JSONL в базу: {n} (старый файл → .migrated)", flush=True)
    return n


def extract(update):
    msg = update.get("message") or update.get("channel_post") or update.get("edited_message")
    if not msg:
        return None
    chat = msg.get("chat") or {}
    parts = []
    file_id = None
    file_name = None
    file_type = None
    if msg.get("text"):
        parts.append(msg["text"])
    if msg.get("caption"):
        parts.append(msg["caption"])
    if msg.get("photo"):
        # самый большой размер — последний в массиве
        biggest = msg["photo"][-1]
        file_id = biggest.get("file_id")
        file_type = "photo"
        parts.append("[фото]")
    if msg.get("document"):
        file_id = msg["document"].get("file_id")
        file_name = msg["document"].get("file_name")
        file_type = "document"
        parts.append(f"[файл: {file_name or file_id[:12]}]")
    who = msg.get("from") or {}
    reply = msg.get("reply_to_message") or {}
    return {
        "update_id": update.get("update_id"),
        "ts": datetime.fromtimestamp(msg.get("date", 0)).isoformat(timespec="seconds"),
        "chat_id": chat.get("id"),
        "chat_title": chat.get("title") or chat.get("username") or "",
        "chat_type": chat.get("type") or "",
        "from": who.get("first_name", ""),
        "from_username": who.get("username") or "",
        "message_id": msg.get("message_id"),
        "reply_to": reply.get("message_id"),
        "text": " ".join(parts).strip(),
        "file_id": file_id,
        "file_name": file_name,
        "file_type": file_type,
    }


def poll_once(offset, timeout=25):
    payload = {"limit": 30, "timeout": timeout}
    if offset is not None:
        payload["offset"] = offset
    return request_json("getUpdates", payload=payload, timeout=timeout + 15)


def cmd_listen(args):
    db_init()
    db_migrate_jsonl()
    pruned = db_prune()
    offset = load_offset()
    print(f"[listen] offset={offset} allowed={sorted(allowed_chat_ids()) or '-'}. db={DB_PATH}. Ctrl+C — выход.", flush=True)
    if pruned:
        print(f"[listen] удалено старых (> {RETENTION_DAYS} дн): {pruned}", flush=True)
    loop = 0
    while True:
        try:
            updates = poll_once(offset, args.poll_timeout)
        except Exception as e:
            print(f"[listen] ошибка: {e} — сплю 10с", flush=True)
            time.sleep(10)
            continue
        for u in updates:
            uid = u.get("update_id")
            if offset is None or uid >= offset:
                offset = uid + 1
            rec = extract(u)
            if not rec:
                continue
            allowed = allowed_chat_ids()
            cid = str(rec.get("chat_id") or "")
            if not allowed or cid in allowed:
                rec["status"] = "new"
            else:
                rec["status"] = "pending"
            # скачать файл, если есть
            if rec.get("file_id"):
                try:
                    path = save_tg_file(rec["file_id"], rec.get("file_name"))
                    rec["file_path"] = path
                    if path:
                        print(f"[file] сохранён: {path}", flush=True)
                except Exception as e:
                    print(f"[file] не скачался: {e}", flush=True)
                    rec["file_path"] = None
            db_insert(rec)
            if rec["status"] == "new":
                extra = f"  📎 файл: {rec['file_path']}" if rec.get("file_path") else ""
                print(f"\n>>> [{rec['ts']}] {rec['from']}:\n    {rec['text']}{extra}\n", flush=True)
        save_offset(offset)
        loop += 1
        if loop % 200 == 0:  # раз в ~час чистим старьё
            db_prune()
        if args.once:
            break


def cmd_fetch(args):
    """Докачать файлы для записей без file_path (повторная попытка)."""
    db_init()
    with db_conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM messages WHERE file_id IS NOT NULL AND file_id!='' "
            "AND (file_path IS NULL OR file_path='')").fetchall()]
    if not rows:
        print("Неоткачанных файлов нет.")
        return
    n = 0
    for r in rows:
        try:
            fp = save_tg_file(r["file_id"], r.get("file_name"))
            if fp:
                _db_set_file(r["update_id"], fp)
                n += 1
                print(f"→ {fp}")
        except Exception as e:
            print(f"  не удалось: {e}", file=sys.stderr)
    print(f"Докачано файлов: {n}")


def _chat_filter(args):
    if not getattr(args, "to", None):
        return None
    return str(resolve_chat(args.to))


def _fmt_msg(r):
    who = r.get("from_user") or ""
    un = r.get("from_username") or ""
    if un:
        who = f"{who} @{un}".strip()
    title = r.get("chat_title") or ""
    extra_head = f" chat={r.get('chat_id')} msg={r.get('message_id') or '-'}"
    if title:
        extra_head += f" «{title}»"
    fp = r.get("file_path")
    extra = f"\n  📎 {fp}" if fp else (
        "\n  📎 файл не скачан — докачай: telegram_bridge.py fetch" if r.get("file_id") else ""
    )
    return f"#{r['update_id']} [{r['ts']}] {who}{extra_head}:\n  {r['text']}{extra}"


def cmd_unread(args):
    db_init()
    db_migrate_jsonl()
    chat = _chat_filter(args)
    with db_conn() as c:
        if chat:
            rows = [dict(r) for r in c.execute(
                "SELECT * FROM messages WHERE status='new' AND chat_id=? ORDER BY update_id ASC",
                (chat,)).fetchall()]
        else:
            rows = [dict(r) for r in c.execute(
                "SELECT * FROM messages WHERE status='new' ORDER BY update_id ASC").fetchall()]
    if not rows:
        print("Непрочитанных нет.")
        return
    print(f"Непрочитанных: {len(rows)}\n" + "=" * 50)
    for r in rows:
        print(_fmt_msg(r) + "\n")
    if args.consume:
        ids = [r["update_id"] for r in rows]
        with db_conn() as c:
            c.executemany("UPDATE messages SET status='read' WHERE update_id=?", [(i,) for i in ids])
        print(f"Помечено прочитанными: {len(rows)}.")


def cmd_latest(args):
    """Самое свежее сообщение (+ файл). По умолчанию read-only (не отмечает прочитанным)."""
    db_init()
    db_migrate_jsonl()
    chat = _chat_filter(args)
    with db_conn() as c:
        if chat:
            row = c.execute(
                "SELECT * FROM messages WHERE status!='ignored' AND chat_id=? "
                "ORDER BY update_id DESC LIMIT 1", (chat,)).fetchone()
        else:
            row = c.execute(
                "SELECT * FROM messages WHERE status!='ignored' ORDER BY update_id DESC LIMIT 1"
            ).fetchone()
    if not row:
        print("Сообщений пока нет.")
        return
    d = dict(row)
    if d.get("file_id") and (args.file or not d.get("file_path")):
        try:
            d["file_path"] = save_tg_file(d["file_id"], d.get("file_name"))
            _db_set_file(d["update_id"], d["file_path"])
        except Exception as e:
            print(f"  ⚠ файл не скачался: {e}", file=sys.stderr)
    print("ПОСЛЕДНЕЕ СООБЩЕНИЕ\n" + _fmt_msg(d))


def cmd_pending(args):
    db_init()
    with db_conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT chat_id, chat_title, chat_type, COUNT(*) AS n, MAX(ts) AS last_ts "
            "FROM messages WHERE status='pending' GROUP BY chat_id, chat_title, chat_type "
            "ORDER BY last_ts DESC").fetchall()]
    if not rows:
        print("Pending нет. Новых чатов вне алиасов бот не видел.")
        return
    print(f"Pending чатов: {len(rows)}")
    for r in rows:
        print(f"  chat_id={r['chat_id']} type={r['chat_type'] or '?'} "
              f"«{r['chat_title'] or ''}» msgs={r['n']} last={r['last_ts']}")
    print("Привязать: telegram_bridge.py bind --alias <имя> --chat-id <id>")


def cmd_bind(args):
    db_init()
    chat_id = args.chat_id
    title = None
    chat_type = None
    if not chat_id:
        with db_conn() as c:
            row = c.execute(
                "SELECT chat_id, chat_title, chat_type FROM messages "
                "WHERE status='pending' ORDER BY update_id DESC LIMIT 1"
            ).fetchone()
        if not row:
            raise TgError("нет pending-чата и не задан --chat-id")
        chat_id, title, chat_type = row["chat_id"], row["chat_title"], row["chat_type"]
    else:
        with db_conn() as c:
            row = c.execute(
                "SELECT chat_title, chat_type FROM messages WHERE chat_id=? "
                "ORDER BY update_id DESC LIMIT 1", (str(chat_id),)
            ).fetchone()
        if row:
            title, chat_type = row["chat_title"], row["chat_type"]
    path = save_target(args.alias, chat_id, chat_type=chat_type, title=title)
    with db_conn() as c:
        n = c.execute(
            "UPDATE messages SET status='new' WHERE status='pending' AND chat_id=?",
            (str(chat_id),)
        ).rowcount
    print(f"bound alias={args.alias} chat_id={chat_id} type={chat_type or '?'} "
          f"title={title or '?'} pending→new={n} file={path}")


def cmd_ack(args):
    db_init()
    with db_conn() as c:
        cur = c.execute("UPDATE messages SET status='read' WHERE update_id=?", (args.update_id,))
        n = cur.rowcount
    if not n:
        raise TgError(f"update_id={args.update_id} не найден")
    print(f"ack update_id={args.update_id}")


def cmd_targets(args):
    data = load_targets()
    if not data:
        print("Алиасов нет.")
        return
    print(f"Алиасов: {len(data)}  ({targets_path()})")
    for alias, item in data.items():
        if isinstance(item, dict):
            label = item.get("title") or item.get("username") or ""
            print(f"  {alias}: chat_id={item.get('chat_id')} type={item.get('type') or '?'} {label}")
        else:
            print(f"  {alias}: {item}")


# ---------- cli ----------

def main():
    load_env()
    p = argparse.ArgumentParser(description="Глобальный Telegram-мост для opencode")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("verify")

    s = sub.add_parser("send")
    s.add_argument("--to")
    s.add_argument("--file")
    s.add_argument("--stdin", action="store_true")
    s.add_argument("--parse-mode", choices=("Markdown", "MarkdownV2", "HTML"))
    s.add_argument("--no-preview", action="store_true")
    s.add_argument("--reply-to", type=int, help="message_id в чате, на который отвечаем")
    s.add_argument("message", nargs="?")

    sf = sub.add_parser("send-file", help="отправить любой файл документом")
    sf.add_argument("--to")
    sf.add_argument("--caption")
    sf.add_argument("path")

    sp = sub.add_parser("send-photo", help="отправить картинку фото с превью")
    sp.add_argument("--to")
    sp.add_argument("--caption")
    sp.add_argument("--parse-mode", choices=("Markdown", "MarkdownV2", "HTML"))
    sp.add_argument("path")

    ur = sub.add_parser("unread")
    ur.add_argument("--consume", action="store_true")
    ur.add_argument("--to", help="алиас или chat_id")
    sub.add_parser("fetch")

    lt = sub.add_parser("latest")
    lt.add_argument("--file", action="store_true",
        help="гарантированно скачать файл последнего сообщения")
    lt.add_argument("--to", help="алиас или chat_id")

    sub.add_parser("pending")
    bd = sub.add_parser("bind")
    bd.add_argument("--alias", required=True)
    bd.add_argument("--chat-id")
    ac = sub.add_parser("ack")
    ac.add_argument("update_id", type=int)
    sub.add_parser("targets")

    lp = sub.add_parser("listen")
    lp.add_argument("--once", action="store_true")
    lp.add_argument("--poll-timeout", type=int, default=25)

    lv = sub.add_parser("live")
    lv.add_argument("seconds", type=int, nargs="?", default=180)
    lv.add_argument("--poll-timeout", type=int, default=25)

    args = p.parse_args()
    try:
        if args.cmd == "verify":
            cmd_verify(args)
        elif args.cmd == "send":
            cmd_send(args)
        elif args.cmd == "send-file":
            cmd_send_file(args)
        elif args.cmd == "send-photo":
            cmd_send_photo(args)
        elif args.cmd == "unread":
            cmd_unread(args)
        elif args.cmd == "latest":
            cmd_latest(args)
        elif args.cmd == "pending":
            cmd_pending(args)
        elif args.cmd == "bind":
            cmd_bind(args)
        elif args.cmd == "ack":
            cmd_ack(args)
        elif args.cmd == "targets":
            cmd_targets(args)
        elif args.cmd == "fetch":
            cmd_fetch(args)
        elif args.cmd in ("listen", "live"):
            if args.cmd == "live":
                t = threading.Timer(args.seconds, lambda: os._exit(0))
                t.daemon = True
                t.start()
                print(f"[live] слушаю {args.seconds}с...", flush=True)
            args.once = getattr(args, "once", False)
            cmd_listen(args)
    except TgError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
