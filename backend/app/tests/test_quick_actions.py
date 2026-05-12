from decimal import Decimal

from app.trading.quick_actions import close_side_for_position, reverse_open_side


def test_close_side_for_position() -> None:
    assert close_side_for_position(Decimal("0.5")) == "SELL"
    assert close_side_for_position(Decimal("-0.5")) == "BUY"


def test_reverse_open_side_matches_opposite_direction() -> None:
    assert reverse_open_side(Decimal("0.5")) == "SELL"
    assert reverse_open_side(Decimal("-0.5")) == "BUY"

