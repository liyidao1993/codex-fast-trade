import json
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.exchanges.binance import BinanceError, map_order_intent
from app.exchanges.credentials import get_active_binance_env, is_mainnet_confirmed, load_binance_client
from app.exchanges.precision import SymbolFilters
from app.models import Order, OrderEvent, ProtectionOrder
from app.schemas import ConfirmPinRequest, FloatingOrderRequest, OrderRequest, ProtectionRequest, ReverseRequest, ok
from app.security import require_session, verify_pin
from app.trading.floating import submit_floating_order
from app.trading.guard import check_light
from app.trading.protection import create_protection_orders
from app.trading.quick_actions import close_all_positions, reverse_position


router = APIRouter(prefix="/api/v1/orders", tags=["orders"])


def serialize_order(order: Order) -> dict:
    return {
        "id": order.id,
        "client_order_id": order.client_order_id,
        "exchange_order_id": order.exchange_order_id,
        "symbol": order.symbol,
        "side": order.side,
        "action": order.action,
        "exchange_side": order.exchange_side,
        "position_side": order.position_side,
        "order_type": order.order_type,
        "price": order.price,
        "qty": order.qty,
        "executed_qty": order.executed_qty,
        "avg_price": order.avg_price,
        "status": order.status,
        "origin": order.origin,
        "strategy_run_id": order.strategy_run_id,
        "parent_order_id": order.parent_order_id,
        "tp_pct": order.tp_pct,
        "sl_pct": order.sl_pct,
        "protection_status": order.protection_status,
        "created_at": order.created_at.isoformat() if order.created_at else "",
        "updated_at": order.updated_at.isoformat() if order.updated_at else "",
    }


def serialize_order_event(event: OrderEvent) -> dict:
    return {
        "id": event.id,
        "client_order_id": event.client_order_id,
        "event_type": event.event_type,
        "payload": json.loads(event.payload or "{}"),
        "created_at": event.created_at.isoformat() if event.created_at else "",
    }


def serialize_protection_order(protection: ProtectionOrder) -> dict:
    return {
        "id": protection.id,
        "parent_client_order_id": protection.parent_client_order_id,
        "sl_client_order_id": protection.sl_client_order_id,
        "sl_exchange_order_id": protection.sl_exchange_order_id,
        "sl_status": protection.sl_status,
        "sl_price": protection.sl_price,
        "tp_client_order_id": protection.tp_client_order_id,
        "tp_exchange_order_id": protection.tp_exchange_order_id,
        "tp_status": protection.tp_status,
        "tp_price": protection.tp_price,
        "mode": protection.mode,
        "error": protection.error,
        "created_at": protection.created_at.isoformat() if protection.created_at else "",
        "updated_at": protection.updated_at.isoformat() if protection.updated_at else "",
    }


