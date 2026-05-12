from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, Order, ProtectionOrder
from app.trading.order_updates import handle_order_trade_update


class FakeProtectionClient:
    async def exchange_info(self):
        return {
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "filters": [
                        {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                        {"filterType": "LOT_SIZE", "stepSize": "0.001"},
                        {"filterType": "MIN_NOTIONAL", "notional": "5"},
                    ],
                }
            ]
        }

    async def place_order(self, **kwargs):
        return {"orderId": f"ex-{kwargs['client_order_id']}", "status": "NEW", **kwargs}


@pytest.mark.asyncio
async def test_order_trade_update_auto_places_protection() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        parent = Order(
            client_order_id="fl-parent",
            symbol="BTCUSDT",
            side="long",
            action="open",
            exchange_side="BUY",
            position_side="BOTH",
            order_type="LIMIT",
            price="100",
            qty="1",
            status="NEW",
            tp_pct="1",
            sl_pct="0.5",
        )
        session.add(parent)
        await session.commit()

        result = await handle_order_trade_update(
            event={"e": "ORDER_TRADE_UPDATE", "o": {"c": "fl-parent", "X": "PARTIALLY_FILLED", "z": "0.5", "ap": "100"}},
            session=session,
            client=FakeProtectionClient(),
        )

        assert result.handled
        assert result.incremental_fill_qty == Decimal("0.5")
        assert result.protection_attempted
        protection = (await session.get(ProtectionOrder, 1))
        assert protection is not None
        assert Decimal(protection.sl_price) == Decimal("99.50")
        assert Decimal(protection.tp_price) == Decimal("101.0")
