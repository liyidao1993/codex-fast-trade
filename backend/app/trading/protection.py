import json
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.exchanges.binance import BinanceClient
from app.exchanges.precision import SymbolFilters
from app.models import Order, OrderEvent, ProtectionOrder


@dataclass(frozen=True)
class ProtectionPlan:
    close_side: str
    sl_price: Decimal | None
    tp_price: Decimal | None
    qty: Decimal


def close_side_for_order(parent: Order) -> str:
    return "SELL" if parent.exchange_side == "BUY" else "BUY"


def calculate_protection_plan(
    parent: Order,
    filters: SymbolFilters,
    *,
    fill_qty: Decimal,
    avg_price: Decimal,
) -> ProtectionPlan:
    close_side = close_side_for_order(parent)
    sl_pct = Decimal(parent.sl_pct) if parent.sl_pct else None
    tp_pct = Decimal(parent.tp_pct) if parent.tp_pct else None
    sl_price: Decimal | None = None
    tp_price: Decimal | None = None

    if parent.exchange_side == "BUY":
        if sl_pct is not None:
            sl_price = filters.price(avg_price * (Decimal("1") - sl_pct / Decimal("100")), "down")
        if tp_pct is not None:
            tp_price = filters.price(avg_price * (Decimal("1") + tp_pct / Decimal("100")), "up")
    else:
        if sl_pct is not None:
            sl_price = filters.price(avg_price * (Decimal("1") + sl_pct / Decimal("100")), "up")
        if tp_pct is not None:
            tp_price = filters.price(avg_price * (Decimal("1") - tp_pct / Decimal("100")), "down")

    return ProtectionPlan(close_side=close_side, sl_price=sl_price, tp_price=tp_price, qty=filters.qty(fill_qty, "down"))


async def create_protection_orders(
    *,
    parent: Order,
    filters: SymbolFilters,
    fill_qty: Decimal,
    avg_price: Decimal,
    session: AsyncSession,
    client: BinanceClient | None = None,
) -> ProtectionOrder:
    if not parent.sl_pct and not parent.tp_pct:
        raise ValueError("parent order has no TP/SL configuration")

    client = client or BinanceClient()
    plan = calculate_protection_plan(parent, filters, fill_qty=fill_qty, avg_price=avg_price)
    if plan.qty <= 0:
        raise ValueError("protection quantity is zero after precision normalization")

    protection = ProtectionOrder(
        parent_client_order_id=parent.client_order_id,
        sl_price=str(plan.sl_price or ""),
        tp_price=str(plan.tp_price or ""),
        mode="pct",
    )

    try:
        if plan.sl_price is not None:
            sl_client_id = f"sl-{uuid.uuid4().hex[:24]}"
            sl_result = await client.place_order(
                symbol=parent.symbol,
                side=plan.close_side,
                order_type="STOP_MARKET",
                quantity=plan.qty,
                position_side=parent.position_side,
                reduce_only=True,
                stop_price=plan.sl_price,
                working_type="MARK_PRICE",
                price_protect=True,
                client_order_id=sl_client_id,
            )
            protection.sl_client_order_id = sl_client_id
            protection.sl_exchange_order_id = str(sl_result.get("orderId", ""))
            protection.sl_status = str(sl_result.get("status", "SUBMITTED"))

        if plan.tp_price is not None:
            tp_client_id = f"tp-{uuid.uuid4().hex[:24]}"
            tp_result = await client.place_order(
                symbol=parent.symbol,
                side=plan.close_side,
                order_type="TAKE_PROFIT_MARKET",
                quantity=plan.qty,
                position_side=parent.position_side,
                reduce_only=True,
                stop_price=plan.tp_price,
                working_type="MARK_PRICE",
                price_protect=True,
                client_order_id=tp_client_id,
            )
            protection.tp_client_order_id = tp_client_id
            protection.tp_exchange_order_id = str(tp_result.get("orderId", ""))
            protection.tp_status = str(tp_result.get("status", "SUBMITTED"))

        parent.protection_status = "PROTECTION_PLACED"
        session.add(protection)
        session.add(
            OrderEvent(
                client_order_id=parent.client_order_id,
                event_type="PROTECTION_PLACED",
                payload=json.dumps(
                    {
                        "sl_client_order_id": protection.sl_client_order_id,
                        "tp_client_order_id": protection.tp_client_order_id,
                        "sl_price": protection.sl_price,
                        "tp_price": protection.tp_price,
                    },
                    ensure_ascii=False,
                ),
            )
        )
        await session.commit()
        return protection
    except Exception as exc:
        parent.protection_status = "PROTECTION_FAILED"
        protection.error = str(exc)
        session.add(protection)
        session.add(
            OrderEvent(
                client_order_id=parent.client_order_id,
                event_type="PROTECTION_FAILED",
                payload=json.dumps({"error": str(exc)}, ensure_ascii=False),
            )
        )
        await session.commit()
        raise


async def load_symbol_filters(client: BinanceClient, symbol: str) -> SymbolFilters:
    info = await client.exchange_info()
    symbol_info = next((item for item in info.get("symbols", []) if item.get("symbol") == symbol), None)
    if not symbol_info:
        raise ValueError(f"symbol not found in exchangeInfo: {symbol}")
    return SymbolFilters.from_exchange_info(symbol_info)
