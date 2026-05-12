from fastapi import APIRouter, Depends

from app.schemas import ok
from app.security import require_session
from app.trading.workers import background_supervisor


router = APIRouter(prefix="/api/v1/workers", tags=["workers"])


@router.get("/status")
async def worker_status(_: None = Depends(require_session)) -> dict:
    return ok(background_supervisor.snapshot())
