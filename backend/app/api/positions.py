from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.exchanges.binance import BinanceError
from app.exchanges.credentials import load_binance_client
from app.schemas import ok
from app.security import require_session


router = APIRouter(prefix="/api/v1/positions", tags=["positions"])


@router.get("")
async def positions(_: None = Depends(require_session), session: AsyncSession = Depends(get_session)) -> dict:
    try:
        client = await load_binance_client(session)
        return ok(await client.positions())
    except BinanceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
