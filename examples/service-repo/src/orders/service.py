"""Order business logic: create, pay, and cancel orders."""

from __future__ import annotations

from orders.errors import InvalidTransition
from orders.events import EventBus
from orders.models import CANCELLED, PAID, Order, OrderItem
from orders.repository import OrderRepository


class OrderService:
    def __init__(self, repository: OrderRepository, events: EventBus) -> None:
        self._repository = repository
        self._events = events

    def create_order(self, order_id: str, customer_id: str, items: list[OrderItem]) -> Order:
        order = Order(id=order_id, customer_id=customer_id, items=list(items))
        self._repository.save(order)
        self._events.publish("order.created", order)
        return order

    def pay_order(self, order_id: str) -> Order:
        return self._transition(order_id, PAID, "order.paid")

    def cancel_order(self, order_id: str) -> Order:
        return self._transition(order_id, CANCELLED, "order.cancelled")

    def _transition(self, order_id: str, status: str, event: str) -> Order:
        order = self._repository.get(order_id)
        if not order.can_transition_to(status):
            raise InvalidTransition(f"{order.status} -> {status}")
        order.status = status
        self._repository.save(order)
        self._events.publish(event, order)
        return order
