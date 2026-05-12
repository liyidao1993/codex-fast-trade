from app.models import Order
from app.trading.reconcile import build_reconcile_plan


def make_order(client_order_id: str, status: str = "NEW") -> Order:
    return Order(
        client_order_id=client_order_id,
        symbol="BTCUSDT",
        side="long",
        action="open",
        exchange_side="BUY",
        order_type="LIMIT",
        price="100",
        qty="1",
        status=status,
    )


def test_reconcile_plan_classifies_local_and_exchange_orders() -> None:
    plan = build_reconcile_plan(
        [make_order("local-only"), make_order("matched"), make_order("filled", "FILLED")],
        [{"clientOrderId": "matched"}, {"clientOrderId": "exchange-only"}],
    )
    assert plan.local_missing_on_exchange == ["local-only"]
    assert plan.exchange_missing_locally == ["exchange-only"]
    assert plan.matched == ["matched"]

