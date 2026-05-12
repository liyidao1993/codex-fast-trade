from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto import reveal_secret
from app.config import get_settings
from app.exchanges.binance import BinanceClient
from app.models import ApiKey, SystemState


BINANCE_REST_BASES = {
    "testnet": "https://demo-fapi.binance.com",
    "mainnet": "https://fapi.binance.com",
}


def normalize_binance_env(env: str | None) -> str:
    value = (env or "testnet").strip().lower()
    if value not in BINANCE_REST_BASES:
        return "testnet"
    return value


def binance_rest_base_for_env(env: str) -> str:
    return BINANCE_REST_BASES[normalize_binance_env(env)]


async def get_state_value(session: AsyncSession, key: str, default: str) -> str:
    state = await session.get(SystemState, key)
    return state.value if state is not None else default


async def set_state_value(session: AsyncSession, key: str, value: str) -> None:
    state = await session.get(SystemState, key)
    if state is None:
        session.add(SystemState(key=key, value=value))
    else:
        state.value = value


async def get_active_binance_env(session: AsyncSession) -> str:
    settings = get_settings()
    configured = await get_state_value(session, "binance_active_env", settings.binance_env)
    return normalize_binance_env(configured)


async def set_active_binance_env(session: AsyncSession, env: str) -> str:
    normalized = normalize_binance_env(env)
    await set_state_value(session, "binance_active_env", normalized)
    return normalized


async def is_mainnet_confirmed(session: AsyncSession) -> bool:
    return (await get_state_value(session, "mainnet_confirmed", "false")).lower() == "true"


async def set_mainnet_confirmed(session: AsyncSession, confirmed: bool) -> None:
    await set_state_value(session, "mainnet_confirmed", "true" if confirmed else "false")


async def get_active_api_key(session: AsyncSession, *, exchange: str = "binance", env: str | None = None) -> ApiKey | None:
    active_env = normalize_binance_env(env) if env is not None else await get_active_binance_env(session)
    return await session.scalar(
        select(ApiKey)
        .where(ApiKey.exchange == exchange, ApiKey.env == active_env)
        .order_by(ApiKey.id.desc())
        .limit(1)
    )


async def load_binance_public_client(session: AsyncSession) -> BinanceClient:
    env = await get_active_binance_env(session)
    return BinanceClient(base_url=binance_rest_base_for_env(env))


async def load_binance_client(session: AsyncSession) -> BinanceClient:
    env = await get_active_binance_env(session)
    api_key = await get_active_api_key(session, env=env)
    base_url = binance_rest_base_for_env(env)
    if api_key is None:
        return BinanceClient(base_url=base_url)
    return BinanceClient(
        api_key=reveal_secret(api_key.key_encrypted),
        api_secret=reveal_secret(api_key.secret_encrypted),
        base_url=base_url,
    )
