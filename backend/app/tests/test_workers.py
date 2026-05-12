import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, MonitorEvent, MonitorRule, Strategy, StrategyRun
from app.trading.user_stream import build_user_stream_url, decode_user_stream_message
from app.trading.workers import run_monitor_cycle, run_strategy_cycle


class FakeTickerClient:
    async def ticker_24hr(self, symbol: str) -> dict:
        assert symbol == "BTCUSDT"
        return {"quoteVolume": "2500000", "priceChangePercent": "1.2", "lastPrice": "80"}


@pytest.mark.asyncio
async def test_monitor_cycle_records_enabled_rules() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            MonitorRule(
                name="volume",
                symbol="BTCUSDT",
                metric="quote_volume",
                operator=">",
                threshold="1000000",
                enabled=1,
            )
        )
        await session.commit()

        result = await run_monitor_cycle(session, client=FakeTickerClient())
        assert result.scanned == 1
        assert result.succeeded == 1
        event = await session.scalar(select(MonitorEvent))
        assert event is not None
        assert event.triggered == 1


@pytest.mark.asyncio
async def test_strategy_cycle_dry_run_creates_run_record() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            Strategy(
                name="grid",
                type="grid",
                symbol="BTCUSDT",
                params=json.dumps({"lower": "90", "upper": "110", "qty_usdt": "50"}),
                stoploss_config=json.dumps({"mode": "pct", "value": "0.5"}),
                enabled=1,
            )
        )
        await session.commit()

        result = await run_strategy_cycle(session, execute=False, client=FakeTickerClient())
        assert result.scanned == 1
        assert result.succeeded == 1
        run = await session.scalar(select(StrategyRun))
        assert run is not None
        assert run.status == "order"


def test_build_user_stream_url() -> None:
    assert build_user_stream_url("abc", "wss://example.test/ws") == "wss://example.test/ws/abc"


def test_decode_user_stream_message_accepts_bytes() -> None:
    assert decode_user_stream_message(b'{"e":"ORDER_TRADE_UPDATE"}') == {"e": "ORDER_TRADE_UPDATE"}
