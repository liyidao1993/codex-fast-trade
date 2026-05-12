import json
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import analyze_market
from app.ai.trade_draft import create_ai_trade_draft, validate_ai_draft_order
from app.config import get_settings
from app.db import get_session
from app.models import AiTradeDraft
from app.schemas import AiAnalyzeRequest, AiDraftApproveRequest, AiTradeDraftRequest, ok
from app.security import require_session, verify_pin
from app.trading.floating import submit_floating_order


router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


@router.get("/drafts")
async def list_ai_drafts(_: None = Depends(require_session), session: AsyncSession = Depends(get_session)) -> dict:
    drafts = list((await session.scalars(select(AiTradeDraft).order_by(AiTradeDraft.id.desc()))).all())
    return ok(
        [
            {
                "id": draft.id,
                "symbol": draft.symbol,
                "action": draft.action,
                "confidence": draft.confidence,
                "rationale": draft.rationale,
                "suggested_order": json.loads(draft.payload or "{}"),
                "status": draft.status,
            }
            for draft in drafts
        ]
    )


@router.post("/trade-drafts")
async def create_trade_draft(
    payload: AiTradeDraftRequest,
    _: None = Depends(require_session),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        draft = await create_ai_trade_draft(session=session, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok({"id": draft.id, "status": draft.status})


@router.post("/analyze")
async def analyze(
    payload: AiAnalyzeRequest,
    _: None = Depends(require_session),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        draft_payload = await analyze_market(payload.symbol)
        if payload.context:
            draft_payload.rationale = f"{draft_payload.rationale} context={json.dumps(payload.context, ensure_ascii=False)}"
        draft = await create_ai_trade_draft(session=session, payload=draft_payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok({"id": draft.id, "status": draft.status, "action": draft.action, "confidence": draft.confidence})


@router.post("/drafts/{draft_id}/validate")
async def validate_draft(
    draft_id: int,
    _: None = Depends(require_session),
    session: AsyncSession = Depends(get_session),
) -> dict:
    draft = await session.get(AiTradeDraft, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="AI draft not found")
    try:
        order = validate_ai_draft_order(draft, min_confidence=Decimal(get_settings().ai_min_confidence))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    draft.status = "validated"
    await session.commit()
    return ok({"id": draft.id, "status": draft.status, "order": order.model_dump(mode="json")})


@router.post("/drafts/{draft_id}/approve")
async def approve_draft(
    draft_id: int,
    payload: AiDraftApproveRequest,
    _: None = Depends(require_session),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not verify_pin(payload.pin):
        raise HTTPException(status_code=401, detail="invalid PIN")
    draft = await session.get(AiTradeDraft, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="AI draft not found")
    try:
        order = validate_ai_draft_order(draft, min_confidence=Decimal(get_settings().ai_min_confidence))
        if payload.execute:
            orders = await submit_floating_order(payload=order, session=session)
            draft.status = "executed"
            await session.commit()
            return ok({"id": draft.id, "status": draft.status, "executed": True, "orders": orders})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    draft.status = "approved"
    await session.commit()
    return ok({"id": draft.id, "status": draft.status, "executed": False, "order": order.model_dump(mode="json")})
