import pytest

from orders.db import Database
from orders.errors import OrderNotFound
from orders.models import Order
from orders.repository import OrderRepository


def test_save_and_get():
    repo = OrderRepository(Database())
    repo.save(Order(id="o1", customer_id="c1"))
    assert repo.get("o1").customer_id == "c1"


def test_get_missing_raises():
    repo = OrderRepository(Database())
    with pytest.raises(OrderNotFound):
        repo.get("nope")
