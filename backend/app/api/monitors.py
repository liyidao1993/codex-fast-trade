from decimal import Decimal

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Alert, MonitorEvent, MonitorRule
from app.schemas import MonitorEvaluateRequest, MonitorRuleRequest, ok
from app.security import require_session
from app.trading.monitoring import evaluate_rule_with_live_ticker, record_monitor_evaluation


router = APIRouter(prefix="/api/v1/monitors", tags=["monitors"])


def serialize_alert(alert: Alert) -> dict:
    return {
        "id": alert.id,
        "source": alert.source,
        "source_id": alert.source_id,
        "symbol": alert.symbol,
        "level": alert.level,
        "title": alert.title,
        "message": alert.message,
        "status": alert.status,
        "payload": json.loads(alert.payload or "{}"),
        "created_at": alert.created_at.isoformat() if alert.created_at else "",
        "updated_at": alert.updated_at.isoformat() if alert.updated_at else "",
    }


@router.get("")
async def list_monitors(_: None = Depends(require_session), session: AsyncSession = Depends(get_session)) -> dict:
    rules = list((await session.scalars(select(MonitorRule).order_by(MonitorRule.id.desc()))).all())
    return ok(
        [
            {
                "id": rule.id,
                "name": rule.name,
                "symbol": rule.symbol,
                "metric": rule.metric,
                "operator": rule.operator,
                "threshold": rule.threshold,
                "window": rule.window,
                "enabled": bool(rule.enabled),
            }
            for rule in rules
        ]
    )


@router.get("/events")
async def list_monitor_events(
    _: None = Depends(require_session),
    session: AsyncSession = Depends(get_session),
    symbol: str | None = None,
    limit: int = Query(default=80, ge=1, le=300),
) -> dict:
    statement = select(MonitorEvent)
    if symbol:
        statement = statement.where(MonitorEvent.symbol == symbol.upper())
    events = list((await session.scalars(statement.order_by(MonitorEvent.id.desc()).limit(limit))).all())
    return ok(
        [
            {
                "id": event.id,
                "rule_id": event.rule_id,
                "symbol": event.symbol,
                "metric": event.metric,
                "value": event.value,
                "threshold": event.threshold,
                "triggered": bool(event.triggered),
                "payload": json.loads(event.payload or "{}"),
                "created_at": event.created_at.isoformat() if event.created_at else "",
            }
            for event in events
        ]
    )


@router.get("/alerts")
async def list_alerts(
    _: None = Depends(require_session),
    session: AsyncSession = Depends(get_session),
    symbol: str | None = None,
    status: str | None = None,
    limit: int = Query(default=80, ge=1, le=300),
) -> dict:
    statement = select(Alert)
    if symbol:
        statement = statement.where(Alert.symbol == symbol.upper())
    if status:
        statement = statement.where(Alert.status == status)
    alerts = list((await session.scalars(statement.order_by(Alert.id.desc()).limit(limit))).all())
    return ok([serialize_alert(alert) for alert in alerts])


@router.post("/alerts/{alert_id}/ack")
async def ack_alert(
    alert_id: int,
    _: None = Depends(require_session),
    session: AsyncSession = Depends(get_session),
) -> dict:
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    alert.status = "acked"
    await session.commit()
    await session.refresh(alert)
    return ok(serialize_alert(alert))


@router.post("")
async def create_monitor(
    payload: MonitorRuleRequest,
    _: None = Depends(require_session),
    session: AsyncSession = Depends(get_session),
) -> dict:
    rule = MonitorRule(
        name=payload.name,
        symbol=payload.symbol,
        metric=payload.metric,
        operator=payload.operator,
        threshold=str(payload.threshold),
        window=payload.window,
        enabled=1 if payload.enabled else 0,
    )
    session.add(rule)
    await session.commit()
    return ok({"id": rule.id})


@router.post("/{rule_id}/evaluate")
async def evaluate_monitor(
    rule_id: int,
    payload: MonitorEvaluateRequest,
    _: None = Depends(require_session),
    session: AsyncSession = Depends(get_session),
) -> dict:
    rule = await session.get(MonitorRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="monitor rule not found")
    try:
        event = await record_monitor_evaluation(
            session=session,
            rule=rule,
            metric_values={key: Decimal(value) for key, value in payload.metric_values.items()},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok({"event_id": event.id, "triggered": bool(event.triggered), "value": event.value})


@router.post("/{rule_id}/evaluate-live")
async def evaluate_monitor_live(
    rule_id: int,
    _: None = Depends(require_session),
    session: AsyncSession = Depends(get_session),
) -> dict:
    rule = await session.get(MonitorRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="monitor rule not found")
    try:
        event = await evaluate_rule_with_live_ticker(session=session, rule=rule)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok({"event_id": event.id, "triggered": bool(event.triggered), "value": event.value})
