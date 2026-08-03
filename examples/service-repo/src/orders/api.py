"""HTTP-style request handlers mapping requests onto the order service."""

from __future__ import annotations

from typing import Any

from orders.auth import require_role
from orders.errors import OrderError
from orders.models import OrderItem
from orders.service import OrderService


class OrderApi:
    def __init__(self, service: OrderService) -> None:
        self._service = service

    def create(self, token: str, body: dict[str, Any]) -> dict[str, Any]:
        require_role(token, "user")
        items = [OrderItem(**item) for item in body.get("items", [])]
        order = self._service.create_order(body["id"], body["customer_id"], items)
        return {"id": order.id, "status": order.status, "total_cents": order.total_cents()}

    def cancel(self, token: str, order_id: str) -> dict[str, Any]:
        require_role(token, "admin")
        try:
            order = self._service.cancel_order(order_id)
        except OrderError as exc:
            return {"error": str(exc)}
        return {"id": order.id, "status": order.status}
