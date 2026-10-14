"""Модуль «Курсы»: подборки источников/глав/блоков с прогрессом и планировщиком."""

from ...kernel.module import Module


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
        )
        register_agents(c)

    def routers(self, c):
        from .api import make_router

        return [make_router(c.courses)]

    def tools(self, c):
        from .tools import courses_tools

        return courses_tools(c)
