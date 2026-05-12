from decimal import Decimal

import pytest

from app.exchanges.precision import SymbolFilters
from app.schemas import FloatingOrderRequest, LaddersConfig
from app.trading.floating import calculate_ladder_orders, choose_basis_price


FILTERS = SymbolFilters(
    symbol="BTCUSDT",
    tick_size=Decimal("0.10"),
    step_size=Decimal("0.001"),
    min_notional=Decimal("5"),
)


@pytest.mark.parametrize(
    ("side", "action", "expected"),
    [
        ("long", "open", Decimal("100")),
        ("long", "close", Decimal("101")),
        ("short", "open", Decimal("101")),
        ("short", "close", Decimal("100")),
    ],
)
def test_choose_basis_price(side: str, action: str, expected: Decimal) -> None:
    payload = FloatingOrderRequest(symbol="BTCUSDT", side=side, action=action, qty=Decimal("100"))
    assert choose_basis_price(payload, Decimal("100"), Decimal("101")) == expected


def test_long_open_floating_order_uses_bid_and_rounds_down() -> None:
    payload = FloatingOrderRequest(
        symbol="BTCUSDT",
        side="long",
        action="open",
        float_pct=Decimal("-0.10"),
        qty_mode="usdt",
        qty=Decimal("100"),
    )
    orders = calculate_ladder_orders(payload, FILTERS, bid=Decimal("100.00"), ask=Decimal("100.20"))
    assert len(orders) == 1
    assert orders[0].exchange_side == "BUY"
    assert orders[0].price == Decimal("99.90")
    assert orders[0].qty == Decimal("1.001")


def test_short_open_ladder_uses_ask_and_rounds_up() -> None:
    payload = FloatingOrderRequest(
        symbol="BTCUSDT",
        side="short",
        action="open",
        float_pct=Decimal("0.10"),
        qty_mode="base",
        qty=Decimal("0.006"),
        ladders=LaddersConfig(count=3, spacing_pct=Decimal("0.10")),
    )
    orders = calculate_ladder_orders(payload, FILTERS, bid=Decimal("100.00"), ask=Decimal("100.20"))
    assert [o.exchange_side for o in orders] == ["SELL", "SELL", "SELL"]
    assert [o.price for o in orders] == [Decimal("100.40"), Decimal("100.50"), Decimal("100.60")]
    assert [o.qty for o in orders] == [Decimal("0.002"), Decimal("0.002"), Decimal("0.002")]
