"""torrent-fetch: поиск книг/фильмов/музыки (Prowlarr) + загрузка (qBittorrent, libgen).

CLI: search "query" [--cat books|movies|music|tv] [--auto] | books "title" [--auto]
     auto "query" | add <N|hash|magnet> | import <hash|подстрока имени> | status
Программный вход: main(**kwargs) — используется скилл-загрузчиком LearnOS.
"""

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from providers.libgen import LibgenClient, LibgenError  # noqa: E402
from providers.prowlarr import ProwlarrClient, ProwlarrError  # noqa: E402
from providers.qbittorrent import (  # noqa: E402
    LEARNOS_BOOKS_CATEGORY,
    QbitClient,
    QbitError,
)

SKILL_DIR = Path(__file__).parent
MAGNET_RE = re.compile(r"^(magnet:\?|xt:urn:btih:)", re.I)
HASH_RE = re.compile(r"^[a-f0-9]{40}$", re.I)


def _config_chain() -> list[Path]:
    """Пути конфига по приоритету: env → рядом со скиллом → data-каталог LearnOS → ~/.config."""
    paths: list[Path] = []
    env = os.environ.get("TORRENT_FETCH_CONFIG", "").strip()
    if env:
        paths.append(Path(env))
    paths.append(SKILL_DIR / "config.json")
    data_dir = os.environ.get("LEARNOS_DATA_DIR", "").strip()
    if data_dir:
        paths.append(Path(data_dir) / "torrent-fetch.json")
    paths.append(Path.home() / ".config" / "torrent-fetch" / "config.json")
    return paths


def _config_path() -> Path | None:
    for p in _config_chain():
        if p.is_file():
            return p
    return None


def _state_path() -> Path:
    """Кэш последнего поиска: env → рядом с найденным конфигом → ~/.config."""
    env = os.environ.get("TORRENT_FETCH_STATE", "").strip()
    if env:
        return Path(env)
    cfg = _config_path()
    if cfg is not None:
        return cfg.parent / "last_search.json"
    return Path.home() / ".config" / "torrent-fetch" / "last_search.json"


def load_config() -> dict:
    """Первый существующий конфиг из цепочки (см. _config_chain)."""
    p = _config_path()
    if p is None:
        tried = ", ".join(str(x) for x in _config_chain())
        raise SystemExit(f"нет конфига (искал: {tried}); образец — config.example.json")
    return json.loads(p.read_text(encoding="utf-8"))


def _state_save(candidates: list[dict]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(candidates, ensure_ascii=False), encoding="utf-8")


def _state_load() -> list[dict]:
    path = _state_path()
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return []


def _fmt_size(n: int) -> str:
    x = float(n)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if x < 1000 or unit == "ГБ":
            return f"{int(x)} {unit}" if unit == "Б" else f"{x:.1f} {unit}"
        x /= 1000
    return f"{x:.1f} ГБ"


def _render_table(candidates: list[dict]) -> str:
    """Человекочитаемая таблица №/название/трекер/размер/сиды."""
    lines = [f"{'№':>2}  {'название':<62} {'трекер':<20} {'размер':>9} {'сиды':>5}"]
    lines.append("-" * 104)
    for i, c in enumerate(candidates, 1):
        lines.append(
            f"{i:>2}  {c['title'][:60]:<62} {c['indexer'][:20]:<20} "
            f"{_fmt_size(c['size']):>9} {c['seeders']:>5}"
        )
    return "\n".join(lines)


def _pick_best_torrent(cands: list[dict]) -> dict | None:
    """Лучший торрент: сиды, при равенстве — компактное название и свежесть."""
    if not cands:
        return None
    return max(
        cands,
        key=lambda c: (
            c["seeders"],
            -len(c["title"]),
            c.get("publish_date", "") or "",
        ),
    )


def _mk_prowlarr(cfg: dict) -> ProwlarrClient:
    p = cfg["prowlarr"]
    return ProwlarrClient(url=p["url"], api_key=p["api_key"])


def _mk_qbit(cfg: dict) -> QbitClient:
    q = cfg["qbittorrent"]
    return QbitClient(
        url=q["url"],
        api_key=q.get("api_key", ""),
        username=q.get("username", ""),
        password=q.get("password", ""),
    )


