"""Сервис курсов: CRUD, элементы, порядок, прогресс, следующий шаг, планировщик."""

import json
import logging

from ...agent.spec import AgentContext
from ...kernel.asyncio_bridge import run_coro_sync
from ...kernel.clock import Clock, now_iso
from ...kernel.errors import NotFound, ValidationFailed
from ...kernel.ids import IdGenerator
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
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._library = library
        self._knowledge = knowledge
        self._learning = learning
        self._runtime = runtime
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
        """Удалить курс (элементы каскадом; источники и блоки не трогаем)."""
        with self._uow() as uow:
            course = self._repo.get(uow.session, ref)
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
        """Удалить элемент курса."""
        with self._uow() as uow:
            course = self._repo.get(uow.session, ref)
            self._repo.remove_item(uow.session, item_id)
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
        research = self._library.research_sources(topic, limit=5)
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
        for item in plan.get("items", []):
            item_type = item.get("item_type", "source")
            if item_type == "source" and item.get("source_uid"):
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
        return self.create_course(
            topic=plan.get("topic", "Курс"),
            title=plan.get("title"),
            description=plan.get("description"),
            category=plan.get("category"),
            items=items,
        )

    # --- прогресс ---

    def _with_progress(self, session, course: dict, with_items: bool = False) -> dict:
        items = self._repo.items(session, course["id"])
        enriched = []
        done = 0
        for item in items:
            e = {**item}
            e["done"] = self._item_done(session, item)
            if e["done"]:
                done += 1
            e["title"], e["hint"] = self._item_title(session, item)
            enriched.append(e)
        out = {**course, "items_count": len(items), "items_done": done}
        if with_items:
            out["items"] = enriched
            next_item = next((i for i in enriched if not i["done"]), None)
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

    def _item_done(self, session, item: dict) -> bool:
        """Элемент пройден: источник — активность done; глава — есть блок по главе; блок — существует."""
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

    def _resolve_source(self, session, ref) -> int:
        src = self._library.get_source(ref)
        return src["id"]

    def _out(self, session, course_id: int) -> dict:
        course = self._repo.get(session, course_id)
        return self._with_progress(session, course, with_items=True)
