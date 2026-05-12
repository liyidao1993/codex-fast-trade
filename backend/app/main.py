from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import activity, ai, auth, market, monitors, orders, positions, settings, strategies, workers
from app.db import init_db
from app.schemas import ok
from app.trading.workers import background_supervisor


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    await background_supervisor.start()
    try:
        yield
    finally:
        await background_supervisor.stop()


app = FastAPI(title="Codex Fast Trade", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict:
    return ok({"status": "ok"})


@app.get("/readyz")
async def readyz() -> dict:
    return ok({"status": "ready"})


app.include_router(auth.router)
app.include_router(market.router)
app.include_router(positions.router)
app.include_router(orders.router)
app.include_router(monitors.router)
app.include_router(strategies.router)
app.include_router(ai.router)
app.include_router(workers.router)
app.include_router(activity.router)
app.include_router(settings.router)
