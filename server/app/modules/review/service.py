"""Сервис повторений: очередь на день, вопрос через Telegram-мост, оценка ответа агентом."""

import json
import logging
from datetime import timedelta

from ...agent.spec import AgentContext
from ...kernel.clock import Clock, now_iso
from ...kernel.db import UnitOfWorkFactory
from ...kernel.errors import NotFound
from .domain import queue_priority, sm2_review

log = logging.getLogger("learnos.review")


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
        """Элементы повторения для всех блоков (R-17): зрелое знание тоже закрепляется.

        Блоки со «Дозакрепить» просто стоят в очереди раньше (queue_priority).
        """
        for meta in self._kb.list_blocks(limit=500):
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
            # созревание честное для всех: проваленный блок (reps=0) тоже ждёт
            # своего due_at — лапс остывает (R-17)
            if str(it["due_at"] or "") > now:
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

    def answer(self, block_uid: str, answer_text: str, question: str | None = None) -> dict:
        """Оценить ответ (0–5), применить SM-2, слабые ответы дописывают «Дозакрепить».

        question — что именно спрашивали (R-17): экзаменатор оценивает ответ
        относительно вопроса, а не блока в целом.
        """
        from ...kernel.asyncio_bridge import run_coro_sync
        from .agents import review_examiner

        block = self._kb.get_block(block_uid)
        ctx = AgentContext(
            system_extra=f"Блок: {block.meta.title}\nСлабые места: {block.meta.weak_spots_count}"
        )
        asked = f"Вопрос, который был задан:\n{question}\n\n" if question else ""
        verdict = run_coro_sync(
            self._runtime.run_structured(
                review_examiner,
                ctx,
                "Слабые места блока: "
                f"{json.dumps(block.content[:2000], ensure_ascii=False)}\n\n"
                f"{asked}Ответ пользователя:\n{answer_text}",
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
                ease=round(ease10 * 10),  # без усечения (R-17)
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
