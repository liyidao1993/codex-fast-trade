from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


ChaseAction = Literal["keep", "replace", "expire_cancel", "expire_market", "expire_keep", "filled"]


@dataclass(frozen=True)
class ChaseDecision:
    action: ChaseAction
    reason: str
    new_price: Decimal | None = None


def should_chase_order(
    *,
    exchange_side: str,
    current_order_price: Decimal,
    desired_price: Decimal,
    attempts: int,
    max_attempts: int,
    on_expire: Literal["cancel", "market", "keep"],
    remaining_qty: Decimal,
    tick_size: Decimal,
) -> ChaseDecision:
    if remaining_qty <= 0:
        return ChaseDecision("filled", "order already filled")
    if attempts >= max_attempts:
        if on_expire == "cancel":
            return ChaseDecision("expire_cancel", "max attempts reached")
        if on_expire == "market":
            return ChaseDecision("expire_market", "max attempts reached")
        return ChaseDecision("expire_keep", "max attempts reached")
    if abs(desired_price - current_order_price) < tick_size:
        return ChaseDecision("keep", "price delta below one tick")
    return ChaseDecision("replace", "price moved by at least one tick", desired_price)

