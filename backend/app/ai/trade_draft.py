import json
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AiTradeDraft
from app.schemas import AiTradeDraftRequest, FloatingOrderRequest
from app.trading.guard import check_light


def validate_ai_trade_draft(payload: AiTradeDraftRequest) -> None:
    if payload.confidence < Decimal("0") or payload.confidence > Decimal("1"):
        raise ValueError("confidence must be between 0 and 1")
    if payload.action != "hold" and not payload.suggested_order:
        raise ValueError("suggested_order is required unless action is hold")


async def create_ai_trade_draft(*, session: AsyncSession, payload: AiTradeDraftRequest) -> AiTradeDraft:
    validate_ai_trade_draft(payload)
    draft = AiTradeDraft(
        symbol=payload.symbol,
        action=payload.action,
        confidence=str(payload.confidence),
        rationale=payload.rationale,
        payload=json.dumps(payload.suggested_order, ensure_ascii=False),
        status="draft",
    )
    session.add(draft)
    await session.commit()
    return draft


def draft_to_floating_order(draft: AiTradeDraft) -> FloatingOrderRequest:
    if draft.action == "hold":
        raise ValueError("hold draft cannot be approved as an order")
    suggested = json.loads(draft.payload or "{}")
    if draft.action == "long_open":
        side = "long"
        action = "open"
    elif draft.action == "short_open":
        side = "short"
        action = "open"
    elif draft.action == "close":
        side = suggested.get("side")
        action = "close"
        if side not in {"long", "short"}:
            raise ValueError("close draft requires suggested_order.side")
    else:
        raise ValueError(f"unsupported AI draft action: {draft.action}")
    return FloatingOrderRequest(
        symbol=draft.symbol,
        side=side,
        action=action,
        float_pct=Decimal(str(suggested.get("float_pct", "0"))),
        qty_mode=suggested.get("qty_mode", "usdt"),
        qty=Decimal(str(suggested.get("qty", suggested.get("qty_usdt", "0")))),
        tp_pct=Decimal(str(suggested["tp_pct"])) if suggested.get("tp_pct") is not None else None,
        sl_pct=Decimal(str(suggested["sl_pct"])) if suggested.get("sl_pct") is not None else None,
        post_only=bool(suggested.get("post_only", True)),
        reduce_only=bool(suggested.get("reduce_only", action == "close")),
    )


def validate_ai_draft_order(draft: AiTradeDraft, *, min_confidence: Decimal) -> FloatingOrderRequest:
    if draft.status not in {"draft", "validated", "approved"}:
        raise ValueError(f"draft status does not allow approval: {draft.status}")
    confidence = Decimal(str(draft.confidence))
    if confidence < min_confidence:
        raise ValueError(f"confidence below minimum: {confidence} < {min_confidence}")
    order = draft_to_floating_order(draft)
    if order.qty <= 0:
        raise ValueError("AI draft order quantity must be greater than zero")
    notional = order.qty if order.qty_mode == "usdt" else Decimal("0")
    decision = check_light(symbol=order.symbol, order_notional=notional, leverage=order.leverage)
    if not decision.allow:
        raise ValueError(decision.reason)
    if order.sl_pct is None:
        raise ValueError("AI draft order requires sl_pct")
    return order
