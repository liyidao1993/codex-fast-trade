import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.activity import recent_activity
from app.models import Alert, Base, MonitorEvent, Order, OrderEvent, ProtectionOrder, StrategyRun


@pytest.mark.asyncio
async def test_recent_activity_aggregates_local_streams() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            Order(
                client_order_id="co-activity-test",
                exchange_order_id="1",
                symbol="BTCUSDT",
                side="long",
                action="open",
                exchange_side="BUY",
                position_side="LONG",
                order_type="LIMIT",
                price="100",
                qty="1",
                status="NEW",
            )
        )
        session.add(OrderEvent(client_order_id="co-activity-test", event_type="SUBMITTED", payload="{}"))
        session.add(
            ProtectionOrder(
                parent_client_order_id="co-activity-test",
                sl_client_order_id="sl-activity-test",
                sl_status="NEW",
                sl_price="95",
                tp_client_order_id="tp-activity-test",
                tp_status="NEW",
                tp_price="110",
            )
        )
        session.add(
            MonitorEvent(
                rule_id=1,
                symbol="BTCUSDT",
                metric="quote_volume",
                value="2000000",
                threshold="1000000",
                triggered=1,
            )
        )
        session.add(
            Alert(
                source="monitor",
                source_id="1",
                symbol="BTCUSDT",
                level="warning",
                title="BTC volume triggered",
                message="2000000 > 1000000",
            )
        )
        session.add(StrategyRun(strategy_id=1, status="order", last_heartbeat="now"))
        await session.commit()

        response = await recent_activity(_=None, session=session, symbol="BTCUSDT", limit=10)
        data = response["data"]
        assert {item["source"] for item in data} == {"order", "order event", "protection", "alert", "monitor", "strategy"}
        assert any(item["tone"] == "red" for item in data)
        order_item = next(item for item in data if item["source"] == "order")
        assert order_item["cancel_client_order_id"] == "co-activity-test"
