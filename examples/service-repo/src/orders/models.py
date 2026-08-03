"""Data models for the orders service."""

from __future__ import annotations

from dataclasses import dataclass, field

OPEN = "open"
PAID = "paid"
CANCELLED = "cancelled"

_ALLOWED = {OPEN: {PAID, CANCELLED}, PAID: {CANCELLED}, CANCELLED: set()}


@dataclass
class OrderItem:
    sku: str
    quantity: int
    unit_price_cents: int

    def subtotal_cents(self) -> int:
        return self.quantity * self.unit_price_cents


@dataclass
class Order:
    id: str
    customer_id: str
    status: str = OPEN
    items: list[OrderItem] = field(default_factory=list)

    def total_cents(self) -> int:
        return sum(item.subtotal_cents() for item in self.items)

    def can_transition_to(self, status: str) -> bool:
        return status in _ALLOWED.get(self.status, set())
