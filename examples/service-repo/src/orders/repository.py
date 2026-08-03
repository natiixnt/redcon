"""Persistence for orders, layered over the in-memory database."""

from __future__ import annotations

from orders.db import Database
from orders.errors import OrderNotFound
from orders.models import Order


class OrderRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def save(self, order: Order) -> Order:
        self._db.put(order.id, order)
        return order

    def get(self, order_id: str) -> Order:
        order = self._db.get(order_id)
        if order is None:
            raise OrderNotFound(order_id)
        return order

    def list_for_customer(self, customer_id: str) -> list[Order]:
        return [o for o in self._db.all() if o.customer_id == customer_id]
