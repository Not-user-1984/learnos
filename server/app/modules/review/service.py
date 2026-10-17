"""Сервис повторений: очередь на день, вопрос через Telegram-мост, оценка ответа агентом."""

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from ...agent.spec import AgentContext
from ...kernel.clock import Clock, now_iso
from ...kernel.db import UnitOfWorkFactory
from ...kernel.errors import NotFound
from .domain import queue_priority, sm2_review

log = logging.getLogger("learnos.review")

BRIDGE = os.path.expanduser("~/.config/opencode/tools/telegram_bridge.py")


class Messenger(Protocol):
    """Порт отправки сообщений повторений (мост Telegram на маке)."""

    def send(self, text: str) -> int:
        """Отправить HTML-сообщение, вернуть message_id."""
        ...


class TelegramBridgeMessenger:
    """Отправка через CLI моста (демон остаётся единственным поллером)."""

    def send(self, text: str) -> int:
        proc = subprocess.run(
            ["python3", BRIDGE, "send", "--to", "dmitry", "--parse-mode", "HTML", "--no-preview", "--stdin"],
            input=text,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"мост не отправил: {proc.stderr[-200:]}")
        # "Sent message_id=49 chat_id=..."
        for part in proc.stdout.split():
            if part.startswith("message_id="):
                return int(part.split("=")[1])
        return 0


@dataclass
class ReviewQuestion:
    """Вопрос дня по блоку."""

    block_uid: str
    title: str
    question: str
    message_id: int | None = None


class ReviewService:
    """Use-cases повторений: очередь, вопрос, ответ → SM-2 → обновление блока."""

    def __init__(self, uow: UnitOfWorkFactory, repo, knowledge, runtime, profile, clock: Clock) -> None:
        self._uow = uow
        self._repo = repo
        self._kb = knowledge
        self._runtime = runtime
        self._profile = profile
        self._clock = clock

    def ensure_items(self) -> None:
        """Создать элементы повторения для блоков со «Дозакрепить», которых ещё нет."""
        for meta in self._kb.list_blocks(limit=500):
            if meta.weak_spots_count < 1:
                continue
            with self._uow() as uow:
                if self._repo.get(uow.session, meta.uid) is None:
                    self._repo.upsert(
                        uow.session,
                        block_uid=meta.uid,
                        ease=25,
                        interval_days=1,
                        due_at=now_iso(self._clock),
                        reps=0,
                        updated_at=now_iso(self._clock),
                    )

    def queue(self, limit: int = 2) -> list[dict]:
        """Очередь на день: сначала слабые, затем созревшие."""
        self.ensure_items()
        now = now_iso(self._clock)
        with self._uow() as uow:
            items = self._repo.all(uow.session)
        enriched = []
        for it in items:
            if it["due_at"] > now and it.get("reps", 0) > 0:
                continue
            try:
                block = self._kb.get_block(it["block_uid"])
            except NotFound:
                continue
            enriched.append(
                {**it, "title": block.meta.title, "weak_spots_count": block.meta.weak_spots_count}
            )
        enriched.sort(key=queue_priority)
        return enriched[:limit]

    def ask(self, block_uid: str | None = None, messenger: Messenger | None = None) -> ReviewQuestion:
        """Сформулировать вопрос (review_examiner) и отправить в Telegram."""
        target = block_uid or (self.queue(1) or [None])[0]
        if not target:
            raise NotFound("очередь повторений пуста")
        uid = target if isinstance(target, str) else target["block_uid"]
        block = self._kb.get_block(uid)
        question = self._make_question(block)
        messenger = messenger or TelegramBridgeMessenger()
        public_url = "http://localhost:3000"
        html = (
            f"<b>Повторение · {block.meta.title}</b>\n\n{question}\n\n"
            f'Ответь reply на это сообщение. <a href="{public_url}/kb/{uid}">блок</a>'
        )
        message_id = messenger.send(html)
        return ReviewQuestion(block_uid=uid, title=block.meta.title, question=question, message_id=message_id)

    def answer(self, block_uid: str, answer_text: str) -> dict:
        """Оценить ответ (0–5), применить SM-2, слабые ответы дописывают «Дозакрепить»."""
        from ...kernel.asyncio_bridge import run_coro_sync
        from .agents import review_examiner

        block = self._kb.get_block(block_uid)
        ctx = AgentContext(
            system_extra=f"Блок: {block.meta.title}\nСлабые места: {block.meta.weak_spots_count}"
        )
        verdict = run_coro_sync(
            self._runtime.run_structured(
                review_examiner,
                ctx,
                "Слабые места блока: "
                f"{json.dumps(block.content[:2000], ensure_ascii=False)}\n\n"
                f"Вопрос был задан по блоку. Ответ пользователя:\n{answer_text}",
            )
        )
        quality = max(0, min(5, verdict.quality))
        feedback = verdict.feedback

        with self._uow() as uow:
            item = self._repo.get(uow.session, block_uid) or {
                "ease": 25,
                "interval_days": 1,
                "reps": 0,
                "due_at": now_iso(self._clock),
            }
        ease10, interval, reps = sm2_review(quality, item["ease"] / 10, item["interval_days"], item["reps"])
        due = (self._clock.now() + timedelta(days=interval)).isoformat(timespec="seconds")
        with self._uow() as uow:
            self._repo.upsert(
                uow.session,
                block_uid=block_uid,
                ease=int(ease10 * 10),
                interval_days=interval,
                due_at=due,
                last_quality=quality,
                reps=reps,
                updated_at=now_iso(self._clock),
            )
        if quality < 3:
            try:
                self._kb.update_block(
                    block_uid,
                    {"append_weak_spots": [f"повторение {now_iso(self._clock)[:10]}: ответ был слабым"]},
                    "слабый ответ в повторении",
                )
            except Exception:  # noqa: BLE001 — правка блока не критична
                log.warning("не удалось дописать «Дозакрепить»")
        return {"quality": quality, "feedback": feedback, "next_due": due, "interval_days": interval}

    def _make_question(self, block) -> str:
        from ...kernel.asyncio_bridge import run_coro_sync
        from .agents import review_examiner

        ctx = AgentContext(system_extra=f"Блок: {block.meta.title}")
        verdict = run_coro_sync(
            self._runtime.run_structured(
                review_examiner,
                ctx,
                "Сформулируй ОДИН вопрос «объясни своими словами» по блоку "
                f"(особенно по слабым местам):\n{block.content[:2500]}",
            )
        )
        return verdict.feedback or f"Объясни своими словами: {block.meta.title}"
