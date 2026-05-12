import json
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, Strategy
from app.strategies.runner import build_strategy_order_request, create_strategy_run, validate_strategy


def test_validate_strategy_requires_stoploss() -> None:
    with pytest.raises(ValueError, match="stoploss_config is required"):
        validate_strategy("grid", {})


def test_validate_strategy_rejects_unknown_type() -> None:
    with pytest.raises(ValueError, match="unsupported strategy type"):
        validate_strategy("unknown", {"mode": "pct", "value": "1"})


@pytest.mark.asyncio
async def test_create_strategy_run() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        strategy = Strategy(
            name="grid",
            type="grid",
            symbol="BTCUSDT",
            params="{}",
            stoploss_config=json.dumps({"mode": "pct", "value": "0.5"}),
        )
        session.add(strategy)
        await session.commit()
        run = await create_strategy_run(session=session, strategy=strategy)
        assert run.id == 1
        assert run.status == "running"


def test_grid_strategy_builds_order_below_lower_bound() -> None:
    strategy = Strategy(
        name="grid",
        type="grid",
        symbol="BTCUSDT",
        params=json.dumps({"lower": "90", "upper": "110", "qty_usdt": "50"}),
        stoploss_config=json.dumps({"mode": "pct", "value": "0.5"}),
    )
    request = build_strategy_order_request(strategy, last_price=80)
    assert request is not None
    assert request.side == "long"
    assert request.sl_pct == Decimal("0.5")


def test_grid_strategy_holds_inside_range() -> None:
    strategy = Strategy(
        name="grid",
        type="grid",
        symbol="BTCUSDT",
        params=json.dumps({"lower": "90", "upper": "110"}),
        stoploss_config=json.dumps({"mode": "pct", "value": "0.5"}),
    )
    assert build_strategy_order_request(strategy, last_price=100) is None


def test_ai_signal_strategy_builds_short_order() -> None:
    strategy = Strategy(
        name="ai",
        type="ai_signal",
        symbol="BTCUSDT",
        params=json.dumps({"ai_action": "short", "qty_usdt": "25"}),
        stoploss_config=json.dumps({"mode": "pct", "value": "0.4"}),
    )
    request = build_strategy_order_request(strategy, last_price=100)
    assert request is not None
    assert request.side == "short"
    assert request.qty == Decimal("25")
