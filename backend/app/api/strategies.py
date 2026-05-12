import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Strategy, StrategyRun
from app.schemas import ConfirmPinRequest, StrategyRequest, StrategyRunOnceRequest, ok
from app.security import require_session, verify_pin
from app.strategies.runner import create_strategy_run, run_strategy_once, validate_strategy


router = APIRouter(prefix="/api/v1/strategies", tags=["strategies"])


@router.get("")
async def list_strategies(_: None = Depends(require_session), session: AsyncSession = Depends(get_session)) -> dict:
    strategies = list((await session.scalars(select(Strategy).order_by(Strategy.id.desc()))).all())
    return ok(
        [
            {
                "id": item.id,
                "name": item.name,
                "type": item.type,
                "symbol": item.symbol,
                "params": json.loads(item.params or "{}"),
                "stoploss_config": json.loads(item.stoploss_config or "{}"),
                "enabled": bool(item.enabled),
            }
            for item in strategies
        ]
    )


@router.get("/runs")
async def list_strategy_runs(
    _: None = Depends(require_session),
    session: AsyncSession = Depends(get_session),
    strategy_id: int | None = None,
    limit: int = Query(default=80, ge=1, le=300),
) -> dict:
    statement = select(StrategyRun)
    if strategy_id is not None:
        statement = statement.where(StrategyRun.strategy_id == strategy_id)
    runs = list((await session.scalars(statement.order_by(StrategyRun.id.desc()).limit(limit))).all())
    return ok(
        [
            {
                "id": run.id,
                "strategy_id": run.strategy_id,
                "status": run.status,
                "last_heartbeat": run.last_heartbeat,
                "error": run.error,
                "created_at": run.created_at.isoformat() if run.created_at else "",
                "updated_at": run.updated_at.isoformat() if run.updated_at else "",
            }
            for run in runs
        ]
    )


@router.post("")
async def create_strategy(
    payload: StrategyRequest,
    _: None = Depends(require_session),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        validate_strategy(payload.type, payload.stoploss_config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    strategy = Strategy(
        name=payload.name,
        type=payload.type,
        symbol=payload.symbol,
        params=json.dumps(payload.params, ensure_ascii=False),
        stoploss_config=json.dumps(payload.stoploss_config, ensure_ascii=False),
        enabled=1,
    )
    session.add(strategy)
    await session.commit()
    return ok({"id": strategy.id})


@router.post("/{strategy_id}/start")
async def start_strategy(
    strategy_id: int,
    payload: ConfirmPinRequest,
    _: None = Depends(require_session),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not verify_pin(payload.pin):
        raise HTTPException(status_code=401, detail="invalid PIN")
    strategy = await session.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy not found")
    try:
        run = await create_strategy_run(session=session, strategy=strategy)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok({"run_id": run.id, "status": run.status})


@router.post("/{strategy_id}/run-once")
async def run_once(
    strategy_id: int,
    payload: StrategyRunOnceRequest,
    _: None = Depends(require_session),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if payload.execute and not (payload.pin and verify_pin(payload.pin)):
        raise HTTPException(status_code=401, detail="valid PIN is required for execution")
    strategy = await session.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy not found")
    try:
        result = await run_strategy_once(session=session, strategy=strategy, execute=payload.execute)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok(result)
