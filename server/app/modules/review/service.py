"""Сервис повторений: очередь на день, вопрос через Telegram-мост, оценка ответа агентом."""

import json
import logging
from datetime import timedelta

from ...agent.spec import AgentContext
from ...kernel.clock import Clock, now_iso
from ...kernel.db import UnitOfWorkFactory
from ...kernel.errors import InvalidState, NotFound
from .domain import queue_priority, sm2_review

log = logging.getLogger("learnos.review")


def _meta_has_source(meta, source_uid: str) -> bool:
    """Блок принадлежит источнику (для «Закрепить книгу», B-014)."""
    return any(s.source == source_uid for s in meta.sources)


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
        Блок с карточками живёт карточками (SM-2 на каждую, B-014) — блоковый
        элемент такому не нужен; блок без карточек — как раньше.
        """
        for meta in self._kb.list_blocks(limit=500):
            with self._uow() as uow:
                if meta.cards:
                    if self._repo.get_card(uow.session, meta.uid, meta.cards[0].id) is None:
                        self._ensure_cards(uow, meta, due_at=now_iso(self._clock))
                    if self._repo.get(uow.session, meta.uid) is not None:
                        self._repo.delete(uow.session, meta.uid)
                elif self._repo.get(uow.session, meta.uid) is None:
                    self._repo.upsert(
                        uow.session,
                        block_uid=meta.uid,
                        ease=25,
                        interval_days=1,
                        due_at=now_iso(self._clock),
                        reps=0,
                        updated_at=now_iso(self._clock),
                    )

    def _ensure_cards(self, uow, meta, due_at: str) -> None:
        """Карточные элементы блока (без перезаписи существующего прогресса)."""
        for card in meta.cards:
            if self._repo.get_card(uow.session, meta.uid, card.id) is None:
                self._repo.upsert_card(
                    uow.session,
                    block_uid=meta.uid,
                    card_id=card.id,
                    ease=25,
                    interval_days=1,
                    due_at=due_at,
                    reps=0,
                    updated_at=now_iso(self._clock),
                )

    def on_session_finished(self, event) -> None:
        """SessionFinished → элементы повторения с due_at = завтра (B-004/B-014).

        Карточки блока получают каждая свой срок; блок без карточек — один
        блоковый элемент, как раньше. Идемпотентно.
        """
        with self._uow() as uow:
            due = (self._clock.now() + timedelta(days=1)).isoformat(timespec="seconds")
            try:
                meta = self._kb.get_block(event.block_uid).meta
            except NotFound:
                return
            if meta.cards:
                self._ensure_cards(uow, meta, due_at=due)
                if self._repo.get(uow.session, event.block_uid) is not None:
                    self._repo.delete(uow.session, event.block_uid)
                return
            if self._repo.get(uow.session, event.block_uid) is not None:
                return
            self._repo.upsert(
                uow.session,
                block_uid=event.block_uid,
                ease=25,
                interval_days=1,
                due_at=due,
                reps=0,
                updated_at=now_iso(self._clock),
            )

    def stats(self, source: str | None = None) -> dict:
        """Сводка повторений для дашборда (B-004/B-005): назрело, просрочено, всего.

        Карточки и блоки без карточек считаются вместе (B-014).
        """
        self.ensure_items()
        now = now_iso(self._clock)
        today_start = (
            self._clock.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")
        )
        blocks, cards = self._collect_items(source)
        items = [*blocks, *cards]
        return {
            "due_today": sum(1 for i in items if str(i["due_at"] or "") <= now),
            "overdue": sum(1 for i in items if str(i["due_at"] or "") < today_start),
            "total": len(items),
        }

    def _collect_items(self, source: str | None) -> tuple[list[dict], list[dict]]:
        """Блоковые и карточные элементы; блок читается один раз на запрос (fix ревью B-014)."""
        with self._uow() as uow:
            block_rows = self._repo.all(uow.session)
            card_rows = self._repo.all_cards(uow.session)
        meta_cache: dict[str, object] = {}

        def meta_of(uid: str):
            if uid not in meta_cache:
                try:
                    meta_cache[uid] = self._kb.get_block(uid).meta
                except NotFound:
                    meta_cache[uid] = None
            return meta_cache[uid]

        blocks_out, cards_out = [], []
        for it in block_rows:
            meta = meta_of(it["block_uid"])
            if meta is None or meta.cards:
                continue  # блок удалён или живёт карточками (B-014)
            if source and not _meta_has_source(meta, source):
                continue
            blocks_out.append(
                {**it, "kind": "block", "title": meta.title, "weak_spots_count": meta.weak_spots_count}
            )
        for it in card_rows:
            meta = meta_of(it["block_uid"])
            if meta is None:
                continue
            card = next((c for c in meta.cards if c.id == it["card_id"]), None)
            if card is None:
                continue  # карточку удалили — элемент почистит on_block_updated
            if source and not _meta_has_source(meta, source):
                continue
            cards_out.append(
                {
                    **it,
                    "kind": "card",
                    "title": meta.title,
                    "q": card.q,
                    "a": card.a,
                    "weak_spots_count": meta.weak_spots_count,
                }
            )
        return blocks_out, cards_out

    def queue(self, limit: int = 2, source: str | None = None) -> list[dict]:
        """Очередь на день: сначала слабые, затем созревшие; source — «набор по книге» (B-014)."""
        self.ensure_items()
        now = now_iso(self._clock)
        blocks, cards = self._collect_items(source)
        items = [*blocks, *cards]
        enriched = [
            it
            for it in items
            # созревание честное для всех: проваленный элемент (reps=0) тоже ждёт
            # своего due_at — лапс остывает (R-17)
            if str(it["due_at"] or "") <= now
        ]
        enriched.sort(key=queue_priority)
        return enriched[:limit]

    def answer_card(self, block_uid: str, card_id: str, grade: str) -> dict:
        """Оценка карточки кнопкой, без LLM (B-014): «Не помню» / «Трудно» / «Помню»."""
        qualities = {"again": 1, "hard": 3, "good": 5}
        if grade not in qualities:
            raise NotFound("оценка должна быть again | hard | good")
        quality = qualities[grade]
        meta = self._kb.get_block(block_uid).meta
        if not any(c.id == card_id for c in meta.cards):
            raise NotFound(f"карточки {card_id} нет в блоке {block_uid}")
        with self._uow() as uow:
            item = self._repo.get_card(uow.session, block_uid, card_id) or {
                "ease": 25,
                "interval_days": 1,
                "reps": 0,
                "due_at": now_iso(self._clock),
            }
        ease10, interval, reps = sm2_review(quality, item["ease"] / 10, item["interval_days"], item["reps"])
        due = (self._clock.now() + timedelta(days=interval)).isoformat(timespec="seconds")
        with self._uow() as uow:
            self._repo.upsert_card(
                uow.session,
                block_uid=block_uid,
                card_id=card_id,
                ease=round(ease10 * 10),
                interval_days=interval,
                due_at=due,
                last_quality=quality,
                reps=reps,
                updated_at=now_iso(self._clock),
            )
        return {"ok": True, "grade": grade, "next_due": due, "interval_days": interval}

    def answer(
        self, block_uid: str, answer_text: str, question: str | None = None, card_id: str | None = None
    ) -> dict:
        """Оценить ответ (0–5), применить SM-2, слабые ответы дописывают «Дозакрепить».

        question — что именно спрашивали (R-17): экзаменатор оценивает ответ
        относительно вопроса, а не блока в целом.
        card_id — проговор карточки: SM-2 двигает карточный элемент, блочный
        не создаётся (fix ревью B-014). Блок с карточками без card_id — отказ:
        он закрепляется карточками, а не блоковым проговором.
        """
        from ...kernel.asyncio_bridge import run_coro_sync
        from .agents import review_examiner

        block = self._kb.get_block(block_uid)
        if card_id is not None:
            card = next((c for c in block.meta.cards if c.id == card_id), None)
            if card is None:
                raise NotFound(f"карточки {card_id} нет в блоке {block_uid}")
            return self._answer_card_by_quality(block_uid, card_id, question or card.q, answer_text)
        if block.meta.cards:
            raise InvalidState(
                "блок закрепляется карточками — проговори карточку и передай её card_id "
                "(get_review_queue отдаёт q/a и card_id)"
            )
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

    def _answer_card_by_quality(self, block_uid: str, card_id: str, question: str, answer_text: str) -> dict:
        """Проговор карточки в чате: экзаменатор ставит quality, SM-2 — карточке (B-014 fix)."""
        from ...kernel.asyncio_bridge import run_coro_sync
        from .agents import review_examiner

        verdict = run_coro_sync(
            self._runtime.run_structured(
                review_examiner,
                AgentContext(system_extra=f"Карточка блока {block_uid}"),
                f"Вопрос карточки:\n{question}\n\nОтвет пользователя:\n{answer_text}\n\n"
                "Оцени, насколько ответ передаёт суть карточки.",
            )
        )
        quality = max(0, min(5, verdict.quality))
        with self._uow() as uow:
            item = self._repo.get_card(uow.session, block_uid, card_id) or {
                "ease": 25,
                "interval_days": 1,
                "reps": 0,
                "due_at": now_iso(self._clock),
            }
        ease10, interval, reps = sm2_review(quality, item["ease"] / 10, item["interval_days"], item["reps"])
        due = (self._clock.now() + timedelta(days=interval)).isoformat(timespec="seconds")
        with self._uow() as uow:
            self._repo.upsert_card(
                uow.session,
                block_uid=block_uid,
                card_id=card_id,
                ease=round(ease10 * 10),
                interval_days=interval,
                due_at=due,
                last_quality=quality,
                reps=reps,
                updated_at=now_iso(self._clock),
            )
        return {
            "card_id": card_id,
            "quality": quality,
            "feedback": verdict.feedback,
            "next_due": due,
            "interval_days": interval,
        }

    def on_block_updated(self, event) -> None:
        """Блок обновлён: карточные элементы следуют карточкам — исчезнувшие
        card_id удаляются, пустой набор карточек чистит все (fix ревью B-014)."""
        try:
            meta = self._kb.get_block(event.block_uid).meta
        except NotFound:
            return
        with self._uow() as uow:
            self._repo.delete_card_items_except(uow.session, event.block_uid, [c.id for c in meta.cards])

    def on_block_deleted(self, event) -> None:
        """Блок удалён: элементы повторения (карточные и блочный) чистятся (fix ревью B-014)."""
        with self._uow() as uow:
            self._repo.delete_for_block(uow.session, event.block_uid)
            self._repo.delete(uow.session, event.block_uid)

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
