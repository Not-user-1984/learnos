"""In-process шина доменных событий: публикация после коммита транзакции."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("learnos.events")


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Базовое доменное событие; поля — примитивы, чтобы пережить любую шину."""

    @classmethod
    def name(cls) -> str:
        """Имя события для логов и подписок."""
        return cls.__name__


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    """Событие + контекст публикации."""

    event: DomainEvent
    publisher: str = "?"


Handler = Callable[[DomainEvent], None]


class EventBus:
    """Простой синхронный диспетчер; подписчики не должны бросать исключения."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = {}

    def subscribe(self, event_name: str, handler: Handler) -> None:
        """Подписаться на события с данным именем (см. DomainEvent.name())."""
        self._handlers.setdefault(event_name, []).append(handler)

    def publish(self, envelope: EventEnvelope) -> None:
        """Разнести событие подписчикам; ошибка подписчика логируется, не роняет вызов."""
        for handler in self._handlers.get(envelope.event.name(), []):
            try:
                handler(envelope.event)
            except Exception:  # noqa: BLE001 — подписчик не должен ломать publisher
                log.exception("handler failed for %s", envelope.event.name())


@dataclass
class PendingEvents:
    """Накопитель событий внутри транзакции."""

    events: list[EventEnvelope] = field(default_factory=list)

    def add(self, event: DomainEvent, publisher: str = "?") -> None:
        self.events.append(EventEnvelope(event=event, publisher=publisher))

    def drain(self) -> list[EventEnvelope]:
        """Забрать все события и очистить накопитель."""
        out, self.events = self.events, []
        return out


def make_event(event_type: type, **kwargs: Any) -> DomainEvent:
    """Фабрика события с проверкой полей на месте вызова."""
    return event_type(**kwargs)
