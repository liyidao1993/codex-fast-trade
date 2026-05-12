from decimal import Decimal

from app.exchanges.precision import SymbolFilters
from app.models import Order
from app.trading.protection import calculate_protection_plan, close_side_for_order


FILTERS = SymbolFilters(
    symbol="BTCUSDT",
    tick_size=Decimal("0.10"),
    step_size=Decimal("0.001"),
    min_notional=Decimal("5"),
)


def parent_order(exchange_side: str, tp_pct: str = "1", sl_pct: str = "0.5") -> Order:
    return Order(
        client_order_id="fl-test",
        symbol="BTCUSDT",
        side="long" if exchange_side == "BUY" else "short",
        action="open",
        exchange_side=exchange_side,
        position_side="BOTH",
        order_type="LIMIT",
        price="100",
        qty="1",
        tp_pct=tp_pct,
        sl_pct=sl_pct,
    )


def test_close_side_for_order() -> None:
    assert close_side_for_order(parent_order("BUY")) == "SELL"
    assert close_side_for_order(parent_order("SELL")) == "BUY"


def test_long_protection_prices() -> None:
    plan = calculate_protection_plan(parent_order("BUY"), FILTERS, fill_qty=Decimal("1.2345"), avg_price=Decimal("100"))
    assert plan.close_side == "SELL"
    assert plan.sl_price == Decimal("99.50")
    assert plan.tp_price == Decimal("101.0")
    assert plan.qty == Decimal("1.234")


def test_short_protection_prices() -> None:
    plan = calculate_protection_plan(parent_order("SELL"), FILTERS, fill_qty=Decimal("1"), avg_price=Decimal("100"))
    assert plan.close_side == "BUY"
    assert plan.sl_price == Decimal("100.50")
    assert plan.tp_price == Decimal("99.0")

