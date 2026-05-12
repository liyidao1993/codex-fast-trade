import json
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.exchanges.binance import BinanceClient, map_order_intent
from app.exchanges.credentials import get_active_binance_env, is_mainnet_confirmed, load_binance_client
from app.exchanges.precision import SymbolFilters
from app.models import Order, OrderEvent
from app.schemas import FloatingOrderRequest
from app.trading.guard import check_light


@dataclass(frozen=True)
class CalculatedOrder:
    client_order_id: str
    price: Decimal
    qty: Decimal
    exchange_side: str
    position_side: str


def choose_basis_price(payload: FloatingOrderRequest, bid: Decimal, ask: Decimal) -> Decimal:
    if payload.side == "long" and payload.action == "open":
        return bid
    if payload.side == "long" and payload.action == "close":
        return ask
    if payload.side == "short" and payload.action == "open":
        return ask
    if payload.side == "short" and payload.action == "close":
        return bid
    raise ValueError(f"Unsupported order intent: {payload.side}/{payload.action}")


def price_round_mode(exchange_side: str) -> str:
    return "down" if exchange_side == "BUY" else "up"


def apply_float_pct(base_price: Decimal, float_pct: Decimal) -> Decimal:
    return base_price * (Decimal("1") + (float_pct / Decimal("100")))


def calculate_ladder_orders(
    payload: FloatingOrderRequest,
    filters: SymbolFilters,
    *,
    bid: Decimal,
    ask: Decimal,
) -> list[CalculatedOrder]:
    exchange_side, position_side = map_order_intent(payload.side, payload.action)
    basis = choose_basis_price(payload, bid, ask)
    count = payload.ladders.count
    spacing = payload.ladders.spacing_pct
    qty_each_input = payload.qty / Decimal(count)
    orders: list[CalculatedOrder] = []

    for index in range(count):
        direction = Decimal("-1") if exchange_side == "BUY" else Decimal("1")
        ladder_offset = direction * spacing * Decimal(index)
        raw_price = apply_float_pct(basis, payload.float_pct + ladder_offset)
        price = filters.price(raw_price, price_round_mode(exchange_side))
        if payload.qty_mode == "usdt":
            raw_qty = qty_each_input / price
        else:
            raw_qty = qty_each_input
        qty = filters.qty(raw_qty, "down")
        if qty <= 0:
            raise ValueError("calculated quantity is zero after precision normalization")
        orders.append(
            CalculatedOrder(
                client_order_id=f"fl-{uuid.uuid4().hex[:24]}",
                price=price,
                qty=qty,
                exchange_side=exchange_side,
                position_side=position_side,
            )
        )
    return orders


async def submit_floating_order(
    *,
    payload: FloatingOrderRequest,
    session: AsyncSession,
    client: BinanceClient | None = None,
) -> list[dict[str, Any]]:
    client = client or await load_binance_client(session)
    ticker = await client.book_ticker(payload.symbol)
    bid = Decimal(str(ticker["bidPrice"]))
    ask = Decimal(str(ticker["askPrice"]))

    info = await client.exchange_info()
    symbol_info = next((item for item in info.get("symbols", []) if item.get("symbol") == payload.symbol), None)
    if not symbol_info:
        raise ValueError(f"symbol not found in exchangeInfo: {payload.symbol}")
    filters = SymbolFilters.from_exchange_info(symbol_info)
    calculated = calculate_ladder_orders(payload, filters, bid=bid, ask=ask)

    order_notional = sum(order.price * order.qty for order in calculated)
    decision = check_light(
        symbol=payload.symbol,
        order_notional=order_notional,
        leverage=payload.leverage,
        is_mainnet=(await get_active_binance_env(session)) == "mainnet",
        mainnet_confirmed=await is_mainnet_confirmed(session),
    )
    if not decision.allow:
        raise ValueError(decision.reason)

    results: list[dict[str, Any]] = []
    for order in calculated:
        exchange_result = await client.place_order(
            symbol=payload.symbol,
            side=order.exchange_side,
            order_type="LIMIT",
            quantity=order.qty,
            price=order.price,
            position_side=order.position_side,
            post_only=payload.post_only,
            reduce_only=payload.reduce_only,
            client_order_id=order.client_order_id,
        )
        session.add(
            Order(
                client_order_id=order.client_order_id,
                exchange_order_id=str(exchange_result.get("orderId", "")),
                symbol=payload.symbol,
                side=payload.side,
                action=payload.action,
                exchange_side=order.exchange_side,
                position_side=order.position_side,
                order_type="LIMIT",
                price=str(order.price),
                qty=str(order.qty),
                status=str(exchange_result.get("status", "SUBMITTED")),
                tp_pct=str(payload.tp_pct) if payload.tp_pct is not None else "",
                sl_pct=str(payload.sl_pct) if payload.sl_pct is not None else "",
                protection_status="PROTECTION_PENDING" if payload.tp_pct is not None or payload.sl_pct is not None else "",
            )
        )
        session.add(
            OrderEvent(
                client_order_id=order.client_order_id,
                event_type="FLOATING_SUBMITTED",
                payload=json.dumps(
                    {
                        "exchange": exchange_result,
                        "float_pct": str(payload.float_pct),
                        "tp_pct": str(payload.tp_pct) if payload.tp_pct is not None else None,
                        "sl_pct": str(payload.sl_pct) if payload.sl_pct is not None else None,
                        "chase": payload.chase.model_dump(),
                        "ladders": payload.ladders.model_dump(mode="json"),
                    },
                    ensure_ascii=False,
                ),
            )
        )
        results.append({"client_order_id": order.client_order_id, "exchange": exchange_result})
    await session.commit()
    return results
