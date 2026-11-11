"""Сервис курсов: CRUD, элементы, порядок, прогресс, следующий шаг, планировщик."""

import json
import logging

from ...agent.spec import AgentContext
from ...kernel.asyncio_bridge import run_coro_sync
from ...kernel.clock import Clock, now_iso
from ...kernel.errors import Conflict, NotFound, ValidationFailed
from ...kernel.ids import IdGenerator
from .events import CourseItemStatusChanged
from .infra.sql_repo import CourseRepository

log = logging.getLogger("learnos.courses")


class CoursesService:
    """Use-cases курсов. Прогресс: источник — активность done; глава — есть блок; блок — существует."""

    def __init__(
        self,
        uow,
        repo: CourseRepository,
        library,
        knowledge,
        learning,
        runtime,
        ids: IdGenerator,
        clock: Clock,
        research=None,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._library = library
        self._knowledge = knowledge
        self._learning = learning
        self._runtime = runtime
        self._research = research
        self._ids = ids
        self._clock = clock

    def create_course(
        self,
        topic: str,
        title: str | None = None,
        description: str | None = None,
        category: str | None = None,
        items: list[dict] | None = None,
        plan: dict | None = None,
    ) -> dict:
        """Создать курс (совместимо со старым create_course(topic, plan_json))."""
        uid = self._ids.new("crs")
        now = now_iso(self._clock)
        with self._uow() as uow:
            course_id = self._repo.insert(
                uow.session,
                uid=uid,
                title=title or topic,
                topic=topic,
                description=description,
                category_path=category,
                status="planned",
                plan_json=json.dumps(plan or {}, ensure_ascii=False),
                created_at=now,
                updated_at=now,
            )
            for pos, item in enumerate(items or [], 1):
                self._add_item_row(uow.session, course_id, pos, item)
            return self._out(uow.session, course_id)

    def list_courses(self) -> list[dict]:
        """Курсы с прогрессом."""
        with self._uow() as uow:
            return [self._with_progress(uow.session, c) for c in self._repo.list(uow.session)]

    def get_course(self, ref: str | int) -> dict:
        """Курс с элементами и прогрессом."""
        with self._uow() as uow:
            course = self._repo.get(uow.session, ref)
            return self._with_progress(uow.session, course, with_items=True)

    def update_course(self, ref: str | int, **values) -> dict:
        """Правка курса (title/description/status)."""
        with self._uow() as uow:
            course = self._repo.get(uow.session, ref)
            allowed = {
                k: v
                for k, v in values.items()
                if k in {"title", "description", "status", "category_path"} and v is not None
            }
            if allowed:
                self._repo.update(uow.session, course["id"], **allowed, updated_at=now_iso(self._clock))
            return self._repo.get(uow.session, ref)

    def delete_course(self, ref: str | int) -> dict:
        """Удалить курс (элементы каскадом; источники и блоки не трогаем).

        Зависимости (сессии/активности курса) проверяем явно — IntegrityError
        отдавал 500 вместо понятного 409 (R-16).
        """
        from sqlalchemy import func, select

        from ..learning.infra.tables import activities as acts
        from ..learning.infra.tables import sessions as ses

        with self._uow() as uow:
            course = self._repo.get(uow.session, ref)
            deps = []
            n_sessions = int(
                uow.session.execute(select(func.count()).where(ses.c.course_id == course["id"])).scalar_one()
            )
            if n_sessions:
                deps.append(f"сессий: {n_sessions}")
            n_acts = int(
                uow.session.execute(select(func.count()).where(acts.c.course_id == course["id"])).scalar_one()
            )
            if n_acts:
                deps.append(f"активностей: {n_acts}")
            if deps:
                raise Conflict(
                    f"курс «{course['topic']}» используют ({', '.join(deps)}) — сначала уберите зависимости"
                )
            self._repo.delete(uow.session, course["id"])
        return {"ok": True, "deleted": course["uid"]}

    def add_item(
        self,
        ref: str | int,
        item_type: str,
        source: str | int | None = None,
        chapter: int | None = None,
        block_uid: str | None = None,
        note: str | None = None,
    ) -> dict:
        """Добавить элемент (source | chapter | block)."""
        if item_type not in {"source", "chapter", "block"}:
            raise ValidationFailed(f"item_type должен быть source|chapter|block, получен '{item_type}'")
        with self._uow() as uow:
            course = self._repo.get(uow.session, ref)
            pos = self._repo.count_items(uow.session, course["id"]) + 1
            source_id = (
                self._resolve_source(uow.session, source) if item_type in {"source", "chapter"} else None
            )
            if item_type == "chapter" and chapter is None:
                raise ValidationFailed("для главы нужен chapter (номер)")
            if item_type == "block" and not block_uid:
                raise ValidationFailed("для блока нужен block_uid")
            self._add_item_row(
                uow.session,
                course["id"],
                pos,
                {
                    "item_type": item_type,
                    "source": source,
                    "source_id": source_id,
                    "chapter": chapter,
                    "block_uid": block_uid,
                    "note": note,
                },
            )
            return self._out(uow.session, course["id"])

    def remove_item(self, ref: str | int, item_id: int) -> dict:
        """Удалить элемент курса; позиции оставшихся перенумеровываются (B-004)."""
        with self._uow() as uow:
            course = self._repo.get(uow.session, ref)
            self._repo.remove_item(uow.session, item_id)
            self._repo.renumber(uow.session, course["id"])
            return self._out(uow.session, course["id"])

    def count_items_for_block(self, block_uid: str) -> int:
        """Число элементов курсов, ссылающихся на блок (для запрета удаления блока)."""
        with self._uow() as uow:
            return self._repo.count_items_for_block(uow.session, block_uid)

    def reorder(self, ref: str | int, item_ids: list[int]) -> dict:
        """Переставить элементы (список id в новом порядке)."""
        with self._uow() as uow:
            course = self._repo.get(uow.session, ref)
            self._repo.reorder(uow.session, course["id"], item_ids)
            return self._out(uow.session, course["id"])

    def plan_course(self, topic: str, constraints: str | None = None) -> dict:
        """Черновик плана курса агентом course_planner (не сохраняется)."""

        from .agents import course_planner

        sources = self._library.list_sources()
        blocks = self._knowledge.list_blocks(limit=30)
        research = self._research_web(topic)  # цепочка провайдеров, не легаси-DDG (R-30)
        brief = (
            f"Тема: {topic}\nОграничения: {constraints or 'нет'}\n\n"
            "Источники в библиотеке:\n"
            + ("\n".join(f"- uid={s['uid']} kind={s['kind']} {s['title']}" for s in sources) or "(пусто)")
            + "\n\nБлоки базы знаний:\n"
            + ("\n".join(f"- {b.uid}: {b.title}" for b in blocks) or "(пусто)")
            + "\n\nКандидаты из веба (нужно добавить, если берёшь):\n"
            + (
                "\n".join(
                    f"- {r.get('title', '?')} | {r.get('url', '')}" for r in research.get("results", [])[:5]
                )
                or "(нет)"
            )
        )
        ctx = AgentContext()
        out = run_coro_sync(self._runtime.run_structured(course_planner, ctx, brief))
        return out.model_dump()

    def create_from_plan(self, plan: dict) -> dict:
        """Создать курс из подтверждённого плана; кандидаты-ссылки добавляются в библиотеку (found)."""
        items = []
        skipped: list[str] = []
        for item in plan.get("items", []):
            item_type = item.get("item_type", "source")
            if item_type == "source" and item.get("source_uid"):
                # планировщик (LLM) мог выдумать uid: валидируем, мусор отбрасываем (R-30)
                try:
                    self._library.get_source(item["source_uid"])
                except NotFound:
                    skipped.append(str(item["source_uid"]))
                    continue
                items.append({"item_type": "source", "source": item["source_uid"], "note": item.get("note")})
            elif item_type == "web":
                created = self._library.add_source("web", item["title"], url=item.get("url"))
                items.append(
                    {
                        "item_type": "source",
                        "source": created["uid"],
                        "note": (item.get("note") or "") + " (нужно обработать)",
                    }
                )
            elif item_type == "chapter":
                items.append(
                    {
                        "item_type": "chapter",
                        "source": item.get("source_uid"),
                        "chapter": item.get("chapter"),
                        "note": item.get("note"),
                    }
                )
            elif item_type == "block" and item.get("block_uid"):
                items.append({"item_type": "block", "block_uid": item["block_uid"], "note": item.get("note")})
        out = self.create_course(
            topic=plan.get("topic", "Курс"),
            title=plan.get("title"),
            description=plan.get("description"),
            category=plan.get("category"),
            items=items,
        )
        if skipped:
            out["skipped_invalid_uids"] = skipped  # планировщик выдумал — не роняем курс (R-30)
        return out

    # --- петля обучения: доска статусов по событиям (B-004) ---

    def start_item_session(
        self, ref: str | int, item_id: int, conversation_id: int | None = None, config: dict | None = None
    ) -> dict:
        """Сессия по элементу курса: get-or-create активности источника и курсор на главе.

        Сессия получает course_item_id — её финиш закроет элемент доски.
        """
        with self._uow() as uow:
            course = self._repo.get(uow.session, ref)
            item = self._repo.item(uow.session, item_id)
            if item["course_id"] != course["id"]:
                raise NotFound(f"элемент {item_id} не принадлежит курсу '{ref}'")
            if item["item_type"] == "block":
                raise ValidationFailed("сессия по блоку не заводится — блок уже есть в базе")
            activity = self._learning.start_activity(item["source_id"], course_id=course["id"])
        return self._learning.start_session(
            course_id=course["id"],
            activity_ref=activity["id"],
            chapter_idx=item["chapter_idx"] or activity["cursor_chapter"],
            conversation_id=conversation_id,
            config=config,
            course_item_id=item_id,
        )

    def start_item_conversation(self, ref: str | int, item_id: int, chat) -> dict:
        """Разговор session-режима + сессия по элементу курса (B-005): web уходит
        в чат, агент-тьютор ведёт урок, финиш закроет элемент доски."""
        conv = chat.create_conversation(mode="session")
        session = self.start_item_session(ref, item_id, conversation_id=conv["id"])
        return {"conversation_uid": conv["uid"], "session_uid": session["session_uid"]}

    def on_session_started(self, event) -> None:
        """SessionStarted → элемент доски в doing (курс становится active)."""
        for item in self._items_for_event(event):
            self._set_item_status(item["course_id"], item["id"], "doing")

    def on_session_finished(self, event) -> None:
        """SessionFinished → элемент доски done (во всех курсах этой главы)."""
        for item in self._items_for_event(event):
            self._set_item_status(item["course_id"], item["id"], "done")

    def on_chapter_read(self, event) -> None:
        """ChapterRead («прочитал сам», quick-разбор) → read, если не done."""
        for item in self._items_for_event(event):
            if item["status"] != "done":
                self._set_item_status(item["course_id"], item["id"], "read")

    def _items_for_event(self, event) -> list[dict]:
        """Элементы, которых касается событие: точечно по course_item_id, иначе по
        паре источник/глава — одна и та же глава закрывается во всех курсах."""
        try:
            with self._uow() as uow:
                if getattr(event, "course_item_id", None):
                    return [self._repo.item(uow.session, event.course_item_id)]
                if not getattr(event, "source_uid", None) or event.chapter_idx is None:
                    return []
                source_id = self._library.get_source(event.source_uid)["id"]
                return self._repo.items_by_chapter(uow.session, source_id, event.chapter_idx)
        except NotFound:
            return []

    def _set_item_status(self, course_id: int, item_id: int, status: str) -> None:
        """Статус элемента + пересчёт статуса курса + событие (одна транзакция)."""
        with self._uow() as uow:
            item = self._repo.item(uow.session, item_id)
            if item["status"] == status:
                return
            self._repo.set_item_status(uow.session, item_id, status)
            self._recourse_status(uow.session, course_id)
            uow.emit(CourseItemStatusChanged(course_id=course_id, item_id=item_id, status=status))

    def _recourse_status(self, session, course_id: int) -> None:
        """Курс: все элементы done|read → done; есть прогресс → active; иначе planned."""
        statuses = [i["status"] for i in self._repo.items(session, course_id)]
        new = "planned"
        if statuses and all(s in {"done", "read"} for s in statuses):
            new = "done"
        elif any(s in {"doing", "done", "read"} for s in statuses):
            new = "active"
        current = self._repo.get(session, course_id)
        if current["status"] != new:
            self._repo.update(session, course_id, status=new, updated_at=now_iso(self._clock))

    # --- прогресс ---

    def _with_progress(self, session, course: dict, with_items: bool = False) -> dict:
        items = self._repo.items(session, course["id"])
        # бэкфилл старых курсов (B-004): todo-элемент, фактически пройденный,
        # получает статус при первом чтении — пересчёт один раз, дальше только статусы
        changed = False
        for item in items:
            if item["status"] == "todo" and self._legacy_item_done(session, item):
                self._repo.set_item_status(session, item["id"], "done")
                item["status"] = "done"
                changed = True
        if changed:
            self._recourse_status(session, course["id"])
            course = self._repo.get(session, course["id"])
        enriched = []
        for item in items:
            e = {**item}
            e["done"] = item["status"] in {"done", "read"}
            e["title"], e["hint"] = self._item_title(session, item)
            if item.get("source_id"):
                # uid источника — для кнопок «Читать»/«Прочитал сам» (B-005)
                e["source_uid"] = self._repo_source_uid(session, item["source_id"])
            enriched.append(e)
        passed = sum(1 for i in items if i["status"] in {"done", "read"})
        out = {**course, "items_count": len(items), "items_done": passed}
        if with_items:
            out["items"] = enriched
            next_item = next((i for i in enriched if i["status"] not in {"done", "read"}), None)
            out["next_step"] = (
                {
                    "item_id": next_item["id"],
                    "item_type": next_item["item_type"],
                    "title": next_item["title"],
                    "hint": next_item["hint"],
                }
                if next_item
                else None
            )
        return out

    def _legacy_item_done(self, session, item: dict) -> bool:
        """Деривационная проверка «элемент пройден» — только для бэкфилла старых курсов
        (до явных статусов, B-004): источник — активность done; глава — есть блок
        по главе; блок — существует."""
        if item["item_type"] == "source":
            for act in self._learning.list_activities():
                if act["source_id"] == item["source_id"] and act["status"] == "done":
                    return True
            return False
        if item["item_type"] == "chapter":
            src = self._repo_source_uid(session, item["source_id"])
            return (
                src is not None
                and self._knowledge.list_blocks(source=src, limit=100)
                and any(
                    s.chapter == item["chapter_idx"]
                    for m in self._knowledge.list_blocks(source=src, limit=100)
                    for s in m.sources
                )
            )
        if item["item_type"] == "block":
            try:
                self._knowledge.get_block(item["block_uid"])
                return True
            except NotFound:
                return False
        return False

    def _item_title(self, session, item: dict) -> tuple[str, str]:
        """Заголовок и подсказка «что делать» для элемента."""
        if item["item_type"] == "source":
            src = self._library.get_source(item["source_id"])
            return src["title"], "Пройти по книге (активность)"
        if item["item_type"] == "chapter":
            src = self._library.get_source(item["source_id"])
            ch = next((c for c in src.get("chapters", []) if c["idx"] == item["chapter_idx"]), None)
            return f"{src['title']} — гл. {item['chapter_idx']}" + (
                f": {ch['title']}" if ch else ""
            ), "Сессия или быстрый разбор главы"
        if item["item_type"] == "block":
            b = self._knowledge.get_block(item["block_uid"])
            return b.meta.title, "Перечитать блок"
        return "?", ""

    def _repo_source_uid(self, session, source_id):
        try:
            return self._library.get_source(source_id)["uid"]
        except NotFound:
            return None

    def _add_item_row(self, session, course_id: int, pos: int, item: dict) -> None:
        source_id = item.get("source_id") or (
            self._resolve_source(session, item.get("source")) if item.get("source") else None
        )
        self._repo.add_item(
            session,
            course_id,
            pos,
            item_type=item["item_type"],
            source_id=source_id,
            chapter_idx=item.get("chapter"),
            block_uid=item.get("block_uid"),
            note=item.get("note"),
        )

    def count_items_for_source(self, source_id: int) -> int:
        """Число элементов курсов по источнику (запрет удаления, R-16)."""
        from sqlalchemy import func, select

        from .infra.tables import course_items

        with self._uow() as uow:
            return int(
                uow.session.execute(
                    select(func.count()).where(course_items.c.source_id == source_id)
                ).scalar_one()
            )

    def _research_web(self, topic: str, limit: int = 5) -> dict:
        """Веб-кандидаты для плана через цепочку провайдеров (R-30)."""
        try:
            return self._research.search(topic, limit=limit)
        except Exception:  # noqa: BLE001 — поиск не критичен для планирования
            return {"results": []}

    def _resolve_source(self, session, ref) -> int:
        src = self._library.get_source(ref)
        return src["id"]

    def _out(self, session, course_id: int) -> dict:
        course = self._repo.get(session, course_id)
        return self._with_progress(session, course, with_items=True)
