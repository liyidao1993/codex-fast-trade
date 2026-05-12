from dataclasses import dataclass
from decimal import Decimal

from app.config import get_settings


@dataclass(frozen=True)
class GuardDecision:
    allow: bool
    reason: str = ""


@dataclass(frozen=True)
class GuardRulesView:
    per_order_max_usdt: Decimal
    global_max_position_usdt: Decimal
    global_max_leverage: int
    allowed_symbols: set[str]
    forbidden_symbols: set[str]


def default_guard_rules() -> GuardRulesView:
    settings = get_settings()
    return GuardRulesView(
        per_order_max_usdt=Decimal(settings.per_order_max_usdt),
        global_max_position_usdt=Decimal(settings.global_max_position_usdt),
        global_max_leverage=settings.global_max_leverage,
        allowed_symbols=settings.allowed_symbol_set,
        forbidden_symbols=settings.forbidden_symbol_set,
    )


def check_light(
    *,
    symbol: str,
    order_notional: Decimal,
    current_position_notional: Decimal = Decimal("0"),
    leverage: int | None = None,
    rules: GuardRulesView | None = None,
    mainnet_confirmed: bool = False,
    is_mainnet: bool | None = None,
) -> GuardDecision:
    settings = get_settings()
    rules = rules or default_guard_rules()
    symbol = symbol.upper()
    mainnet_active = settings.is_mainnet if is_mainnet is None else is_mainnet

    if mainnet_active and not mainnet_confirmed:
        return GuardDecision(False, "mainnet requires explicit confirmation")
    if rules.allowed_symbols and symbol not in rules.allowed_symbols:
        return GuardDecision(False, f"{symbol} is not in allowed_symbols")
    if symbol in rules.forbidden_symbols:
        return GuardDecision(False, f"{symbol} is in forbidden_symbols")
    if order_notional > rules.per_order_max_usdt:
        return GuardDecision(False, "order notional exceeds per-order max")
    if current_position_notional + order_notional > rules.global_max_position_usdt:
        return GuardDecision(False, "position notional exceeds global max")
    if leverage is not None and leverage > rules.global_max_leverage:
        return GuardDecision(False, "leverage exceeds global max")
    return GuardDecision(True)
