import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.exchanges.binance import BinanceClient
from app.models import Order, OrderEvent
from app.trading.chase import ChaseDecision, should_chase_order


@dataclass(frozen=True)
class ChaseConfigView:
    attempts: int
    max_attempts: int
    on_expire: Literal["cancel", "market", "keep"]
    tick_size: Decimal


async def execute_chase_once(
    *,
    order: Order,
    desired_price: Decimal,
    remaining_qty: Decimal,
    config: ChaseConfigView,
    session: AsyncSession,
    client: BinanceClient | None = None,
) -> ChaseDecision:
    client = client or BinanceClient()
    decision = should_chase_order(
        exchange_side=order.exchange_side,
        current_order_price=Decimal(order.price),
        desired_price=desired_price,
        attempts=config.attempts,
        max_attempts=config.max_attempts,
        on_expire=config.on_expire,
        remaining_qty=remaining_qty,
        tick_size=config.tick_size,
    )

    if decision.action == "replace" and decision.new_price is not None:
        await client.cancel_order(symbol=order.symbol, client_order_id=order.client_order_id)
        replacement = await client.place_order(
            symbol=order.symbol,
            side=order.exchange_side,
            order_type="LIMIT",
            quantity=remaining_qty,
            price=decision.new_price,
            position_side=order.position_side,
            post_only=True,
            reduce_only=order.action == "close",
            client_order_id=order.client_order_id,
        )
        order.price = str(decision.new_price)
        order.status = str(replacement.get("status", "REPLACED"))
        session.add(
            OrderEvent(
                client_order_id=order.client_order_id,
                event_type="CHASE_REPLACED",
                payload=json.dumps({"new_price": str(decision.new_price), "exchange": replacement}, ensure_ascii=False),
            )
        )
        await session.commit()
    elif decision.action in {"expire_cancel", "expire_market", "expire_keep", "filled", "keep"}:
        session.add(
            OrderEvent(
                client_order_id=order.client_order_id,
                event_type=f"CHASE_{decision.action.upper()}",
                payload=json.dumps({"reason": decision.reason}, ensure_ascii=False),
            )
        )
        await session.commit()

    return decision
