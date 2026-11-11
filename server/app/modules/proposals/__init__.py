"""Модуль «Предложения» (B-010): задачи-идеи, ветки агентов, правки промптов — в одном месте."""

from ...kernel.module import Module


class ProposalsModule(Module):
    """Человек видит всё, что предложили агенты, и принимает/отклоняет одним кликом."""

    name = "proposals"

    def wire(self, c) -> None:
        from .service import ProposalsService

        c.proposals = ProposalsService(uow=c.uow, revision=c.revision, tuning=c.tuning, settings=c.settings)

    def routers(self, c):
        from .api import make_router

        return [make_router(c.proposals)]