@router.get("")
async def list_orders(
    _: None = Depends(require_session),
    session: AsyncSession = Depends(get_session),
    symbol: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    statement = select(Order)
    if symbol:
        statement = statement.where(Order.symbol == symbol.upper())
    orders = list((await session.scalars(statement.order_by(Order.id.desc()).limit(limit))).all())
    return ok([serialize_order(order) for order in orders])


@router.get("/events")
async def list_order_events(
    _: None = Depends(require_session),
    session: AsyncSession = Depends(get_session),
    client_order_id: str | None = None,
    limit: int = Query(default=80, ge=1, le=300),
) -> dict:
    statement = select(OrderEvent)
    if client_order_id:
        statement = statement.where(OrderEvent.client_order_id == client_order_id)
    events = list((await session.scalars(statement.order_by(OrderEvent.id.desc()).limit(limit))).all())
    return ok([serialize_order_event(event) for event in events])


@router.get("/protections")
async def list_protection_orders(
    _: None = Depends(require_session),
    session: AsyncSession = Depends(get_session),
    parent_client_order_id: str | None = None,
    limit: int = Query(default=80, ge=1, le=300),
) -> dict:
    statement = select(ProtectionOrder)
    if parent_client_order_id:
        statement = statement.where(ProtectionOrder.parent_client_order_id == parent_client_order_id)
    protections = list((await session.scalars(statement.order_by(ProtectionOrder.id.desc()).limit(limit))).all())
    return ok([serialize_protection_order(protection) for protection in protections])


@router.delete("/{client_order_id}")
async def cancel_local_order(
    client_order_id: str,
    payload: ConfirmPinRequest,
    _: None = Depends(require_session),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not verify_pin(payload.pin):
        raise HTTPException(status_code=401, detail="invalid PIN")
    order = await session.scalar(select(Order).where(Order.client_order_id == client_order_id))
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    try:
        client = await load_binance_client(session)
        result = await client.cancel_order(symbol=order.symbol, client_order_id=client_order_id)
    except BinanceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    order.status = str(result.get("status", "CANCELED"))
    session.add(
        OrderEvent(
            client_order_id=client_order_id,
            event_type="CANCELED",
            payload=json.dumps(result, ensure_ascii=False),
        )
    )
    await session.commit()
    return ok({"client_order_id": client_order_id, "exchange": result})


@router.post("")
async def place_order(
    payload: OrderRequest,
    _: None = Depends(require_session),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if payload.type == "LIMIT" and payload.price is None:
        raise HTTPException(status_code=422, detail="LIMIT order requires price")

    order_notional = (payload.price or Decimal("0")) * payload.qty
    if payload.type == "MARKET":
        order_notional = payload.qty

    decision = check_light(
        symbol=payload.symbol,
        order_notional=order_notional,
        leverage=payload.leverage,
        is_mainnet=(await get_active_binance_env(session)) == "mainnet",
        mainnet_confirmed=await is_mainnet_confirmed(session),
    )
    if not decision.allow:
        raise HTTPException(status_code=400, detail=decision.reason)

    exchange_side, position_side = map_order_intent(payload.side, payload.action)
    client_order_id = f"co-{uuid.uuid4().hex[:24]}"

    try:
        client = await load_binance_client(session)
        exchange_result = await client.place_order(
            symbol=payload.symbol,
            side=exchange_side,
            order_type=payload.type,
            quantity=payload.qty,
            price=payload.price,
            position_side=position_side,
            post_only=payload.post_only,
            client_order_id=client_order_id,
        )
    except BinanceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    order = Order(
        client_order_id=client_order_id,
        exchange_order_id=str(exchange_result.get("orderId", "")),
        symbol=payload.symbol,
        side=payload.side,
        action=payload.action,
        exchange_side=exchange_side,
        position_side=position_side,
        order_type=payload.type,
        price=str(payload.price or ""),
        qty=str(payload.qty),
        status=str(exchange_result.get("status", "SUBMITTED")),
    )
    session.add(order)
    session.add(
        OrderEvent(
            client_order_id=client_order_id,
            event_type="SUBMITTED",
            payload=json.dumps(exchange_result, ensure_ascii=False),
        )
    )
    await session.commit()
    return ok({"client_order_id": client_order_id, "exchange": exchange_result})


@router.post("/floating")
async def place_floating_order(
    payload: FloatingOrderRequest,
    _: None = Depends(require_session),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        results = await submit_floating_order(payload=payload, session=session)
    except (BinanceError, ValueError) as exc:
        raise HTTPException(status_code=400 if isinstance(exc, ValueError) else 502, detail=str(exc)) from exc
    return ok({"orders": results})


@router.post("/close-all")
async def close_all(
    payload: ConfirmPinRequest,
    _: None = Depends(require_session),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not verify_pin(payload.pin):
        raise HTTPException(status_code=401, detail="invalid PIN")
    try:
        return ok({"orders": await close_all_positions(client=await load_binance_client(session))})
    except BinanceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/reverse")
async def reverse(
    payload: ReverseRequest,
    _: None = Depends(require_session),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not verify_pin(payload.pin):
        raise HTTPException(status_code=401, detail="invalid PIN")
    try:
        return ok(await reverse_position(payload.symbol, client=await load_binance_client(session)))
    except BinanceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/{client_order_id}/protection")
async def attach_protection(
    client_order_id: str,
    payload: ProtectionRequest,
    _: None = Depends(require_session),
    session: AsyncSession = Depends(get_session),
) -> dict:
    parent = await session.scalar(select(Order).where(Order.client_order_id == client_order_id))
    if parent is None:
        raise HTTPException(status_code=404, detail="parent order not found")
    try:
        client = await load_binance_client(session)
        info = await client.exchange_info()
        symbol_info = next((item for item in info.get("symbols", []) if item.get("symbol") == parent.symbol), None)
        if not symbol_info:
            raise ValueError(f"symbol not found in exchangeInfo: {parent.symbol}")
        protection = await create_protection_orders(
            parent=parent,
            filters=SymbolFilters.from_exchange_info(symbol_info),
            fill_qty=payload.fill_qty,
            avg_price=payload.avg_price,
            session=session,
            client=client,
        )
    except (BinanceError, ValueError) as exc:
        raise HTTPException(status_code=400 if isinstance(exc, ValueError) else 502, detail=str(exc)) from exc
    return ok(
        {
            "parent_client_order_id": protection.parent_client_order_id,
            "sl_client_order_id": protection.sl_client_order_id,
            "tp_client_order_id": protection.tp_client_order_id,
            "sl_price": protection.sl_price,
            "tp_price": protection.tp_price,
        }
    )
