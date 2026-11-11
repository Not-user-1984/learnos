"""Авто-заголовок разговора (B-009)."""

import logging

from ....kernel.clock import now_iso
from ....llm.types import LLMRequest, Message

log = logging.getLogger("learnos.chat")


class TitleMaker:
    """Перенос из chat/service.py."""

    def __init__(self, svc) -> None:
        self._svc = svc

    async def _make_title(self, conv: dict, first_reply: str) -> str | None:
        """Авто-заголовок разговора (роль fast)."""
        try:
            provider, model, role_params = self._svc._router.resolve("fast")

            resp = await provider.complete(
                model,
                LLMRequest(
                    extra_params=role_params,
                    messages=(
                        Message(
                            role="system",
                            content=(
                                "Придумай заголовок разговора по-русски, ≤ 60 символов, "
                                "без кавычек. Ответь только заголовком."
                            ),
                        ),
                        Message(
                            role="user",
                            content=(conv["messages"][-1]["content"] if conv.get("messages") else "")[:500]
                            + "\n---\n"
                            + first_reply[:500],
                        ),
                    ),
                ),
            )
            title = resp.text.strip().strip('"«»')[:60]
            if title:
                with self._svc._uow() as uow:
                    self._svc._convs.update(
                        uow.session, conv["id"], title=title, updated_at=now_iso(self._svc._clock)
                    )
                return title
        except Exception:  # noqa: BLE001 — заголовок не критичен
            log.info("авто-заголовок не сработал")
        return None
