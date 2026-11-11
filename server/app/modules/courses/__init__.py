"""Модуль «Курсы»: подборки источников/глав/блоков с прогрессом и планировщиком."""

from ...kernel.module import Module
from ..learning.events import ChapterRead, SessionFinished, SessionStarted


class CoursesModule(Module):
    """Курс — упорядоченная подборка; прогресс пересчитывается по событиям."""

    name = "courses"

    def wire(self, c) -> None:
        from .agents import register_agents
        from .infra.sql_repo import CourseRepository
        from .service import CoursesService

        c.courses = CoursesService(
            uow=c.uow,
            repo=CourseRepository(),
            library=c.library,
            knowledge=c.knowledge,
            learning=c.learning,
            runtime=c.agent_runtime,
            ids=c.ids,
            clock=c.clock,
            research=c.research,
        )
        register_agents(c)

    def routers(self, c):
        from .api import make_router

        return [make_router(c.courses, chat=c.chat)]

    def subscribe(self, bus, c) -> None:
        # доска статусов элементов курса живёт событиями (B-004): learning о курсах не знает
        bus.subscribe(SessionStarted.name(), c.courses.on_session_started)
        bus.subscribe(SessionFinished.name(), c.courses.on_session_finished)
        bus.subscribe(ChapterRead.name(), c.courses.on_chapter_read)

    def tools(self, c):
        from .tools import courses_tools

        return courses_tools(c)
