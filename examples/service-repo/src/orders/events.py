"""In-process event publishing for order lifecycle changes."""

from __future__ import annotations

from collections.abc import Callable

from orders.models import Order

Listener = Callable[[str, Order], None]


class EventBus:
    def __init__(self) -> None:
        self._listeners: list[Listener] = []

    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def publish(self, event: str, order: Order) -> None:
        for listener in self._listeners:
            listener(event, order)
