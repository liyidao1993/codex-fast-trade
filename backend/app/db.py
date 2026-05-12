from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models import Base, GuardRules, SystemState


settings = get_settings()

if settings.database_url.startswith("sqlite"):
    db_path = settings.database_url.rsplit("///", 1)[-1]
    if db_path and db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(settings.database_url, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        if settings.database_url.startswith("sqlite"):
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA busy_timeout=5000"))
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        await seed_defaults(session)


async def seed_defaults(session: AsyncSession) -> None:
    guard = await session.get(GuardRules, 1)
    if guard is None:
        session.add(
            GuardRules(
                id=1,
                per_order_max_usdt=settings.per_order_max_usdt,
                global_max_position_usdt=settings.global_max_position_usdt,
                global_max_leverage=settings.global_max_leverage,
                allowed_symbols=",".join(sorted(settings.allowed_symbol_set)),
                forbidden_symbols=",".join(sorted(settings.forbidden_symbol_set)),
            )
        )

    existing = await session.scalar(select(SystemState).where(SystemState.key == "mainnet_confirmed"))
    if existing is None:
        session.add(SystemState(key="mainnet_confirmed", value="false"))

    active_env = await session.scalar(select(SystemState).where(SystemState.key == "binance_active_env"))
    if active_env is None:
        session.add(SystemState(key="binance_active_env", value=settings.binance_env))

    await session.commit()


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
