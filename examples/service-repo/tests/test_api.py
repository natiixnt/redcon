import pytest

from orders.api import OrderApi
from orders.db import Database
from orders.errors import AuthError
from orders.events import EventBus
from orders.repository import OrderRepository
from orders.service import OrderService


def _api():
    return OrderApi(OrderService(OrderRepository(Database()), EventBus()))


def test_create_returns_total():
    api = _api()
    result = api.create(
        "tok_user",
        {"id": "o1", "customer_id": "c1", "items": [{"sku": "a", "quantity": 2, "unit_price_cents": 250}]},
    )
    assert result["total_cents"] == 500


def test_cancel_requires_admin():
    api = _api()
    with pytest.raises(AuthError):
        api.cancel("tok_user", "o1")
