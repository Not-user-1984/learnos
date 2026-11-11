"""REST курсов."""

from fastapi import APIRouter
from pydantic import BaseModel

from .schemas import CourseCreate, CourseItemIn, CoursePatch, ReorderIn


class PlanIn(BaseModel):
    """Запрос плана агентом."""

    topic: str
    constraints: str | None = None


class PlanConfirm(BaseModel):
    """Создание курса из подтверждённого плана."""

    plan: dict


class ItemSessionIn(BaseModel):
    """Сессия по элементу курса (B-004): закроет элемент при финишe."""

    config: dict = {}


def make_router(svc) -> APIRouter:
    """Роуты курсов."""
    r = APIRouter(prefix="/courses", tags=["courses"])

    @r.get("")
    def list_courses():
        return svc.list_courses()

    @r.post("")
    def create_course(body: CourseCreate):
        return svc.create_course(body.topic, body.title, body.description, body.category, body.items)

    @r.post("/plan")
    def plan(body: PlanIn):
        return svc.plan_course(body.topic, body.constraints)

    @r.post("/from-plan")
    def from_plan(body: PlanConfirm):
        return svc.create_from_plan(body.plan)

    @r.get("/{ref}")
    def get_course(ref: str):
        return svc.get_course(ref)

    @r.patch("/{ref}")
    def patch_course(ref: str, body: CoursePatch):
        return svc.update_course(ref, **body.model_dump())

    @r.delete("/{ref}")
    def delete_course(ref: str):
        return svc.delete_course(ref)

    @r.post("/{ref}/items")
    def add_item(ref: str, body: CourseItemIn):
        return svc.add_item(ref, body.item_type, body.source, body.chapter, body.block_uid, body.note)

    @r.delete("/{ref}/items/{item_id}")
    def remove_item(ref: str, item_id: int):
        return svc.remove_item(ref, item_id)

    @r.post("/{ref}/items/{item_id}/session")
    def start_item_session(ref: str, item_id: int, body: ItemSessionIn | None = None):
        """Начать сессию по элементу доски курса (B-004): финиш закроет элемент."""
        return svc.start_item_session(ref, item_id, config=(body.config if body else None))

    @r.post("/{ref}/reorder")
    def reorder(ref: str, body: ReorderIn):
        return svc.reorder(ref, body.item_ids)

    return r
