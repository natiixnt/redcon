from orders.db import Database
from orders.events import EventBus
from orders.models import CANCELLED, OrderItem
from orders.repository import OrderRepository
from orders.service import OrderService


def _service():
    return OrderService(OrderRepository(Database()), EventBus())


def test_create_and_cancel():
    service = _service()
    service.create_order("o1", "c1", [OrderItem("a", 1, 100)])
    cancelled = service.cancel_order("o1")
    assert cancelled.status == CANCELLED
