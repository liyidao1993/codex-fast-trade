from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto import mask_key, protect_secret, reveal_secret
from app.db import get_session
from app.exchanges.binance import BinanceClient, BinanceError
from app.exchanges.credentials import (
    binance_rest_base_for_env,
    get_active_api_key,
    get_active_binance_env,
    is_mainnet_confirmed,
    normalize_binance_env,
    set_active_binance_env,
    set_mainnet_confirmed,
)
from app.models import ApiKey
from app.schemas import BinanceApiKeyRequest, ok
from app.security import require_session


router = APIRouter(prefix="/api/v1/settings", tags=["settings"])
ENV_LABELS = {"testnet": "币安合约测试网", "mainnet": "币安合约实盘"}


async def serialize_api_key(session: AsyncSession, api_key: ApiKey | None, env: str) -> dict:
    base = {
        "configured": False,
        "exchange": "binance",
        "env": env,
        "env_label": ENV_LABELS[env],
        "base_url": binance_rest_base_for_env(env),
        "mainnet_confirmed": await is_mainnet_confirmed(session),
    }
    if api_key is None:
        return base
    return base | {
        "configured": True,
        "id": api_key.id,
        "exchange": api_key.exchange,
        "env": api_key.env,
        "label": api_key.label,
        "key_masked": mask_key(reveal_secret(api_key.key_encrypted)),
        "created_at": api_key.created_at.isoformat() if api_key.created_at else "",
    }


@router.get("/binance-key")
async def get_binance_key(_: None = Depends(require_session), session: AsyncSession = Depends(get_session)) -> dict:
    env = await get_active_binance_env(session)
    return ok(await serialize_api_key(session, await get_active_api_key(session, env=env), env))


@router.put("/binance-key")
async def save_binance_key(
    payload: BinanceApiKeyRequest,
    _: None = Depends(require_session),
    session: AsyncSession = Depends(get_session),
) -> dict:
    env = normalize_binance_env(payload.env)
    if env == "mainnet" and not payload.confirm_mainnet:
        raise HTTPException(status_code=400, detail="mainnet requires explicit confirmation")
    old_keys = list((await session.scalars(select(ApiKey).where(ApiKey.exchange == "binance", ApiKey.env == env))).all())
    for old_key in old_keys:
        await session.delete(old_key)
    await set_active_binance_env(session, env)
    await set_mainnet_confirmed(session, env == "mainnet")
    api_key = ApiKey(
        exchange="binance",
        env=env,
        key_encrypted=protect_secret(payload.api_key.strip()),
        secret_encrypted=protect_secret(payload.api_secret.strip()),
        label=payload.label.strip() or ENV_LABELS[env],
    )
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)
    return ok(await serialize_api_key(session, api_key, env))


@router.delete("/binance-key")
async def delete_binance_key(_: None = Depends(require_session), session: AsyncSession = Depends(get_session)) -> dict:
    env = await get_active_binance_env(session)
    keys = list((await session.scalars(select(ApiKey).where(ApiKey.exchange == "binance", ApiKey.env == env))).all())
    for api_key in keys:
        await session.delete(api_key)
    if keys:
        await session.commit()
    return ok(await serialize_api_key(session, None, env))


@router.post("/binance-key/test")
async def test_binance_key(_: None = Depends(require_session), session: AsyncSession = Depends(get_session)) -> dict:
    env = await get_active_binance_env(session)
    api_key = await get_active_api_key(session, env=env)
    if api_key is None:
        raise HTTPException(status_code=400, detail=f"Binance {env} key is not configured")
    client = BinanceClient(
        api_key=reveal_secret(api_key.key_encrypted),
        api_secret=reveal_secret(api_key.secret_encrypted),
        base_url=binance_rest_base_for_env(env),
    )
    try:
        account = await client.account()
    except BinanceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ok(
        {
            "connected": True,
            "can_trade": bool(account.get("canTrade", False)),
            "fee_tier": account.get("feeTier"),
            "assets": len(account.get("assets", [])),
            "positions": len(account.get("positions", [])),
            "env": env,
            "base_url": binance_rest_base_for_env(env),
        }
    )
