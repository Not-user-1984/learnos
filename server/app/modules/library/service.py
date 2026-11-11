"""Сервис библиотеки: источники, главы, jobs, upload."""

import json
import logging
import shutil
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx

from ...kernel.clock import Clock, now_iso
from ...kernel.db import UnitOfWorkFactory
from ...kernel.errors import Conflict, ExternalServiceError, NotFound, ValidationFailed
from ...kernel.ids import IdGenerator
from .domain import SourceRules, normalize_url
from .events import SourceDeleted
from .infra.sql_repo import ChapterRepository, JobRepository, SourceRepository

log = logging.getLogger("learnos.library")

# скачивание PDF по ссылке (from-url): браузерный UA (трекеры режут роботов),
# лимит размера и таймаут на соединение/чанк стрима
URL_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126 Safari/537.36"
)
MAX_URL_PDF_BYTES = 200 * 1024 * 1024
URL_TIMEOUT = httpx.Timeout(connect=15, read=90, write=10, pool=15)
_PDF_MAGIC_PROBE = 1024  # байт достаточно, чтобы увидеть %PDF- в начале ответа


class LibraryService:
    """Use-cases библиотеки: добавить источник, обработать (job), читать главы."""

    def __init__(
        self,
        uow: UnitOfWorkFactory,
        sources: SourceRepository,
        chapters: ChapterRepository,
        jobs: JobRepository,
        skills,
        ids: IdGenerator,
        clock: Clock,
        settings,
        runtime=None,
        research=None,
    ) -> None:
        self._uow = uow
        self._sources = sources
        self._chapters = chapters
        self._jobs = jobs
        self._skills = skills
        self._ids = ids
        self._clock = clock
        self._settings = settings
        self._runtime = runtime
        self._research = research  # публичный сервис research (веб-статьи → главы)
        self._knowledge = None  # ставится в bootstrap (публичный сервис knowledge)
        self._learning = None  # ставится в bootstrap (каскад удаления)
        self._chat = None
        self._courses = None  # проверка «источник в элементах курсов» (R-16)
        self._outline_cache: dict[int, dict] = {}  # source_id → страницы глав по закладкам PDF
        from .usecases.processing import ProcessingUseCases

        self._processing_uc = ProcessingUseCases(self)

    def bind(self, knowledge) -> None:
        """Связь с публичным сервисом базы знаний (для проверки удаления)."""
        self._knowledge = knowledge

    def bind_runtime(self, learning, chat) -> None:
        """Сервисы обучения/чата — для каскада при удалении источника."""
        self._learning = learning
        self._chat = chat

    def bind_courses(self, courses) -> None:
        """Публичный сервис курсов — для запрета удаления источника из курсов (R-16)."""
        self._courses = courses

    # --- источники ---

    def add_source(
        self,
        kind: str,
        title: str,
        url: str | None = None,
        local_path: str | None = None,
        course_id: int | None = None,
        author: str | None = None,
    ) -> dict:
        """Добавить источник в библиотеку (без обязательного курса)."""
        del course_id  # добавление в курс — отдельный вызов courses
        try:
            kind = SourceRules.normalize_kind(kind)
        except ValueError as e:
            raise ValidationFailed(str(e)) from e
        # дедуп по URL (B-007): повторный add_source не плодит источников
        normalized = normalize_url(url) if url else url
        if normalized:
            with self._uow() as uow:
                existing = self._sources.find_by_url(uow.session, normalized)
            if existing is not None:
                return {**existing, "created": False, "note": "источник с таким URL уже есть"}
        uid = self._ids.new("src")
        now = now_iso(self._clock)
        with self._uow() as uow:
            source_id = self._sources.insert(
                uow.session,
                uid=uid,
                kind=kind,
                title=title,
                author=author,
                url=normalized,
                local_path=local_path,
                status="chosen",
                meta_json="{}",
                created_at=now,
                updated_at=now,
            )
        return {
            "id": source_id,
            "uid": uid,
            "kind": kind,
            "title": title,
            "status": "chosen",
            "created": True,
        }

    def resolve_ref(self, ref: str | int) -> dict:
        """id/uid/title по ссылке — лёгкий порт без глав (B-009)."""
        with self._uow() as uow:
            src = self._sources.get(uow.session, ref)
            return {"id": src["id"], "uid": src["uid"], "title": src["title"]}

    def source_ref(self, source_id: int) -> dict:
        """uid+title по id — порт для learning (block_sources урока, B-009)."""
        with self._uow() as uow:
            src = self._sources.get(uow.session, source_id)
            return {"uid": src["uid"], "title": src["title"]}

    def chapters_count(self, source_id: int) -> int:
        """Число глав источника — порт вместо прямого чтения infra (B-009)."""
        with self._uow() as uow:
            return self._chapters.count(uow.session, source_id)

    def segments(self, ref: str | int) -> dict:
        """Сегменты видео-транскрипта с таймкодами (B-006): data/youtube/<id>.segments.json.

        Старые видео без файла сегментов отвечают пустым списком — транскрипт
        работает как раньше, без синхронизации плеера.
        """
        src = self.get_source(ref)
        video_id = (src.get("meta") or {}).get("video_id")
        if not video_id:
            return {"segments": [], "video_id": None, "url": src.get("url")}
        path = Path(self._settings.data_dir) / "youtube" / f"{video_id}.segments.json"
        segments = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
        return {"segments": segments, "video_id": video_id, "url": src.get("url")}

    def get_source(self, ref: str | int) -> dict:
        """Обзор источника + главы."""
        with self._uow() as uow:
            src = self._sources.get(uow.session, ref)
            src["last_error"] = self._source_last_error(uow.session, src)
            src["chapters"] = [
                {
                    k: ch[k]
                    for k in (
                        "idx",
                        "title",
                        "tokens_est",
                        "summary",
                        "key_points",
                        "has_exercises",
                        "number",
                        "start_page",
                        "end_page",
                    )
                }
                for ch in self._chapters.list(uow.session, src["id"])
            ]
            return src

    def list_sources(
        self, kind: str | None = None, q: str | None = None, course_id: int | None = None
    ) -> list[dict]:
        """Список источников с числом глав; course_id фильтрует по курсу (через курс-сервис)."""
        del course_id
        with self._uow() as uow:
            items = self._sources.list(uow.session, kind=kind, q=q)
            for s in items:
                s["chapters_count"] = self._chapters.count(uow.session, s["id"])
                s["last_error"] = self._source_last_error(uow.session, s)
            return items

    def _source_last_error(self, session, src: dict) -> str | None:
        """Ошибка последней обработки — только у failed-источников (B-001)."""
        if src.get("status") != "failed":
            return None
        return self._jobs.last_error(session, target=src["uid"])

    def delete_source(self, ref: str | int) -> dict:
        """Удалить источник; запрещено, если по нему есть блоки. Файлы удаляются тоже.

        Каскад: разговоры и сессии отвязываются от активностей (история остаётся),
        активности удаляются — иначе FK sources←activities роняет удаление.
        """
        with self._uow() as uow:
            src = self._sources.get(uow.session, ref)
            if self._knowledge is not None and self._knowledge.count_for_source(src["uid"]) > 0:
                raise Conflict(f"по источнику «{src['title']}» есть блоки — сначала удалите их")
        if self._courses is not None:
            used = self._courses.count_items_for_source(src["id"])
            if used:
                raise Conflict(
                    f"источник «{src['title']}» входит в {used} элемент(ов) курсов — "
                    "сначала уберите его из курсов"
                )
        if self._learning is not None:
            act_ids = self._learning.activity_ids_for_source(src["uid"])
            if act_ids:
                if self._chat is not None:
                    self._chat.detach_activities(act_ids)
                self._learning.release_activities(act_ids)
        with self._uow() as uow:
            self._sources.delete(uow.session, src["id"])
            uow.emit(SourceDeleted(source_uid=src["uid"]))
        self._outline_cache.pop(src["id"], None)
        data_dir = Path(self._settings.data_dir)
        for sub in ("sources",):
            candidate = data_dir / sub / str(src["id"])
            if candidate.exists():
                shutil.rmtree(candidate, ignore_errors=True)
            by_uid = data_dir / sub / src["uid"]
            if by_uid.exists():
                shutil.rmtree(by_uid, ignore_errors=True)
        return {"ok": True, "deleted": src["uid"]}

    def process_source(self, ref: str | int, force: bool = False) -> dict:
        """Запуск обработки (usecases/processing, B-009)."""
        return self._processing_uc.process_source(ref, force)

    def get_job(self, job_id: int) -> dict:
        """Статус job."""
        with self._uow() as uow:
            return self._jobs.get(uow.session, job_id)

    # --- конвейер обработки (перенесено в usecases/processing.py, B-009) ---

    def finish_job(self, job_id: int, status: str, message: str = "") -> None:
        self._processing_uc.finish_job(job_id, status, message)

    def fail_stuck_job(self, job_id: int, source_uid: str | None, error: str) -> None:
        self._processing_uc.fail_stuck_job(job_id, source_uid, error)

    def recover_stuck_jobs(self) -> dict:
        return self._processing_uc.recover_stuck_jobs()

    def run_job(self, job: dict) -> dict:
        return self._processing_uc.run_job(job)

    # --- главы ---

    def list_chapters(self, ref: str | int) -> list[dict]:
        """Главы обработанного источника."""
        with self._uow() as uow:
            src = self._sources.get(uow.session, ref)
            return [
                {
                    k: ch[k]
                    for k in (
                        "idx",
                        "title",
                        "tokens_est",
                        "summary",
                        "key_points",
                        "has_exercises",
                        "number",
                        "start_page",
                        "end_page",
                    )
                }
                for ch in self._chapters.list(uow.session, src["id"])
            ]

    def read_chapter(self, ref: str | int, chapter: int, offset: int = 0, limit: int = 6000) -> dict:
        """Порция текста главы (контекст LLM не захламляем)."""
        with self._uow() as uow:
            src = self._sources.get(uow.session, ref)
            ch = self._chapters.get(uow.session, src["id"], chapter)
        text = Path(ch["path"]).read_text(encoding="utf-8")
        chunk = text[offset : offset + limit]
        return {
            "source": src["uid"],
            "source_title": src["title"],
            "kind": src["kind"],
            "idx": ch["idx"],
            "title": ch["title"],
            "total_chars": len(text),
            "offset": offset,
            "next_offset": offset + limit if offset + limit < len(text) else None,
            "message": f"символы {offset + 1}–{min(offset + limit, len(text))} из {len(text)}",
            "text": chunk,
        }

    # --- PDF-оригинал и закладки ---

    def source_file(self, ref: str | int) -> Path:
        """Путь к оригинальному PDF источника (для встроенного просмотрщика)."""
        with self._uow() as uow:
            src = self._sources.get(uow.session, ref)
        if src["kind"] != "book" or not src.get("local_path"):
            raise NotFound(f"у источника «{src['title']}» нет PDF-оригинала")
        path = Path(src["local_path"])
        if not path.is_file():
            raise NotFound(f"файл источника «{src['title']}» не найден на диске")
        return path

    def chapter_pages(self, ref: str | int) -> dict:
        """Оглавление для PDF-ридера: стартовые страницы, номера глав, секции level-2.

        Новый ингест пишет границы страниц сплиттером — отдаём из БД. Старые источники
        (без start_page) — матч закладок по нормализованному названию, промах —
        страница предыдущей главы +1. Результат кэшируется по source_id до reprocess.
        """
        with self._uow() as uow:
            src = self._sources.get(uow.session, ref)
            chapter_list = self._chapters.list(uow.session, src["id"])
        if src["kind"] != "book":
            raise NotFound(f"у источника «{src['title']}» нет PDF-оригинала")
        from_db = [ch for ch in chapter_list if ch.get("start_page")]
        if not from_db and not src.get("local_path"):
            # старый ингест без страниц в БД: страницы можно достать только из закладок PDF
            raise NotFound(f"у источника «{src['title']}» нет PDF-оригинала")
        cached = self._outline_cache.get(src["id"])
        if cached is not None:
            return {"source": src["uid"], **cached}

        result: dict = {"total_pages": 0, "pages": {}, "numbers": {}, "sections": {}}
        if from_db:
            for ch in chapter_list:
                key = str(ch["idx"])
                if ch.get("start_page"):
                    result["pages"][key] = int(ch["start_page"])
                if ch.get("number"):
                    result["numbers"][key] = int(ch["number"])
                if ch.get("sections"):
                    result["sections"][key] = ch["sections"]
            result["total_pages"] = max((int(ch.get("end_page") or 0) for ch in chapter_list), default=0)
        else:
            result = self._outline_by_toc_match(src, chapter_list)
        self._outline_cache[src["id"]] = result
        return {"source": src["uid"], **result}

    def _outline_by_toc_match(self, src: dict, chapter_list: list[dict]) -> dict:
        """Фолбэк для старых источников: страницы по матчу названий с закладками PDF."""
        import fitz  # pymupdf — уже в зависимостях (book-splitter)

        try:
            doc = fitz.open(src["local_path"])
        except Exception as e:  # noqa: BLE001 — битый PDF не должен ронять API
            raise ValidationFailed(f"не удалось прочитать PDF: {str(e)[:200]}") from e
        with doc:
            toc = doc.get_toc(simple=True)
            # как в book-splitter: главы строились из закладок верхнего уровня
            top = [(t, p) for lvl, t, p in toc if lvl == 1] or [(t, p) for _lvl, t, p in toc]
            toc_pages: dict[str, int] = {}
            for title, page in top:
                toc_pages.setdefault(_norm_title(title), page)
            result: dict = {"total_pages": doc.page_count, "pages": {}, "numbers": {}, "sections": {}}
            last_matched = 1
            for ch in chapter_list:
                hit = toc_pages.get(_norm_title(ch["title"]))
                if hit is not None:
                    last_matched = hit
                    result["pages"][str(ch["idx"])] = hit
                elif last_matched > 1:
                    # промах по названию: глава начинается после предыдущей сматченной
                    result["pages"][str(ch["idx"])] = min(last_matched + 1, doc.page_count)
                else:
                    result["pages"][str(ch["idx"])] = 1
                if ch.get("number"):
                    result["numbers"][str(ch["idx"])] = int(ch["number"])
        return result

    def source_image(self, ref: str | int, name: str) -> Path:
        """Картинка главы источника: только basename из data/sources/<id>/images/.

        Raises:
            NotFound: файла нет или имя пытается выйти за каталог (path traversal).
        """
        with self._uow() as uow:
            src = self._sources.get(uow.session, ref)
        safe = Path(name).name
        if not safe or safe != name or safe.startswith("."):
            raise NotFound(f"картинка «{name}» не найдена")
        path = Path(self._settings.data_dir) / "sources" / str(src["id"]) / "images" / safe
        if not path.is_file():
            raise NotFound(f"картинка «{safe}» не найдена")
        return path

    # --- upload ---

    def upload_pdf(self, filename: str, data: bytes, title: str | None = None) -> dict:
        """Сохранить PDF в data/sources/<uid>/original.pdf и создать источник + job."""
        uid = self._ids.new("src")
        out_dir = Path(self._settings.data_dir) / "sources" / uid
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "original.pdf").write_bytes(data)
        name = title or filename.rsplit(".", 1)[0]
        now = now_iso(self._clock)
        with self._uow() as uow:
            source_id = self._sources.insert(
                uow.session,
                uid=uid,
                kind="book",
                title=name,
                local_path=str(out_dir / "original.pdf"),
                status="chosen",
                meta_json="{}",
                created_at=now,
                updated_at=now,
            )
            job_id = self._jobs.enqueue(uow.session, kind="process_source", target=uid, total=1, now=now)
        return {
            "id": source_id,
            "uid": uid,
            "kind": "book",
            "title": name,
            "status": "chosen",
            "job_id": job_id,
        }

    def research_sources(self, topic: str, limit: int = 8) -> dict:
        """Веб-поиск кандидатов-источников (скилл web-search)."""
        return self._skills.run("web-search", {"query": f"лучшие книги и курсы: {topic}", "limit": limit})

    # --- добавление по ссылке (меню действий над ссылкой в чате) ---

    def from_url(self, url: str) -> dict:
        """Добавить материал по ссылке одним действием; обработка — асинхронным job.

        YouTube-ролик → video-источник с транскриптом; PDF (расширение .pdf или
        content-type/magic-байты ответа) → скачивание и upload-путь книг; прочий
        URL → web-статья. Ответ сразу: uid, kind и job обработки.
        """
        from ...kernel.netguard import assert_public_http_url
        from .domain import is_youtube_url

        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValidationFailed("нужна http(s)-ссылка на видео, PDF или статью")
        assert_public_http_url(url, allow_private=self._settings.allow_private_url_fetch)
        if is_youtube_url(url):
            return self._start_url_source("video", url)
        data = self._probe_pdf(url)
        if data is not None:
            name = Path(unquote(parts.path)).name or "book"
            if not name.lower().endswith(".pdf"):
                name = f"{name}.pdf"
            out = self.upload_pdf(name, data)
            return {
                "ok": True,
                "uid": out["uid"],
                "kind": out["kind"],
                "title": out["title"],
                "job_id": out["job_id"],
                "processing": True,
            }
        return self._start_url_source("web", url)

    def _start_url_source(self, kind: str, url: str) -> dict:
        """Создать video/web-источник по ссылке и поставить job обработки."""
        source = self.add_source(kind, title=url, url=url)
        proc = self.process_source(source["uid"])
        return {
            "ok": True,
            "uid": source["uid"],
            "kind": kind,
            "title": url,
            "job_id": proc.get("job_id"),
            "processing": bool(proc.get("ok")),
        }

    def _probe_pdf(self, url: str) -> bytes | None:
        """GET по ссылке: байты PDF или None, если ответ не похож на книгу.

        Решение по расширению .pdf, content-type и magic-байтам %PDF- в первом
        килобайте (трекеры отдают файлы без расширения и с битым content-type).
        """
        from ...kernel.netguard import checked_stream
        from .domain import is_pdf_url

        proxy = (getattr(self._settings, "web_proxy", "") or "") or None
        chunks: list[bytes] = []
        size = 0
        looks_pdf = is_pdf_url(url)
        try:
            with checked_stream(
                url,
                allow_private=self._settings.allow_private_url_fetch,
                proxy=proxy,
                timeout=URL_TIMEOUT,
                headers={"User-Agent": URL_UA},
            ) as r:
                r.raise_for_status()
                looks_pdf = looks_pdf or (r.headers.get("content-type") or "").lower().startswith(
                    "application/pdf"
                )
                for chunk in r.iter_bytes(64 * 1024):
                    if not looks_pdf:
                        looks_pdf = chunk.lstrip()[:1024].startswith(b"%PDF-")
                    size += len(chunk)
                    if size > MAX_URL_PDF_BYTES:
                        raise ValidationFailed(
                            f"файл больше {MAX_URL_PDF_BYTES // (1024 * 1024)} МБ — "
                            "скачай вручную и загрузи через загрузку PDF"
                        )
                    chunks.append(chunk)
                    if not looks_pdf and size >= _PDF_MAGIC_PROBE:
                        return None
        except httpx.HTTPError as e:
            raise ExternalServiceError(f"не удалось скачать {url}: {str(e)[:200]}") from e
        if size == 0:
            raise ExternalServiceError(f"по ссылке {url} пришёл пустой ответ")
        return b"".join(chunks) if looks_pdf else None


def _norm_title(s: str) -> str:
    """Нормализация названия для матча закладок с главами."""
    import re

    return re.sub(r"\s+", " ", s).strip().lower()
