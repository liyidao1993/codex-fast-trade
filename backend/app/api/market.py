from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.exchanges.binance import BinanceError
from app.db import get_session
from app.exchanges.credentials import load_binance_public_client
from app.exchanges.precision import SymbolFilters
from app.schemas import ok


router = APIRouter(prefix="/api/v1/market", tags=["market"])


@router.get("/symbols")
async def symbols(session: AsyncSession = Depends(get_session)) -> dict:
    try:
        client = await load_binance_public_client(session)
        info = await client.exchange_info()
    except BinanceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    result = []
    for item in info.get("symbols", []):
        if item.get("contractType") not in (None, "PERPETUAL"):
            continue
        filters = SymbolFilters.from_exchange_info(item)
        result.append(
            {
                "symbol": filters.symbol,
                "tick_size": str(filters.tick_size),
                "step_size": str(filters.step_size),
                "min_notional": str(filters.min_notional),
            }
        )
    return ok(result)


@router.get("/ticker")
async def ticker(symbol: str, session: AsyncSession = Depends(get_session)) -> dict:
    try:
        client = await load_binance_public_client(session)
        return ok(await client.book_ticker(symbol))
    except BinanceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
