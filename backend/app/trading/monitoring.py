import json
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.exchanges.binance import BinanceClient
from app.models import Alert, MonitorEvent, MonitorRule


@dataclass(frozen=True)
class MonitorDecision:
    triggered: bool
    value: Decimal
    threshold: Decimal
    reason: str


def metric_text(metric: str) -> str:
    return {
        "quote_volume": "成交额",
        "price_change_pct": "价格涨跌幅",
        "last_price": "最新价",
    }.get(metric, metric)


def compare_metric(value: Decimal, operator: str, threshold: Decimal) -> bool:
    if operator == ">":
        return value > threshold
    if operator == ">=":
        return value >= threshold
    if operator == "<":
        return value < threshold
    if operator == "<=":
        return value <= threshold
    raise ValueError(f"unsupported operator: {operator}")


def evaluate_rule(rule: MonitorRule, metric_values: dict[str, Decimal]) -> MonitorDecision:
    if not rule.enabled:
        return MonitorDecision(False, Decimal("0"), Decimal(rule.threshold), "监控规则已关闭")
    if rule.metric not in metric_values:
        raise ValueError(f"missing metric value: {rule.metric}")
    value = metric_values[rule.metric]
    threshold = Decimal(rule.threshold)
    triggered = compare_metric(value, rule.operator, threshold)
    return MonitorDecision(triggered, value, threshold, f"{metric_text(rule.metric)} {rule.operator} {threshold}")


async def record_monitor_evaluation(
    *,
    session: AsyncSession,
    rule: MonitorRule,
    metric_values: dict[str, Decimal],
) -> MonitorEvent:
    decision = evaluate_rule(rule, metric_values)
    event = MonitorEvent(
        rule_id=rule.id,
        symbol=rule.symbol,
        metric=rule.metric,
        value=str(decision.value),
        threshold=str(decision.threshold),
        triggered=1 if decision.triggered else 0,
        payload=json.dumps({"reason": decision.reason}, ensure_ascii=False),
    )
    session.add(event)
    await session.flush()
    if decision.triggered:
        session.add(
            Alert(
                source="monitor",
                source_id=str(event.id),
                symbol=rule.symbol,
                level="warning",
                title=f"{rule.symbol} {metric_text(rule.metric)}已触发",
                message=f"{decision.value} {rule.operator} {decision.threshold}",
                payload=json.dumps({"rule_id": rule.id, "event_id": event.id, "reason": decision.reason}, ensure_ascii=False),
            )
        )
    await session.commit()
    return event


def metrics_from_24hr_ticker(ticker: dict) -> dict[str, Decimal]:
    return {
        "quote_volume": Decimal(str(ticker.get("quoteVolume", "0"))),
        "price_change_pct": Decimal(str(ticker.get("priceChangePercent", "0"))),
        "last_price": Decimal(str(ticker.get("lastPrice", "0"))),
    }


async def evaluate_rule_with_live_ticker(
    *,
    session: AsyncSession,
    rule: MonitorRule,
    client: BinanceClient | None = None,
) -> MonitorEvent:
    client = client or BinanceClient()
    ticker = await client.ticker_24hr(rule.symbol)
    return await record_monitor_evaluation(session=session, rule=rule, metric_values=metrics_from_24hr_ticker(ticker))
