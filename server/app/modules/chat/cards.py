"""Карточки-решения в сообщениях: стабильные id, статус на сервере, resolve (B-003).

Статус нажатой кнопки раньше жил в useState веба и терялся при перезагрузке
(«зомби-кнопки»). Теперь карточка в JSON сообщения несёт card_id/status/choice:
клик → POST /conversations/{uid}/cards/{card_id}/resolve → кнопки не возвращаются.
"""

from typing import Any

from ...kernel.errors import Conflict, NotFound

# карточки, из которых пользователь выбирает одно действие: на ход — максимум одна
DECISION_TYPES = {"action_offer", "quick_replies"}


def build_options(card: dict[str, Any]) -> list[dict[str, str]]:
    """Универсальные варианты решения: [{label, text}].

    action_offer → Да/Нет с готовыми текстами ответа; quick_replies → сами варианты;
    уже собранные options (слияние за ход) — как есть. Старым карточкам без options
    дефолты собирает веб по тем же правилам.
    """
    if card.get("options"):
        return list(card["options"])
    if card.get("type") == "action_offer":
        title = card.get("title", "")
        return [
            {"label": "Да", "text": f"Да — делай: «{title}»"},
            {"label": "Нет", "text": f"Нет, не надо: «{title}»"},
        ]
    return [{"label": r, "text": r} for r in card.get("replies") or []]


def merge_decision(existing: dict[str, Any], new: dict[str, Any]) -> None:
    """Влить варианты второй карточки-решения в первую: одна зона действий на ход."""
    opts = list(existing.get("options") or build_options(existing))
    known = {o["label"] for o in opts}
    for o in build_options(new):
        if o["label"] not in known:
            opts.append(o)
            known.add(o["label"])
    existing["options"] = opts


def ensure_card_ids(message_id: int, cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Каждой карточке — стабильный card_id; старым сообщениям id детерминированно
    из message_id и индекса (тем же правилом их найдёт resolve)."""
    for i, c in enumerate(cards):
        if isinstance(c, dict) and not c.get("card_id"):
            c["card_id"] = f"m{message_id}c{i}"
    return cards


class CardState:
    """Resolve карточек в сообщениях разговора: статус и выбор — в БД."""

    def __init__(self, uow, conversations, messages) -> None:
        self._uow = uow
        self._convs = conversations
        self._msgs = messages

    def resolve(self, conversation_uid: str, card_id: str, choice: str) -> dict:
        """Зафиксировать выбор по карточке-решению.

        Идемпотентно: повтор с тем же choice → 200 с той же карточкой; другой
        choice после решённой карточки → 409 (кнопка уже нажата).
        """
        with self._uow() as uow:
            conv = self._convs.get(uow.session, conversation_uid)
            msg_id, cards = self._msgs.find_card(uow.session, conv["id"], card_id)
            if msg_id is None:
                raise NotFound(f"карточка '{card_id}' не найдена")
            card = next(c for c in cards if c.get("card_id") == card_id)
            if card.get("status") == "resolved":
                if card.get("choice") == choice:
                    return card
                raise Conflict("решение по карточке уже принято")
            card["status"] = "resolved"
            card["choice"] = choice
            self._msgs.update_cards(uow.session, msg_id, cards)
            return card

    def mark(self, conversation_uid: str, card_id: str, status: str) -> dict | None:
        """Поставить статус карточке из чужого эндпоинта (tuning/revision):
        applied/rejected там означают то же, что resolved у решений."""
        if not conversation_uid or not card_id:
            return None
        with self._uow() as uow:
            conv = self._convs.get(uow.session, conversation_uid)
            msg_id, cards = self._msgs.find_card(uow.session, conv["id"], card_id)
            if msg_id is None:
                return None  # карточка не найдена (старая/из другого канала) — не мешаем основному действию
            card = next(c for c in cards if c.get("card_id") == card_id)
            card["status"] = status
            self._msgs.update_cards(uow.session, msg_id, cards)
            return card
