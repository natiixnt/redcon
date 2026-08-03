"""Entrypoint that wires the orders service together."""

from __future__ import annotations

from orders.api import OrderApi
from orders.config import load_settings
from orders.db import Database
from orders.events import EventBus
from orders.repository import OrderRepository
from orders.service import OrderService


def build_api() -> OrderApi:
    settings = load_settings()
    assert settings.max_items_per_order > 0
    events = EventBus()
    repository = OrderRepository(Database())
    service = OrderService(repository, events)
    return OrderApi(service)


def main() -> None:
    api = build_api()
    api.create("tok_user", {"id": "o1", "customer_id": "c1", "items": []})


if __name__ == "__main__":
    main()
