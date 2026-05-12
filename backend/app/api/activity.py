from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Alert, MonitorEvent, Order, OrderEvent, ProtectionOrder, StrategyRun
from app.schemas import ok
from app.security import require_session


router = APIRouter(prefix="/api/v1/activity", tags=["activity"])


def iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def activity_item(*, source: str, item_id: int, time: str, title: str, detail: str, tone: str = "") -> dict[str, Any]:
    return {
        "id": f"{source}-{item_id}",
        "source": source,
        "time": time,
        "title": title,
        "detail": detail,
        "tone": tone,
    }


def cancelable_order_status(status: str) -> bool:
    return status.upper() in {"NEW", "PARTIALLY_FILLED", "LOCAL_NEW", "SUBMITTED"}


def short_id(value: str) -> str:
    return f"{value[:8]}...{value[-4:]}" if len(value) > 12 else value


def side_text(value: str) -> str:
    return {"long": "做多", "short": "做空"}.get(value, value)


def action_text(value: str) -> str:
    return {"open": "开仓", "close": "平仓"}.get(value, value)


def order_type_text(value: str) -> str:
    return {
        "LIMIT": "限价",
        "MARKET": "市价",
        "STOP_MARKET": "止损市价",
        "TAKE_PROFIT_MARKET": "止盈市价",
    }.get(value.upper(), value)


def order_status_text(value: str) -> str:
    return {
        "CANCELED": "已撤单",
        "EXPIRED": "已过期",
        "FILLED": "已成交",
        "LOCAL_NEW": "本地新建",
        "NEW": "已挂单",
        "PARTIALLY_FILLED": "部分成交",
        "REJECTED": "已拒绝",
        "SUBMITTED": "已提交",
    }.get(value.upper(), value)


def alert_level_text(value: str) -> str:
    return {"warning": "警告", "error": "异常", "info": "信息"}.get(value.lower(), value)


def metric_text(value: str) -> str:
    return {
        "last_price": "最新价",
        "price_change_pct": "价格涨跌幅",
        "quote_volume": "成交额",
    }.get(value, value)


def run_status_text(value: str) -> str:
    return {
        "completed": "已完成",
        "error": "异常",
        "running": "运行中",
        "submitted": "已提交",
    }.get(value.lower(), order_status_text(value))


@router.get("/recent")
async def recent_activity(
    _: None = Depends(require_session),
    session: AsyncSession = Depends(get_session),
    symbol: str | None = None,
    limit: int = Query(default=40, ge=1, le=200),
) -> dict:
    order_statement = select(Order)
    monitor_statement = select(MonitorEvent)
    if symbol:
        normalized_symbol = symbol.upper()
        order_statement = order_statement.where(Order.symbol == normalized_symbol)
        monitor_statement = monitor_statement.where(MonitorEvent.symbol == normalized_symbol)

    orders = list((await session.scalars(order_statement.order_by(Order.id.desc()).limit(limit))).all())
    order_events = list((await session.scalars(select(OrderEvent).order_by(OrderEvent.id.desc()).limit(limit))).all())
    protections = list((await session.scalars(select(ProtectionOrder).order_by(ProtectionOrder.id.desc()).limit(limit))).all())
    alerts = list((await session.scalars(select(Alert).order_by(Alert.id.desc()).limit(limit))).all())
    monitor_events = list((await session.scalars(monitor_statement.order_by(MonitorEvent.id.desc()).limit(limit))).all())
    strategy_runs = list((await session.scalars(select(StrategyRun).order_by(StrategyRun.id.desc()).limit(limit))).all())

    items: list[dict[str, Any]] = []
    items.extend(
        {
            **activity_item(
                source="order",
                item_id=order.id,
                time=iso(order.updated_at or order.created_at),
                title=f"{order.symbol} {side_text(order.side)}/{action_text(order.action)} {order_status_text(order.status)}",
                detail=f"{order_type_text(order.order_type)} 数量 {order.qty}，成交 {order.executed_qty}，{short_id(order.client_order_id)}",
                tone="green" if order.status == "FILLED" else "",
            ),
            "cancel_client_order_id": order.client_order_id if cancelable_order_status(order.status) else "",
        }
        for order in orders
    )
    items.extend(
        activity_item(
            source="order event",
            item_id=event.id,
            time=iso(event.created_at),
            title="订单事件",
            detail=short_id(event.client_order_id),
        )
        for event in order_events
    )
    items.extend(
        activity_item(
            source="protection",
            item_id=protection.id,
            time=iso(protection.updated_at or protection.created_at),
            title=f"止盈 {order_status_text(protection.tp_status or '-')} / 止损 {order_status_text(protection.sl_status or '-')}",
            detail=f"父订单 {short_id(protection.parent_client_order_id)}，止盈 {protection.tp_price or '-'}，止损 {protection.sl_price or '-'}",
            tone="red" if protection.error else "",
        )
        for protection in protections
    )
    items.extend(
        activity_item(
            source="alert",
            item_id=alert.id,
            time=iso(alert.updated_at or alert.created_at),
            title=f"{alert_level_text(alert.level)} {alert.title}",
            detail=alert.message,
            tone="red" if alert.status == "new" else "",
        )
        for alert in alerts
    )
    items.extend(
        activity_item(
            source="monitor",
            item_id=event.id,
            time=iso(event.created_at),
            title=f"{event.symbol} {metric_text(event.metric)}",
            detail=f"{event.value} / {event.threshold}",
            tone="red" if event.triggered else "",
        )
        for event in monitor_events
    )
    items.extend(
        activity_item(
            source="strategy",
            item_id=run.id,
            time=iso(run.updated_at or run.created_at),
            title=f"策略 #{run.strategy_id} {run_status_text(run.status)}",
            detail=run.error or run.last_heartbeat or f"运行 #{run.id}",
            tone="red" if run.status == "error" else "",
        )
        for run in strategy_runs
    )
    items.sort(key=lambda item: item["time"], reverse=True)
    return ok(items[:limit])
