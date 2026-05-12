from decimal import Decimal

from app.exchanges.precision import SymbolFilters, quantize_to_step


def test_quantize_to_step_down_and_up() -> None:
    assert quantize_to_step(Decimal("43123.456"), Decimal("0.10"), "down") == Decimal("43123.4")
    assert quantize_to_step(Decimal("43123.456"), Decimal("0.10"), "up") == Decimal("43123.5")
    assert quantize_to_step(Decimal("0.123456"), Decimal("0.001"), "down") == Decimal("0.123")
    assert quantize_to_step(Decimal("0.123456"), Decimal("0.001"), "up") == Decimal("0.124")


def test_symbol_filters_from_exchange_info() -> None:
    filters = SymbolFilters.from_exchange_info(
        {
            "symbol": "BTCUSDT",
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                {"filterType": "LOT_SIZE", "stepSize": "0.001"},
                {"filterType": "MIN_NOTIONAL", "notional": "100"},
            ],
        }
    )

    assert filters.symbol == "BTCUSDT"
    assert filters.price(Decimal("100.19"), "down") == Decimal("100.1")
    assert filters.qty(Decimal("0.1239"), "down") == Decimal("0.123")
    assert filters.validate_notional(Decimal("100"), Decimal("1"))
    assert not filters.validate_notional(Decimal("99"), Decimal("1"))