def _libgen_enabled(cfg: dict) -> bool:
    lg = cfg.get("libgen") or {}
    return bool(lg.get("enabled"))


def do_search(cfg: dict, query: str, cat: str = "books", auto: bool = False, limit: int = 20) -> dict:
    """Поиск: suggest-таблица кандидатов или сразу добавить лучшего (auto)."""
    mode_auto = auto or cfg.get("mode") == "auto"
    candidates: list[dict] = []
    errors: list[str] = []

    if cat == "books" and _libgen_enabled(cfg):
        lg_cfg = cfg.get("libgen") or {}
        try:
            libgen = LibgenClient(mirrors=lg_cfg.get("mirrors"), proxy=lg_cfg.get("proxy", ""))
            # libgen-лейн занимает верх списка, торренты добирают хвост
            candidates = libgen.search(query, limit=max(3, limit // 2))
        except LibgenError as e:
            errors.append(f"libgen: {e}")

    if len(candidates) < limit:
        try:
            prowlarr = _mk_prowlarr(cfg)
            candidates += prowlarr.search(query, cat=cat, limit=limit - len(candidates))
        except ProwlarrError as e:
            errors.append(str(e))
            if not candidates:
                return {"error": "search_failed", "message": "; ".join(errors)}

    _state_save(candidates)
    if mode_auto:
        return _auto_add(cfg, candidates, cat=cat)
    return {
        "mode": "suggest",
        "query": query,
        "cat": cat,
        "count": len(candidates),
        "table": _render_table(candidates),
        "candidates": [
            {k: c.get(k) for k in ("title", "indexer", "size", "seeders", "kind")} for c in candidates[:limit]
        ],
        "next": "add N — скачать кандидата №N",
        "errors": errors or None,
    }


def _auto_add(cfg: dict, candidates: list[dict], cat: str) -> dict:
    """Выбрать лучшего и добавить (книги: libgen-PDF → лучший торрент)."""
    if not candidates:
        return {"error": "not_found", "message": "кандидатов нет"}
    best = candidates[0] if candidates[0]["kind"] == "libgen" else _pick_best_torrent(candidates)
    return _add_candidate(cfg, best, cat=cat)


def _add_candidate(cfg: dict, cand: dict, cat: str) -> dict:
    """Добавить конкретного кандидата: libgen-файл или торрент в qBit."""
    if cand["kind"] == "libgen":
        dest = Path(cfg.get("download_dir", "~/Downloads/torrent-fetch")).expanduser()
        try:
            path = LibgenClient(
                mirrors=(cfg.get("libgen") or {}).get("mirrors"),
                proxy=(cfg.get("libgen") or {}).get("proxy", ""),
            ).download(cand["md5"], dest_dir=dest, filename_hint=cand["title"])
            return {
                "added": True,
                "kind": "libgen",
                "file": str(path),
                "size": path.stat().st_size,
                "title": cand["title"],
            }
        except LibgenError as e:
            return {"error": "libgen_download_failed", "message": str(e), "fallback": "add торрент-кандидата"}
    category = LEARNOS_BOOKS_CATEGORY if cat == "books" else ""
    qbit = _mk_qbit(cfg)
    try:
        res = qbit.add(cand["link"], category=category)
        res.update({"kind": "torrent", "title": cand["title"], "size": cand["size"]})
        return res
    finally:
        qbit.close()


def do_add(cfg: dict, target: str, cat: str = "books") -> dict:
    """add N (из последнего поиска) | hash | magnet-ссылка."""
    candidates = _state_load()
    if MAGNET_RE.match(target) or HASH_RE.match(target):
        if not MAGNET_RE.match(target):
            target = f"magnet:?xt.urn:btih:{target}"
        category = LEARNOS_BOOKS_CATEGORY if cat == "books" else ""
        qbit = _mk_qbit(cfg)
        try:
            return qbit.add(target, category=category)
        finally:
            qbit.close()
    if target.isdigit():
        idx = int(target)
        if not 1 <= idx <= len(candidates):
            return {
                "error": "bad_index",
                "message": f"номер {idx} вне диапазона 1..{len(candidates)}; повтори поиск",
            }
        return _add_candidate(cfg, candidates[idx - 1], cat=cat)
    return {"error": "bad_target", "message": "ожидался номер, 40-символьный hash или magnet-ссылка"}


def do_status(cfg: dict, limit: int = 15) -> dict:
    """Текущие и завершённые раздачи qBit с прогрессом."""
    qbit = _mk_qbit(cfg)
    try:
        torrents = qbit.torrents(limit=limit)
    finally:
        qbit.close()
    table = [f"{'торрент':<60} {'кат':<15} {'%':>5} {'состояние'}"]
    table.append("-" * 100)
    for t in torrents:
        table.append(f"{t['name'][:58]:<60} {t['category'][:15]:<15} {t['progress']:>5} {t['state']}")
    return {"count": len(torrents), "table": "\n".join(table), "torrents": torrents}


# минимальный размер PDF при выборе из каталога раздачи — как в hook на media-CT
_IMPORT_MIN_PDF_BYTES = 100 * 1024


def _import_app():
    """(get_db, DATA_DIR, генератор uid) ядра LearnOS — import пишет source/job в БД.

    Лениво: search/add/status работают без app.* рядом; корень сервера
    добавляется в sys.path для subprocess-запуска run.py вне процесса сервиса.
    """
    root = str(Path(__file__).resolve().parent.parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)
    from app.db import get_db  # лениво: нужен только действию import
    from app.kernel.clock import SystemClock, now_iso
    from app.kernel.ids import UuidHexGenerator
    from app.paths import DATA_DIR

    return get_db, DATA_DIR, UuidHexGenerator(), now_iso, SystemClock()


def _pick_pdf(content_path: str) -> Path | None:
    """PDF раздачи: сам content_path-файл или крупнейший PDF в каталоге (>= 100 КБ)."""
    cp = Path(content_path)
    if cp.is_file():
        return cp if cp.suffix.lower() == ".pdf" else None
    if cp.is_dir():
        pdfs = [p for p in cp.rglob("*.pdf") if p.is_file() and p.stat().st_size >= _IMPORT_MIN_PDF_BYTES]
        return max(pdfs, key=lambda p: p.stat().st_size, default=None)
    return None


def do_import(cfg: dict, ref: str) -> dict:
    """Импорт завершённой раздачи книг в библиотеку LearnOS — fallback hook'а.

    ref — info-hash или подстрока имени раздачи. Допуск: категория learnos-books
    или раздача без категории, обязательно завершённая. PDF — как в hook:
    content_path-файл либо крупнейший PDF каталога. Source и job process_source
    пишутся напрямую в БД (уровень app.db, без сервисного слоя — см. book-splitter);
    существующий source с тем же title не дублируется (existed=True).
    """
    ref = ref.strip()
    if not ref:
        return {"error": "no_target", "message": "import требует hash или query/title раздачи"}
    qbit = _mk_qbit(cfg)
    try:
        torrents = qbit.torrents(limit=500)
    finally:
        qbit.close()
    ref_l = ref.lower()
    matches = [t for t in torrents if t["hash"].lower() == ref_l] or [
        t for t in torrents if ref_l in t["name"].lower()
    ]
    if not matches:
        return {"error": "not_found", "message": f"раздача по «{ref}» в qBit не найдена (см. status)"}
    t = matches[0]
    if t["category"] and t["category"] != LEARNOS_BOOKS_CATEGORY:
        return {
            "error": "bad_category",
            "message": f"категория «{t['category']}» — импортируются только книги "
            f"({LEARNOS_BOOKS_CATEGORY} или без категории)",
        }
    if t["progress"] < 99.9 and not str(t["state"]).upper().endswith("UP"):
        return {
            "error": "not_finished",
            "message": f"раздача ещё не завершена: {t['progress']}% ({t['state']}) — повтори import позже",
        }

    title = Path(t["name"]).stem or t["name"]
    try:
        get_db, data_dir, ids, now_iso, clock = _import_app()
    except Exception as e:  # запуск вне окружения сервиса LearnOS
        return {"error": "no_db", "message": f"БД LearnOS недоступна: {e}"}
    conn = get_db()
    try:
        # идемпотентность: hook мог успеть залить книгу раньше (title с .pdf или без)
        dup = conn.execute(
            "SELECT uid, title, status FROM sources WHERE title IN (?, ?) AND status != 'failed' LIMIT 1",
            (title, f"{title}.pdf"),
        ).fetchone()
        if dup:
            return {
                "ok": True,
                "uid": dup["uid"],
                "title": dup["title"],
                "existed": True,
                "source_status": dup["status"],
            }
        pdf = _pick_pdf(t.get("content_path") or "")
        if pdf is None:
            if t.get("content_path") and not Path(t["content_path"]).exists():
                return {
                    "error": "file_unreachable",
                    "message": (
                        f"файл раздачи «{t['content_path']}» не виден из сервиса "
                        "(qBit на другом хосте — книгу зальёт hook на media-CT)"
                    ),
                }
            return {"error": "no_pdf", "message": f"в раздаче «{t['name']}» нет PDF-файла"}
        uid = ids.new("src")
        out_dir = Path(data_dir) / "sources" / uid
        out_dir.mkdir(parents=True, exist_ok=True)
        dst = out_dir / "original.pdf"
        shutil.copyfile(pdf, dst)
        now = now_iso(clock)
        conn.execute(
            "INSERT INTO sources(uid, kind, title, local_path, status, meta_json, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (uid, "book", title, str(dst), "chosen", "{}", now, now),
        )
        job_id = conn.execute(
            "INSERT INTO jobs(kind, target, status, progress, total, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?)",
            ("process_source", uid, "queued", 0, 1, now, now),
        ).lastrowid
        conn.commit()
        return {"ok": True, "uid": uid, "title": title, "job_id": job_id, "existed": False}
    finally:
        conn.close()


def main(
    action: str = "status",
    query: str = "",
    title: str = "",
    num: int = 0,
    cat: str = "books",
    auto: bool = False,
    magnet: str = "",
    hash: str = "",  # параметр скилла: info-hash раздачи для import
    limit: int = 20,
    **_,
) -> dict:
    """Вход для скилл-загрузчика: action = search | add | status | books | auto | import."""
    try:
        cfg = load_config()
    except SystemExit as e:
        return {"error": "no_config", "message": str(e)}
    try:
        if action == "search":
            if not query:
                return {"error": "no_query", "message": "search требует query"}
            return do_search(cfg, query, cat=cat or "books", auto=auto, limit=limit)
        if action == "books":
            q = query or title
            if not q:
                return {"error": "no_query", "message": "books требует query/title"}
            return do_search(cfg, q, cat="books", auto=auto, limit=limit)
        if action == "auto":
            if not query:
                return {"error": "no_query", "message": "auto требует query"}
            return do_search(cfg, query, cat=cat or "books", auto=True, limit=limit)
        if action == "add":
            target = magnet or (str(num) if num else "")
            if not target:
                return {"error": "no_target", "message": "add требует num или magnet"}
            return do_add(cfg, target, cat=cat or "books")
        if action == "import":
            return do_import(cfg, hash or query or title)
        if action == "status":
            return do_status(cfg)
    except (ProwlarrError, QbitError, LibgenError) as e:
        return {"error": type(e).__name__.lower(), "message": str(e)}
    return {"error": "bad_action", "message": f"неизвестное действие: {action}"}


def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=["search", "books", "auto", "add", "import", "status"])
    parser.add_argument("value", nargs="?", default="", help="query / № / hash / magnet")
    parser.add_argument("--cat", default="books", help="books | movies | music | tv")
    parser.add_argument("--auto", action="store_true", help="качать лучшего без вопроса")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    cfg = load_config()
    if args.action in ("search", "books"):
        res = do_search(cfg, args.value, cat=args.cat, auto=args.auto, limit=args.limit)
    elif args.action == "auto":
        res = do_search(cfg, args.value, cat=args.cat, auto=True, limit=args.limit)
    elif args.action == "add":
        res = do_add(cfg, args.value, cat=args.cat)
    elif args.action == "import":
        res = do_import(cfg, args.value)
    else:
        res = do_status(cfg)
    if res.get("table"):
        print(res["table"])
        res.pop("table")
        print()
    print(json.dumps(res, ensure_ascii=False, indent=2)[:4000])


if __name__ == "__main__":
    _cli()
