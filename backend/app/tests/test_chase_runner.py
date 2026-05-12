from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, Order, OrderEvent
from app.trading.chase_runner import ChaseConfigView, execute_chase_once


class FakeChaseClient:
    def __init__(self) -> None:
        self.canceled = []
        self.placed = []

    async def cancel_order(self, **kwargs):
        self.canceled.append(kwargs)
        return {"status": "CANCELED"}

    async def place_order(self, **kwargs):
        self.placed.append(kwargs)
        return {"status": "NEW", "orderId": "replacement"}


@pytest.mark.asyncio
async def test_execute_chase_once_replaces_order() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        order = Order(
            client_order_id="fl-chase",
            symbol="BTCUSDT",
            side="long",
            action="open",
            exchange_side="BUY",
            order_type="LIMIT",
            price="100.0",
            qty="1",
            status="NEW",
        )
        session.add(order)
        await session.commit()

        client = FakeChaseClient()
        decision = await execute_chase_once(
            order=order,
            desired_price=Decimal("99.8"),
            remaining_qty=Decimal("1"),
            config=ChaseConfigView(attempts=0, max_attempts=3, on_expire="cancel", tick_size=Decimal("0.1")),
            session=session,
            client=client,
        )

        assert decision.action == "replace"
        assert client.canceled[0]["client_order_id"] == "fl-chase"
        assert client.placed[0]["price"] == Decimal("99.8")
        await session.refresh(order)
        assert order.price == "99.8"
        events = list((await session.scalars(select(OrderEvent))).all())
        assert events[0].event_type == "CHASE_REPLACED"

