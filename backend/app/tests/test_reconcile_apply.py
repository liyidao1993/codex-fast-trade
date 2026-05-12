import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, Order, OrderEvent
from app.trading.reconcile import apply_reconcile_plan


@pytest.mark.asyncio
async def test_apply_reconcile_plan_marks_missing_and_orphan_orders() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        local = Order(
            client_order_id="local-only",
            symbol="BTCUSDT",
            side="long",
            action="open",
            exchange_side="BUY",
            order_type="LIMIT",
            price="100",
            qty="1",
            status="NEW",
        )
        session.add(local)
        await session.commit()

        plan = await apply_reconcile_plan(
            session=session,
            local_orders=[local],
            exchange_orders=[{"clientOrderId": "exchange-only"}],
        )

        assert plan.local_missing_on_exchange == ["local-only"]
        assert plan.exchange_missing_locally == ["exchange-only"]
        await session.refresh(local)
        assert local.status == "NEED_RECONCILE"
        events = list((await session.scalars(select(OrderEvent))).all())
        assert {event.event_type for event in events} == {"NEED_RECONCILE", "ORPHAN_EXCHANGE_ORDER"}

