from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Alert, Base, MonitorRule
from app.trading.monitoring import compare_metric, evaluate_rule, metrics_from_24hr_ticker, record_monitor_evaluation


def test_compare_metric() -> None:
    assert compare_metric(Decimal("100"), ">", Decimal("99"))
    assert compare_metric(Decimal("100"), ">=", Decimal("100"))
    assert compare_metric(Decimal("99"), "<", Decimal("100"))
    assert compare_metric(Decimal("100"), "<=", Decimal("100"))


def test_evaluate_volume_rule_triggers() -> None:
    rule = MonitorRule(
        id=1,
        name="BTC volume",
        symbol="BTCUSDT",
        metric="quote_volume",
        operator=">",
        threshold="1000000",
        window="5m",
        enabled=1,
    )
    decision = evaluate_rule(rule, {"quote_volume": Decimal("2000000")})
    assert decision.triggered
    assert decision.value == Decimal("2000000")


def test_disabled_rule_does_not_trigger() -> None:
    rule = MonitorRule(
        id=1,
        name="disabled",
        symbol="BTCUSDT",
        metric="quote_volume",
        operator=">",
        threshold="1",
        enabled=0,
    )
    decision = evaluate_rule(rule, {"quote_volume": Decimal("2000000")})
    assert not decision.triggered


def test_metrics_from_24hr_ticker() -> None:
    metrics = metrics_from_24hr_ticker({"quoteVolume": "123.4", "priceChangePercent": "-1.2", "lastPrice": "50000"})
    assert metrics["quote_volume"] == Decimal("123.4")
    assert metrics["price_change_pct"] == Decimal("-1.2")
    assert metrics["last_price"] == Decimal("50000")


@pytest.mark.asyncio
async def test_triggered_monitor_creates_alert() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        rule = MonitorRule(
            id=1,
            name="BTC volume",
            symbol="BTCUSDT",
            metric="quote_volume",
            operator=">",
            threshold="1000000",
            enabled=1,
        )
        await record_monitor_evaluation(session=session, rule=rule, metric_values={"quote_volume": Decimal("2000000")})
        alert = await session.scalar(select(Alert))
        assert alert is not None
        assert alert.source == "monitor"
        assert alert.status == "new"
