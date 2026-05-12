from decimal import Decimal

from app.trading.chase import should_chase_order


def test_chase_keeps_when_delta_below_tick() -> None:
    decision = should_chase_order(
        exchange_side="BUY",
        current_order_price=Decimal("100.0"),
        desired_price=Decimal("100.04"),
        attempts=0,
        max_attempts=3,
        on_expire="cancel",
        remaining_qty=Decimal("1"),
        tick_size=Decimal("0.1"),
    )
    assert decision.action == "keep"


def test_chase_replaces_when_delta_reaches_tick() -> None:
    decision = should_chase_order(
        exchange_side="BUY",
        current_order_price=Decimal("100.0"),
        desired_price=Decimal("99.8"),
        attempts=0,
        max_attempts=3,
        on_expire="cancel",
        remaining_qty=Decimal("1"),
        tick_size=Decimal("0.1"),
    )
    assert decision.action == "replace"
    assert decision.new_price == Decimal("99.8")


def test_chase_expires_by_config() -> None:
    decision = should_chase_order(
        exchange_side="SELL",
        current_order_price=Decimal("100.0"),
        desired_price=Decimal("101.0"),
        attempts=3,
        max_attempts=3,
        on_expire="market",
        remaining_qty=Decimal("1"),
        tick_size=Decimal("0.1"),
    )
    assert decision.action == "expire_market"

