from orders.models import CANCELLED, OPEN, PAID, Order, OrderItem


def test_total_cents_sums_items():
    order = Order(id="o1", customer_id="c1", items=[OrderItem("a", 2, 500), OrderItem("b", 1, 300)])
    assert order.total_cents() == 1300


def test_transition_rules():
    order = Order(id="o1", customer_id="c1")
    assert order.status == OPEN
    assert order.can_transition_to(PAID)
    assert order.can_transition_to(CANCELLED)
    order.status = CANCELLED
    assert not order.can_transition_to(PAID)
