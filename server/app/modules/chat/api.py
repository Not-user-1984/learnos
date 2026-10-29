"""REST чата: разговоры + SSE-эндпоинт сообщений.

Генерация живёт в фоновой задаче: при разрыве соединения ответ дорабатывает и сохраняется.
"""

import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ...kernel.errors import AppError
from .schemas import ConversationCreate, ConversationItem, ConversationPatch, MessageIn
from .service import SseEvent


def _sse(ev: SseEvent) -> str:
    return f"event: {ev.event}\ndata: {json.dumps(ev.data, ensure_ascii=False)}\n\n"


def _streaming_response(source) -> StreamingResponse:
    """SSE-обёртка: генерация живёт в фоновой задаче и не зависит от читателя.

    При обрыве соединения прокачка продолжает собирать события и сохранять ответ.
    Ошибки приложения несут свой код (conflict/…) — клиент различает «занято» и сбой.
    """
    queue: asyncio.Queue[SseEvent | None] = asyncio.Queue()

    async def pump() -> None:
        try:
            async for ev in source:
                await queue.put(ev)
        except AppError as e:  # ошибка приложения уходит клиенту как SSE error с кодом
            await queue.put(SseEvent("error", {"error": e.code, "message": e.message}))
        except Exception as e:  # noqa: BLE001 — остальное тоже уходит клиенту, не в лог молча
            await queue.put(SseEvent("error", {"error": "internal", "message": str(e)[:300]}))
        finally:
            await queue.put(None)

    task = asyncio.create_task(pump())

    async def gen():
        while True:
            ev = await queue.get()
            if ev is None:
                break
            yield _sse(ev)
        await task  # не оставляем предупреждение о незавершённой задаче

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def make_router(svc) -> APIRouter:
    """Роуты чата."""
    r = APIRouter(prefix="/conversations", tags=["chat"])

    @r.get("", response_model=list[ConversationItem])
    def list_conversations(
        mode: str | None = None,
        q: str | None = None,
        source: str | None = None,
        chapter: int | None = None,
    ):
        return [
            {
                "uid": c["uid"],
                "title": c["title"],
                "mode": c["mode"],
                "scenario": c.get("scenario", ""),
                "updated_at": c["updated_at"],
                "messages_count": c.get("messages_count", 0),
            }
            for c in svc.list_conversations(mode, q, source=source, chapter=chapter)
        ]

    @r.post("")
    def create_conversation(body: ConversationCreate):
        return svc.create_conversation(body.mode, body.activity, body.chapter, body.focus_block, body.title)

    @r.get("/{uid}")
    def get_conversation(uid: str):
        return svc.get_conversation(uid)

    @r.patch("/{uid}")
    def patch_conversation(uid: str, body: ConversationPatch):
        return svc.patch_conversation(uid, body.title)

    @r.delete("/{uid}")
    def delete_conversation(uid: str):
        return svc.delete_conversation(uid)

    @r.post("/{uid}/messages")
    async def send_message(uid: str, body: MessageIn):
        # занятый разговор — HTTP 409 до SSE: клиент показывает пояснение,
        # а сообщение-дубль не сохраняется (BUG-001)
        svc.ensure_idle(uid)

        async def source():
            async for ev in svc.stream_reply(
                uid,
                body.content,
                research=body.research,
                attachments=[a.source_uid for a in body.attachments],
                intent=body.intent,
            ):
                yield ev

        return _streaming_response(source())

    @r.post("/{uid}/resume")
    async def resume(uid: str):
        """Дописать прерванный ответ (SSE как у messages); проверки до стрима дают 409."""
        return _streaming_response(svc.resume(uid))

    @r.post("/{uid}/stop")
    def stop(uid: str):
        return svc.stop(uid)

    return r
