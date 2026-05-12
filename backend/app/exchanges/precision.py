from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Any, Literal


RoundMode = Literal["down", "up"]


@dataclass(frozen=True)
class SymbolFilters:
    symbol: str
    tick_size: Decimal
    step_size: Decimal
    min_notional: Decimal

    @classmethod
    def from_exchange_info(cls, item: dict[str, Any]) -> "SymbolFilters":
        filters = {f["filterType"]: f for f in item.get("filters", [])}
        price_filter = filters.get("PRICE_FILTER", {})
        lot_filter = filters.get("LOT_SIZE", {})
        market_lot_filter = filters.get("MARKET_LOT_SIZE", {})
        notional_filter = filters.get("MIN_NOTIONAL") or filters.get("NOTIONAL") or {}

        step_size = lot_filter.get("stepSize") or market_lot_filter.get("stepSize") or "1"
        min_notional = notional_filter.get("notional") or notional_filter.get("minNotional") or "0"

        return cls(
            symbol=str(item["symbol"]).upper(),
            tick_size=Decimal(str(price_filter.get("tickSize", "0.01"))),
            step_size=Decimal(str(step_size)),
            min_notional=Decimal(str(min_notional)),
        )

    def price(self, value: Decimal, mode: RoundMode = "down") -> Decimal:
        return quantize_to_step(value, self.tick_size, mode)

    def qty(self, value: Decimal, mode: RoundMode = "down") -> Decimal:
        return quantize_to_step(value, self.step_size, mode)

    def validate_notional(self, price: Decimal, qty: Decimal) -> bool:
        return price * qty >= self.min_notional


def quantize_to_step(value: Decimal, step: Decimal, mode: RoundMode = "down") -> Decimal:
    if step <= 0:
        raise ValueError("step must be positive")
    rounding = ROUND_FLOOR if mode == "down" else ROUND_CEILING
    units = (value / step).to_integral_value(rounding=rounding)
    return units * step

