from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exchanges.binance import BinanceClient
from app.models import Order, OrderEvent


@dataclass(frozen=True)
class ReconcilePlan:
    local_missing_on_exchange: list[str]
    exchange_missing_locally: list[str]
    matched: list[str]


def build_reconcile_plan(local_orders: Iterable[Order], exchange_orders: Iterable[dict]) -> ReconcilePlan:
    local_active = {
        order.client_order_id
        for order in local_orders
        if order.status not in {"FILLED", "CANCELED", "EXPIRED", "REJECTED", "NEED_RECONCILE"}
    }
    exchange_active = {
        str(item.get("clientOrderId") or item.get("client_order_id"))
        for item in exchange_orders
        if item.get("clientOrderId") or item.get("client_order_id")
    }
    return ReconcilePlan(
        local_missing_on_exchange=sorted(local_active - exchange_active),
        exchange_missing_locally=sorted(exchange_active - local_active),
        matched=sorted(local_active & exchange_active),
    )


async def apply_reconcile_plan(
    *,
    session: AsyncSession,
    local_orders: Iterable[Order],
    exchange_orders: Iterable[dict],
) -> ReconcilePlan:
    local_orders = list(local_orders)
    plan = build_reconcile_plan(local_orders, exchange_orders)
    by_client_id = {order.client_order_id: order for order in local_orders}

    for client_order_id in plan.local_missing_on_exchange:
        order = by_client_id[client_order_id]
        order.status = "NEED_RECONCILE"
        session.add(
            OrderEvent(
                client_order_id=client_order_id,
                event_type="NEED_RECONCILE",
                payload='{"reason":"local active order missing from exchange open orders"}',
            )
        )

    for client_order_id in plan.exchange_missing_locally:
        session.add(
            OrderEvent(
                client_order_id=client_order_id,
                event_type="ORPHAN_EXCHANGE_ORDER",
                payload='{"reason":"exchange open order missing locally"}',
            )
        )

    await session.commit()
    return plan


async def reconcile_open_orders(
    *,
    session: AsyncSession,
    client: BinanceClient | None = None,
    symbol: str | None = None,
) -> ReconcilePlan:
    client = client or BinanceClient()
    local_orders = list((await session.scalars(select(Order))).all())
    exchange_orders = await client.open_orders(symbol)
    return await apply_reconcile_plan(session=session, local_orders=local_orders, exchange_orders=exchange_orders)

