import asyncio
import json
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

import websockets
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import get_settings
from app.exchanges.binance import BinanceClient
from app.trading.order_updates import handle_order_trade_update


@dataclass
class UserStreamState:
    listen_key: str = ""
    running: bool = False
    events_handled: int = 0
    keepalives: int = 0
    last_error: str = ""


def build_user_stream_url(listen_key: str, ws_base: str | None = None) -> str:
    base = (ws_base or get_settings().binance_ws_base).rstrip("/")
    return f"{base}/{listen_key}"


def decode_user_stream_message(raw_message: str | bytes) -> dict[str, Any]:
    if isinstance(raw_message, bytes):
        raw_message = raw_message.decode("utf-8")
    event = json.loads(raw_message)
    if not isinstance(event, dict):
        raise ValueError("user stream message must be a JSON object")
    return event


async def keepalive_loop(state: UserStreamState, client: BinanceClient | None = None, interval_sec: int = 30 * 60) -> None:
    client = client or BinanceClient()
    while state.running and state.listen_key:
        await asyncio.sleep(interval_sec)
        if state.running and state.listen_key:
            await client.keepalive_user_stream(state.listen_key)
            state.keepalives += 1


async def consume_user_stream(
    *,
    state: UserStreamState,
    session_factory: async_sessionmaker,
    client: BinanceClient | None = None,
    ws_base: str | None = None,
    keepalive_sec: int = 30 * 60,
) -> None:
    client = client or BinanceClient()
    state.listen_key = await client.start_user_stream()
    state.running = True
    keepalive_task = asyncio.create_task(keepalive_loop(state, client=client, interval_sec=keepalive_sec))
    try:
        async with websockets.connect(build_user_stream_url(state.listen_key, ws_base)) as websocket:
            async for raw_message in websocket:
                event = decode_user_stream_message(raw_message)
                async with session_factory() as session:
                    result = await handle_order_trade_update(event=event, session=session, client=client)
                    if result.handled:
                        state.events_handled += 1
    except Exception as exc:
        state.last_error = str(exc)
        raise
    finally:
        state.running = False
        keepalive_task.cancel()
        try:
            await keepalive_task
        except asyncio.CancelledError:
            pass
        if state.listen_key:
            with suppress(Exception):
                await client.close_user_stream(state.listen_key)
