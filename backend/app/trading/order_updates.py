import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exchanges.binance import BinanceClient
from app.models import Order, OrderEvent
from app.trading.protection import create_protection_orders, load_symbol_filters


@dataclass(frozen=True)
class OrderUpdateResult:
    handled: bool
    client_order_id: str
    status: str = ""
    incremental_fill_qty: Decimal = Decimal("0")
    protection_attempted: bool = False


def extract_order_trade_update(event: dict[str, Any]) -> dict[str, Any]:
    if event.get("e") == "ORDER_TRADE_UPDATE":
        return dict(event.get("o") or {})
    if "o" in event and isinstance(event["o"], dict):
        return dict(event["o"])
    return dict(event)


def incremental_fill(previous_executed_qty: str, new_executed_qty: str) -> Decimal:
    delta = Decimal(str(new_executed_qty or "0")) - Decimal(str(previous_executed_qty or "0"))
    return max(delta, Decimal("0"))


async def handle_order_trade_update(
    *,
    event: dict[str, Any],
    session: AsyncSession,
    client: BinanceClient | None = None,
) -> OrderUpdateResult:
    payload = extract_order_trade_update(event)
    client_order_id = str(payload.get("c") or payload.get("clientOrderId") or "")
    if not client_order_id:
        return OrderUpdateResult(False, "")

    parent = await session.scalar(select(Order).where(Order.client_order_id == client_order_id))
    if parent is None:
        return OrderUpdateResult(False, client_order_id)

    new_status = str(payload.get("X") or payload.get("status") or parent.status)
    new_executed_qty = str(payload.get("z") or payload.get("executedQty") or parent.executed_qty)
    avg_price = Decimal(str(payload.get("ap") or payload.get("avgPrice") or payload.get("L") or parent.avg_price or "0"))
    delta = incremental_fill(parent.executed_qty, new_executed_qty)

    parent.status = new_status
    parent.executed_qty = new_executed_qty
    if avg_price > 0:
        parent.avg_price = str(avg_price)
    session.add(
        OrderEvent(
            client_order_id=client_order_id,
            event_type="ORDER_TRADE_UPDATE",
            payload=json.dumps(payload, ensure_ascii=False),
        )
    )

    protection_attempted = False
    if delta > 0 and avg_price > 0 and (parent.sl_pct or parent.tp_pct):
        protection_attempted = True
        client = client or BinanceClient()
        filters = await load_symbol_filters(client, parent.symbol)
        await create_protection_orders(
            parent=parent,
            filters=filters,
            fill_qty=delta,
            avg_price=avg_price,
            session=session,
            client=client,
        )
    else:
        await session.commit()

    return OrderUpdateResult(
        True,
        client_order_id,
        status=new_status,
        incremental_fill_qty=delta,
        protection_attempted=protection_attempted,
    )

