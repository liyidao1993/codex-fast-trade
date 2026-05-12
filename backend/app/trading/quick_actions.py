import uuid
from decimal import Decimal
from typing import Any

from app.exchanges.binance import BinanceClient


def close_side_for_position(position_amt: Decimal) -> str:
    return "SELL" if position_amt > 0 else "BUY"


def reverse_open_side(position_amt: Decimal) -> str:
    return "SELL" if position_amt > 0 else "BUY"


async def close_all_positions(client: BinanceClient | None = None) -> list[dict[str, Any]]:
    client = client or BinanceClient()
    positions = await client.positions()
    results: list[dict[str, Any]] = []
    symbols = sorted({p["symbol"] for p in positions})
    for symbol in symbols:
        await client.cancel_all_open_orders(symbol)
    for position in positions:
        amt = Decimal(str(position.get("positionAmt", "0")))
        if amt == 0:
            continue
        result = await client.place_order(
            symbol=position["symbol"],
            side=close_side_for_position(amt),
            order_type="MARKET",
            quantity=abs(amt),
            reduce_only=True,
            client_order_id=f"ca-{uuid.uuid4().hex[:24]}",
        )
        results.append(result)
    return results


async def reverse_position(symbol: str, client: BinanceClient | None = None) -> dict[str, Any]:
    client = client or BinanceClient()
    symbol = symbol.upper()
    await client.cancel_all_open_orders(symbol)
    positions = await client.positions()
    position = next((p for p in positions if p.get("symbol") == symbol), None)
    if position is None:
        return {"symbol": symbol, "closed": None, "opened": None, "reason": "no position"}
    amt = Decimal(str(position.get("positionAmt", "0")))
    if amt == 0:
        return {"symbol": symbol, "closed": None, "opened": None, "reason": "flat"}

    qty = abs(amt)
    close_result = await client.place_order(
        symbol=symbol,
        side=close_side_for_position(amt),
        order_type="MARKET",
        quantity=qty,
        reduce_only=True,
        client_order_id=f"rv-close-{uuid.uuid4().hex[:20]}",
    )
    open_result = await client.place_order(
        symbol=symbol,
        side=reverse_open_side(amt),
        order_type="MARKET",
        quantity=qty,
        reduce_only=False,
        client_order_id=f"rv-open-{uuid.uuid4().hex[:21]}",
    )
    return {"symbol": symbol, "closed": close_result, "opened": open_result}

