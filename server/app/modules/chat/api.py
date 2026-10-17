"""REST чата: разговоры + SSE-эндпоинт сообщений.

Генерация живёт в фоновой задаче: при разрыве соединения ответ дорабатывает и сохраняется.
"""

import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from .schemas import ConversationCreate, ConversationItem, ConversationPatch, MessageIn
from .service import SseEvent


def _sse(ev: SseEvent) -> str:
    return f"event: {ev.event}\ndata: {json.dumps(ev.data, ensure_ascii=False)}\n\n"


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
        queue: asyncio.Queue[SseEvent | None] = asyncio.Queue()

        async def pump() -> None:
            """Генерация агента → очередь; не зависит от читателя."""
            try:
                async for ev in svc.stream_reply(uid, body.content):
                    await queue.put(ev)
            except Exception as e:  # noqa: BLE001 — ошибка уходит клиенту как SSE error
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

    @r.post("/{uid}/stop")
    def stop(uid: str):
        return svc.stop(uid)

    return r
