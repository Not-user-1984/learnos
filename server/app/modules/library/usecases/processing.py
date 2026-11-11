"""Конвейер обработки источников: jobs, куратор книги, video/web, саммари (B-009)."""

import json
import logging
from pathlib import Path

from ....agent.spec import AgentContext
from ....kernel.asyncio_bridge import run_coro_sync
from ....kernel.clock import now_iso
from ....kernel.errors import NotFound, ValidationFailed
from ..events import SourceProcessed

log = logging.getLogger("learnos.library")


class ProcessingUseCases:
    """Перенос из library/service.py без изменения поведения."""

    def __init__(self, svc) -> None:
        self._svc = svc

    # --- выполнение jobs (вызывает воркер) ---

    def finish_job(self, job_id: int, status: str, message: str = "") -> None:
        """Завершить job стороннего хэндлера: done | skipped (B-008, без источника)."""
        from sqlalchemy import update

        from ..infra.tables import jobs as jobs_t

        with self._svc._uow() as uow:
            uow.session.execute(
                update(jobs_t)
                .where(jobs_t.c.id == job_id)
                .values(status=status, message=str(message)[:500], updated_at=now_iso(self._svc._clock))
            )

    def fail_stuck_job(self, job_id: int, source_uid: str | None, error: str) -> None:
        """Job → failed и связанный источник из processing → failed (R-10).

        Без этого падение воркера оставляло источник «обрабатывается» навсегда:
        process_source не даёт повтор без force, а UI его не передаёт.
        """
        from sqlalchemy import update

        from ..infra.tables import jobs as jobs_t

        now = now_iso(self._svc._clock)
        with self._svc._uow() as uow:
            uow.session.execute(
                update(jobs_t)
                .where(jobs_t.c.id == job_id)
                .values(status="failed", error=str(error)[:500], updated_at=now)
            )
            if not source_uid:
                return
            try:
                src = self._svc._sources.get(uow.session, source_uid)
            except NotFound:
                return
            if src["status"] == "processing":
                self._svc._sources.update(uow.session, src["id"], status="failed", updated_at=now)

    def recover_stuck_jobs(self) -> dict:
        """Старт сервиса: jobs running (убило рестартом) → failed, их источники тоже.

        Идемпотентен; вызывается из lifespan воркера.
        """
        from sqlalchemy import select

        from ..infra.tables import jobs as jobs_t

        with self._svc._uow() as uow:
            rows = uow.session.execute(
                select(jobs_t.c.id, jobs_t.c.target).where(jobs_t.c.status == "running")
            ).all()
        for job_id, target in rows:
            self.fail_stuck_job(job_id, target, "воркер перезапущен во время обработки")
        return {"ok": True, "recovered_jobs": len(rows)}

    def run_job(self, job: dict) -> dict:
        """Выполнить один job: process_source → скилл → summarize_chapters."""
        if job["kind"] == "process_source":
            return self._run_process(job)
        if job["kind"] == "summarize_chapters":
            return self._run_summarize(job)
        raise ValidationFailed(f"неизвестный вид job: {job['kind']}")

    def _run_process(self, job: dict) -> dict:
        src_uid = job["target"]
        with self._svc._uow() as uow:
            src = self._svc._sources.get(uow.session, src_uid)
            source_id, kind, url = src["id"], src["kind"], src["url"]
            self._svc._jobs.update(
                uow.session, job["id"], status="running", updated_at=now_iso(self._svc._clock)
            )
            self._svc._chapters.delete_for_source(uow.session, source_id)
        self._svc._outline_cache.pop(source_id, None)  # главы пересоздаются — матчинг закладок устарел

        if kind == "book":
            result = self._svc._skills.run("book-splitter", {"source_id": source_id})
            # pages-режим (PDF без закладок): куски равноценны, куратор не нужен
            if result.get("ok") and result.get("mode") != "pages":
                # куратор структуры: LLM-классификация top-записей → чистка мусора, номера глав
                result = {**result, **self._curate_book(source_id, src_uid, result)}
        elif kind == "video" and url:
            result = self._run_video(src, url)
        elif kind == "web" and url:
            result = self._run_web(src, url)
        else:
            result = {
                "error": (
                    f"не знаю, как обрабатывать kind='{kind}' "
                    "(нужен url для video/web или local_path для book)"
                )
            }

        now = now_iso(self._svc._clock)
        if result.get("ok"):
            chapters_count = 0
            with self._svc._uow() as uow:
                chapters_count = self._svc._chapters.count(uow.session, source_id)
                self._svc._sources.update(uow.session, source_id, status="processed", updated_at=now)
                self._svc._jobs.update(
                    uow.session, job["id"], status="done", progress=1, total=1, updated_at=now
                )
                summary_job = self._svc._jobs.enqueue(
                    uow.session, kind="summarize_chapters", target=src_uid, total=chapters_count, now=now
                )
                uow.emit(SourceProcessed(source_uid=src_uid, source_id=source_id, chapters=chapters_count))
            return {
                "ok": True,
                "job_id": job["id"],
                "summary_job_id": summary_job,
                "chapters": chapters_count,
            }
        with self._svc._uow() as uow:
            self._svc._sources.update(uow.session, source_id, status="failed", updated_at=now)
            self._svc._jobs.update(
                uow.session, job["id"], status="failed", error=str(result.get("error"))[:500], updated_at=now
            )
        return {"error": result.get("error"), "job_id": job["id"]}

    # --- куратор структуры книги (Э1) ---

    def _curate_book(self, source_id: int, src_uid: str, splitter_result: dict) -> dict:
        """Классифицировать top-записи закладок: chapter/front_matter/appendix.

        LLM-куратор (structure_curator, один вызов на книгу); любая ошибка — эвристика.
        front_matter удаляется (текст кратко уходит в meta источника для обзора),
        главы перенумеровываются подряд, chapter получает number из названия книги.
        Падение куратора не роняет обработку: без классификации записи остаются как есть.
        """
        entries = splitter_result.get("entries") or []
        if not entries:
            return {"curated": False}
        labels = self._curator_labels(entries)
        if labels is None:
            return {"curated": False}
        front_matter: list[str] = []
        with self._svc._uow() as uow:
            rows = {ch["idx"]: ch for ch in self._svc._chapters.list(uow.session, source_id)}
            # позиционные номера — только книгам без собственной нумерации в названиях
            # (иначе «Предисловие»=1 и «Глава 1»=1 дублируются)
            numbered_book = any(
                labels[e["idx"]][1] is not None for e in entries if labels[e["idx"]][0] == "chapter"
            )
            new_idx = 0
            chapter_seq = 0
            for e in entries:
                cls, number = labels[e["idx"]]
                row = rows.get(e["idx"])
                if row is None:
                    continue
                if cls == "front_matter":
                    Path(row["path"]).unlink(missing_ok=True)
                    self._svc._chapters.delete(uow.session, row["id"])
                    if e.get("snippet"):
                        front_matter.append(f"{e['title']}: {e['snippet']}")
                    continue
                new_idx += 1
                if cls == "chapter":
                    chapter_seq += 1
                    if number is None and not numbered_book:
                        number = chapter_seq
                else:
                    number = None
                self._svc._chapters.update(uow.session, row["id"], idx=new_idx, number=number)
            if front_matter and new_idx:
                meta = self._meta_for(uow.session, source_id)
                meta["front_matter"] = "\n\n".join(front_matter)[:2000]
                self._svc._sources.update(
                    uow.session,
                    source_id,
                    meta_json=json.dumps(meta, ensure_ascii=False),
                    updated_at=now_iso(self._svc._clock),
                )
        log.info(
            "куратор %s: глав %d, служебных страниц удалено %d",
            src_uid,
            new_idx,
            len(front_matter),
        )
        return {"curated": True, "front_matter_dropped": len(front_matter), "chapters": new_idx}

    def _curator_labels(self, entries: list[dict]) -> dict[int, tuple[str, int | None]] | None:
        """Метки классов для каждой записи: LLM-куратор, при сбое — эвристика домена.

        Жёсткие правила эвристики (стоп-слова, короткие предисловия) переопределяют
        LLM — модель иногда тащит титульные предисловия в главы. Номер главы —
        только из названия книги; LLM классифицирует, но не нумерует.
        """
        from ..domain import classify_toc_entry, merge_curator_labels, parse_chapter_number

        heuristic = {e["idx"]: classify_toc_entry(e["title"], int(e.get("page_count") or 0)) for e in entries}
        llm: dict[int, str] | None = None
        if self._svc._runtime is not None:
            try:
                llm = self._curate_with_llm(entries)
            except Exception:  # noqa: BLE001 — куратор не должен ронять job
                log.warning("LLM-куратор структуры не сработал, фолбэк на эвристику", exc_info=True)
        classes = merge_curator_labels(entries, heuristic, llm)
        return {e["idx"]: (classes[e["idx"]], parse_chapter_number(e["title"])) for e in entries}

    def _curate_with_llm(self, entries: list[dict]) -> dict[int, str] | None:
        """Один вызов structure_curator на книгу; None — если ответ не покрывает все записи."""
        from ....kernel.asyncio_bridge import run_coro_sync
        from ..agents import structure_curator

        lines = [
            f"{e['idx']}. «{e['title']}» — стр. {e.get('start_page')}, "
            f"{e.get('page_count')} стр.; начало текста: {(e.get('snippet') or '—')[:200]}"
            for e in entries
        ]
        prompt = "Записи закладок книги:\n" + "\n".join(lines)
        out = run_coro_sync(self._svc._runtime.run_structured(structure_curator, AgentContext(), prompt))
        got = {item.idx: item.cls for item in out.entries}
        if set(got) != {e["idx"] for e in entries}:
            log.warning("куратор вернул не все записи (получено %d из %d)", len(got), len(entries))
            return None
        return got

    def _meta_for(self, session, source_id: int) -> dict:
        src = self._svc._sources.get(session, source_id)
        return dict(src.get("meta") or {})

    def _run_video(self, src: dict, url: str) -> dict:
        """YouTube → транскрипт-скилл → одна глава."""
        result = self._svc._skills.run("youtube-to-summary", {"url": url})
        if not result.get("ok"):
            return result
        path = Path(result["path"])
        text_len = path.stat().st_size
        now = now_iso(self._svc._clock)
        video_title = (result.get("title") or "").strip()
        with self._svc._uow() as uow:
            self._svc._chapters.insert(
                uow.session,
                source_id=src["id"],
                idx=1,
                title=video_title or url,
                path=str(path),
                tokens_est=max(1, text_len // 4),
                summary=(result.get("preview") or "")[:280],
            )
            self._svc._sources.update(
                uow.session,
                src["id"],
                status="processed",
                # настоящий тайтл из YouTube: с фронта мог прийти URL (oembed не ответил)
                title=video_title or src["title"],
                updated_at=now,
                meta_json=json.dumps({"video_id": result.get("video_id"), "lang": result.get("lang")}),
            )
        return result

    def _run_web(self, src: dict, url: str) -> dict:
        """Веб-статья → главы по заголовкам (research.extract_chapters), полный текст — в библиотеку."""
        if self._svc._research is None:
            return {"error": "research-модуль недоступен"}
        try:
            page = self._svc._research.extract_chapters(url)
        except Exception as e:  # noqa: BLE001 — битая страница не роняет job
            return {"error": f"не удалось извлечь статью: {str(e)[:300]}"}
        out_dir = Path(self._svc._settings.data_dir) / "sources" / str(src["id"]) / "chapters"
        out_dir.mkdir(parents=True, exist_ok=True)
        now = now_iso(self._svc._clock)
        with self._svc._uow() as uow:
            for i, ch in enumerate(page["chapters"], start=1):
                path = out_dir / f"ch_{i:02d}.md"
                path.write_text(f"# {ch['title']}\n\n{ch['text']}\n", encoding="utf-8")
                self._svc._chapters.insert(
                    uow.session,
                    source_id=src["id"],
                    idx=i,
                    title=ch["title"],
                    path=str(path),
                    tokens_est=max(1, len(ch["text"]) // 4),
                    summary=ch["text"][:280],
                )
            self._svc._sources.update(
                uow.session,
                src["id"],
                status="processed",
                # настоящий заголовок статьи: с фронта мог прийти URL
                title=(page["title"] or src["title"])[:300],
                updated_at=now,
            )
        return {"ok": True, "title": page["title"], "chapters": len(page["chapters"]), "url": url}

    def _run_summarize(self, job: dict) -> dict:
        """Summary по каждой главе через chapter_summarizer + обзор источника."""
        if self._svc._runtime is None:
            return {"ok": True, "note": "LLM не настроен, summary пропущены"}
        src_uid = job["target"]
        with self._svc._uow() as uow:
            src = self._svc._sources.get(uow.session, src_uid)
            chapter_list = self._svc._chapters.list(uow.session, src["id"])
            self._svc._jobs.update(
                uow.session, job["id"], status="running", updated_at=now_iso(self._svc._clock)
            )

        summaries: list[str] = []
        done = 0
        for ch in chapter_list:
            text = Path(ch["path"]).read_text(encoding="utf-8")
            try:
                out = self._summarize_text(src["title"], ch["idx"], ch["title"], text)
                summary, key_points, has_ex = out.summary, out.key_points, out.has_exercises
            except Exception as e:  # noqa: BLE001 — без LLM оставляем заглушки
                log.warning("chapter summary failed: %s", e)
                summary, key_points, has_ex = (ch["summary"] or "")[:280], ch["key_points"], False
            summaries.append(f"Глава {ch['idx']}. {ch['title']}: {summary}")
            done += 1
            with self._svc._uow() as uow:
                self._svc._chapters.update(
                    uow.session,
                    ch["id"],
                    summary=summary,
                    key_points_json=json.dumps(key_points, ensure_ascii=False),
                    has_exercises=int(has_ex),
                )
                self._svc._jobs.update(
                    uow.session, job["id"], progress=done, updated_at=now_iso(self._svc._clock)
                )

        now = now_iso(self._svc._clock)
        overview = self._generate_overview(
            src["title"], summaries, front_matter=(src.get("meta") or {}).get("front_matter") or ""
        )
        with self._svc._uow() as uow:
            self._svc._sources.update(uow.session, src["id"], summary=overview, updated_at=now)
            self._svc._jobs.update(uow.session, job["id"], status="done", progress=done, updated_at=now)
        return {"ok": True, "chapters": done}

    def _summarize_text(self, src_title: str, idx: int, title: str, text: str):
        """Сводка главы: короткая — один вызов, длинная — map-reduce по чанкам (R-20).

        Раньше брались первые 12k символов: summary длинной главы писалось по
        её началу. Теперь чанки по 8k (до 6) сводятся отдельным вызовом.
        """
        from ..agents import chapter_summarizer

        def _call(user_prompt: str):
            return run_coro_sync(
                self._svc._runtime.run_structured(
                    chapter_summarizer,
                    AgentContext(system_extra=f"Источник: {src_title}\nГлава {idx}: {title}"),
                    user_prompt,
                )
            )

        if len(text) <= 16000:
            return _call(text[:16000])

        chunks = [text[i : i + 8000] for i in range(0, min(len(text), 6 * 8000), 8000)]
        partial: list[str] = []
        for i, chunk in enumerate(chunks, 1):
            try:
                out = _call(
                    f"Фрагмент {i}/{len(chunks)} длинной главы (продолжение посередине текста):\n{chunk}"
                )
                partial.append(out.summary or "")
            except Exception:  # noqa: BLE001 — фрагмент без выжимки не роняет главу
                log.warning("summary фрагмента %d главы %s не удался", i, title)
        merged = "\n\n".join(f"Фрагмент {i}: {p}" for i, p in enumerate(partial, 1) if p)
        return _call(
            "Выжимки фрагментов одной длинной главы — собери целостный итог главы "
            "(summary, key_points, упражнения):\n\n" + merged
        )

    def _generate_overview(self, title: str, chapter_summaries: list[str], front_matter: str = "") -> str:
        """Цельный обзор книги из конспектов глав (source_overviewer); фолбэк — склейка.

        front_matter — краткий текст служебных страниц (титул/лицензия/предисловия),
        вырезанных куратором: даёт обзорщику контекст «о книге».
        """
        joined = "\n".join(chapter_summaries)
        front_block = (
            f"\n\nСлужебные страницы книги (титул/лицензия/отзывы):\n{front_matter[:1200]}"
            if front_matter
            else ""
        )
        if self._svc._runtime is not None:
            try:
                from ...kernel.asyncio_bridge import run_coro_sync
                from .agents import source_overviewer

                ctx = AgentContext()
                out = run_coro_sync(
                    self._svc._runtime.run_structured(
                        source_overviewer, ctx, f"Книга: {title}{front_block}\n\nКонспекты глав:\n{joined}"
                    )
                )
                if out.summary.strip():
                    return out.summary.strip()
            except Exception:  # noqa: BLE001 — обзор не должен ронять summarize
                log.warning("обзор источника не сгенерировался, фолбэк на склейку", exc_info=True)
        return joined[:2000]

    def process_source(self, ref: str | int, force: bool = False) -> dict:
        """Поставить job обработки источника (PDF → главы; YouTube → транскрипт)."""
        from ....kernel.errors import Conflict
        from ..domain import SourceRules

        svc = self._svc
        with svc._uow() as uow:  # noqa: SLF001
            src = svc._sources.get(uow.session, ref)  # noqa: SLF001
            if src["status"] == "processed" and not force:
                return {
                    "ok": True,
                    "note": "уже обработан",
                    "source": src["uid"],
                    "chapters": len(svc._chapters.list(uow.session, src["id"])),  # noqa: SLF001
                }
            if not force and not SourceRules.can_process(src["status"]):
                raise Conflict(f"источник в статусе '{src['status']}' — обработка недоступна")
            now = now_iso(svc._clock)  # noqa: SLF001
            job_id = svc._jobs.enqueue(  # noqa: SLF001
                uow.session, kind="process_source", target=src["uid"], total=1, now=now
            )
            svc._sources.update(uow.session, src["id"], status="processing", updated_at=now)  # noqa: SLF001
        return {"ok": True, "job_id": job_id, "source": src["uid"]}
