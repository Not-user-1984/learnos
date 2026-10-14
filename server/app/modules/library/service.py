"""Сервис библиотеки: источники, главы, jobs, upload."""

import logging
import shutil
from pathlib import Path

from ...kernel.clock import Clock, now_iso
from ...kernel.db import UnitOfWorkFactory
from ...kernel.errors import Conflict, ValidationFailed
from ...kernel.ids import IdGenerator
from .domain import SourceRules
from .events import SourceProcessed
from .infra.sql_repo import ChapterRepository, JobRepository, SourceRepository

log = logging.getLogger("learnos.library")


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
        self._knowledge = None  # ставится в bootstrap (публичный сервис knowledge)

    def bind(self, knowledge) -> None:
        """Связь с публичным сервисом базы знаний (для проверки удаления)."""
        self._knowledge = knowledge

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
        uid = self._ids.new("src")
        now = now_iso(self._clock)
        with self._uow() as uow:
            source_id = self._sources.insert(
                uow.session,
                uid=uid,
                kind=kind,
                title=title,
                author=author,
                url=url,
                local_path=local_path,
                status="chosen",
                meta_json="{}",
                created_at=now,
                updated_at=now,
            )
        return {"id": source_id, "uid": uid, "kind": kind, "title": title, "status": "chosen"}

    def get_source(self, ref: str | int) -> dict:
        """Обзор источника + главы."""
        with self._uow() as uow:
            src = self._sources.get(uow.session, ref)
            src["chapters"] = [
                {k: ch[k] for k in ("idx", "title", "tokens_est", "summary", "key_points", "has_exercises")}
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
            return items

    def delete_source(self, ref: str | int) -> dict:
        """Удалить источник; запрещено, если по нему есть блоки. Файлы удаляются тоже."""
        with self._uow() as uow:
            src = self._sources.get(uow.session, ref)
            if self._knowledge is not None and self._knowledge.count_for_source(src["uid"]) > 0:
                raise Conflict(f"по источнику «{src['title']}» есть блоки — сначала удалите их")
            self._sources.delete(uow.session, src["id"])
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
        """Поставить job обработки источника (PDF → главы; YouTube → транскрипт)."""
        with self._uow() as uow:
            src = self._sources.get(uow.session, ref)
            if src["status"] == "processed" and not force:
                return {
                    "ok": True,
                    "note": "уже обработан",
                    "source": src["uid"],
                    "chapters": len(self._chapters.list(uow.session, src["id"])),
                }
            if not force and not SourceRules.can_process(src["status"]):
                raise Conflict(f"источник в статусе '{src['status']}' — обработка недоступна")
            now = now_iso(self._clock)
            job_id = self._jobs.enqueue(
                uow.session, kind="process_source", target=src["uid"], total=1, now=now
            )
            self._sources.update(uow.session, src["id"], status="processing", updated_at=now)
        return {"ok": True, "job_id": job_id, "source": src["uid"]}

    def get_job(self, job_id: int) -> dict:
        """Статус job."""
        with self._uow() as uow:
            return self._jobs.get(uow.session, job_id)

    # --- выполнение jobs (вызывает воркер) ---

    def run_job(self, job: dict) -> dict:
        """Выполнить один job: process_source → скилл → summarize_chapters."""
        if job["kind"] == "process_source":
            return self._run_process(job)
        if job["kind"] == "summarize_chapters":
            return self._run_summarize(job)
        raise ValidationFailed(f"неизвестный вид job: {job['kind']}")

    def _run_process(self, job: dict) -> dict:
        src_uid = job["target"]
        with self._uow() as uow:
            src = self._sources.get(uow.session, src_uid)
            source_id, kind, url = src["id"], src["kind"], src["url"]
            self._jobs.update(uow.session, job["id"], status="running", updated_at=now_iso(self._clock))
            self._chapters.delete_for_source(uow.session, source_id)

        if kind == "book":
            result = self._skills.run("book-splitter", {"source_id": source_id})
        elif kind == "video" and url:
            result = self._run_video(src, url)
        else:
            result = {
                "error": (
                    f"не знаю, как обрабатывать kind='{kind}' (нужен url для video или local_path для book)"
                )
            }

        now = now_iso(self._clock)
        if result.get("ok"):
            chapters_count = 0
            with self._uow() as uow:
                chapters_count = self._chapters.count(uow.session, source_id)
                self._sources.update(uow.session, source_id, status="processed", updated_at=now)
                self._jobs.update(uow.session, job["id"], status="done", progress=1, total=1, updated_at=now)
                summary_job = self._jobs.enqueue(
                    uow.session, kind="summarize_chapters", target=src_uid, total=chapters_count, now=now
                )
                uow.emit(SourceProcessed(source_uid=src_uid, source_id=source_id, chapters=chapters_count))
            return {
                "ok": True,
                "job_id": job["id"],
                "summary_job_id": summary_job,
                "chapters": chapters_count,
            }
        with self._uow() as uow:
            self._sources.update(uow.session, source_id, status="failed", updated_at=now)
            self._jobs.update(
                uow.session, job["id"], status="failed", error=str(result.get("error"))[:500], updated_at=now
            )
        return {"error": result.get("error"), "job_id": job["id"]}

    def _run_video(self, src: dict, url: str) -> dict:
        """YouTube → транскрипт-скилл → одна глава."""
        result = self._skills.run("youtube-to-summary", {"url": url})
        if not result.get("ok"):
            return result
        from pathlib import Path as P

        path = P(result["path"])
        text_len = path.stat().st_size
        now = now_iso(self._clock)
        with self._uow() as uow:
            self._chapters.insert(
                uow.session,
                source_id=src["id"],
                idx=1,
                title=result.get("title") or url,
                path=str(path),
                tokens_est=max(1, text_len // 4),
                summary=(result.get("preview") or "")[:280],
            )
            import json

            self._sources.update(
                uow.session,
                src["id"],
                status="processed",
                updated_at=now,
                meta_json=json.dumps({"video_id": result.get("video_id"), "lang": result.get("lang")}),
            )
        return result

    def _run_summarize(self, job: dict) -> dict:
        """Summary по каждой главе через chapter_summarizer + обзор источника."""
        if self._runtime is None:
            return {"ok": True, "note": "LLM не настроен, summary пропущены"}
        from .agents import chapter_summarizer

        src_uid = job["target"]
        with self._uow() as uow:
            src = self._sources.get(uow.session, src_uid)
            chapter_list = self._chapters.list(uow.session, src["id"])
            self._jobs.update(uow.session, job["id"], status="running", updated_at=now_iso(self._clock))

        from ...kernel.asyncio_bridge import run_coro_sync

        summaries: list[str] = []
        done = 0
        for ch in chapter_list:
            text = Path(ch["path"]).read_text(encoding="utf-8")[:12000]
            try:
                out = run_coro_sync(
                    self._runtime.run_structured(
                        chapter_summarizer,
                        type(
                            "Ctx",
                            (),
                            {
                                "system_extra": f"Источник: {src['title']}\nГлава {ch['idx']}: {ch['title']}",
                                "conversation_uid": None,
                                "parent_run_id": None,
                                "variables": {},
                                "cancellation": None,
                            },
                        )(),
                        text,
                    )
                )
                summary, key_points, has_ex = out.summary, out.key_points, out.has_exercises
            except Exception as e:  # noqa: BLE001 — без LLM оставляем заглушки
                log.warning("chapter summary failed: %s", e)
                summary, key_points, has_ex = (ch["summary"] or "")[:280], ch["key_points"], False
            summaries.append(f"Глава {ch['idx']}. {ch['title']}: {summary}")
            done += 1
            with self._uow() as uow:
                import json

                self._chapters.update(
                    uow.session,
                    ch["id"],
                    summary=summary,
                    key_points_json=json.dumps(key_points, ensure_ascii=False),
                    has_exercises=int(has_ex),
                )
                self._jobs.update(uow.session, job["id"], progress=done, updated_at=now_iso(self._clock))

        now = now_iso(self._clock)
        with self._uow() as uow:
            self._sources.update(uow.session, src["id"], summary=" ".join(summaries)[:2000], updated_at=now)
            self._jobs.update(uow.session, job["id"], status="done", progress=done, updated_at=now)
        return {"ok": True, "chapters": done}

    # --- главы ---

    def list_chapters(self, ref: str | int) -> list[dict]:
        """Главы обработанного источника."""
        with self._uow() as uow:
            src = self._sources.get(uow.session, ref)
            return [
                {k: ch[k] for k in ("idx", "title", "tokens_est", "summary", "key_points", "has_exercises")}
                for ch in self._chapters.list(uow.session, src["id"])
            ]

    def read_chapter(self, ref: str | int, chapter: int, offset: int = 0, limit: int = 12000) -> dict:
        """Порция текста главы (контекст LLM не захламляем)."""
        with self._uow() as uow:
            src = self._sources.get(uow.session, ref)
            ch = self._chapters.get(uow.session, src["id"], chapter)
        text = Path(ch["path"]).read_text(encoding="utf-8")
        chunk = text[offset : offset + limit]
        return {
            "source": src["uid"],
            "source_title": src["title"],
            "idx": ch["idx"],
            "title": ch["title"],
            "total_chars": len(text),
            "offset": offset,
            "next_offset": offset + limit if offset + limit < len(text) else None,
            "text": chunk,
        }

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
