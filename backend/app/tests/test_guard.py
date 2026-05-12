from decimal import Decimal

from app.trading.guard import GuardRulesView, check_light


RULES = GuardRulesView(
    per_order_max_usdt=Decimal("500"),
    global_max_position_usdt=Decimal("5000"),
    global_max_leverage=10,
    allowed_symbols={"BTCUSDT", "ETHUSDT"},
    forbidden_symbols={"DOGEUSDT"},
)


def test_guard_allows_valid_order() -> None:
    decision = check_light(symbol="BTCUSDT", order_notional=Decimal("100"), leverage=5, rules=RULES)
    assert decision.allow


def test_guard_rejects_unlisted_symbol() -> None:
    decision = check_light(symbol="SOLUSDT", order_notional=Decimal("100"), rules=RULES)
    assert not decision.allow
    assert "allowed_symbols" in decision.reason


def test_guard_rejects_forbidden_symbol() -> None:
    decision = check_light(symbol="DOGEUSDT", order_notional=Decimal("100"), rules=RULES)
    assert not decision.allow
    assert "allowed_symbols" in decision.reason or "forbidden_symbols" in decision.reason


def test_guard_rejects_order_and_position_limits() -> None:
    too_large = check_light(symbol="BTCUSDT", order_notional=Decimal("501"), rules=RULES)
    assert not too_large.allow

    too_much_position = check_light(
        symbol="BTCUSDT",
        order_notional=Decimal("100"),
        current_position_notional=Decimal("4950"),
        rules=RULES,
    )
    assert not too_much_position.allow


def test_guard_rejects_high_leverage() -> None:
    decision = check_light(symbol="BTCUSDT", order_notional=Decimal("100"), leverage=20, rules=RULES)
    assert not decision.allow
    assert "leverage" in decision.reason

