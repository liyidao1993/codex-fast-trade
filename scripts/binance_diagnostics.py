import argparse
import asyncio
import hashlib
import hmac
import json
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.config import get_settings  # noqa: E402
from app.crypto import mask_key, reveal_secret  # noqa: E402


DEFAULT_BASES = [
    "https://testnet.binancefuture.com",
    "https://demo-fapi.binance.com",
    "https://fapi.binance.com",
]


@dataclass(frozen=True)
class SavedKey:
    api_key: str
    api_secret: str
    label: str
    created_at: str


def load_active_env(con: sqlite3.Connection) -> str:
    row = con.execute("select value from system_state where key='binance_active_env'").fetchone()
    return row[0] if row and row[0] in {"testnet", "mainnet"} else get_settings().binance_env


def load_saved_key() -> tuple[str, SavedKey | None]:
    settings = get_settings()
    db_path = settings.database_url.rsplit("///", 1)[-1]
    con = sqlite3.connect(db_path)
    try:
        env = load_active_env(con)
        row = con.execute(
            "select key_encrypted, secret_encrypted, label, created_at from api_keys "
            "where exchange='binance' and env=? order by id desc limit 1",
            (env,),
        ).fetchone()
    finally:
        con.close()
    if not row:
        return env, None
    return env, SavedKey(
        api_key=reveal_secret(row[0]),
        api_secret=reveal_secret(row[1]),
        label=row[2],
        created_at=row[3],
    )


def sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: sanitize_payload(item) for key, item in value.items() if key.lower() not in {"apikey", "signature"}}
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value[:5]]
    return value


async def request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    key: SavedKey | None = None,
    signed: bool = False,
    api_key_only: bool = False,
    server_time: int | None = None,
) -> dict[str, Any]:
    params = dict(params or {})
    headers: dict[str, str] = {}
    if signed or api_key_only:
        if key is None:
            return {"ok": False, "status": "missing_key", "detail": "no saved api key"}
        headers["X-MBX-APIKEY"] = key.api_key
    if signed:
        params["timestamp"] = server_time or int(time.time() * 1000)
        params["recvWindow"] = get_settings().binance_recv_window
        query = urlencode(params)
        params["signature"] = hmac.new(key.api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
    try:
        response = await client.request(method, path, params=params, headers=headers)
    except Exception as exc:
        return {"ok": False, "status": "network_error", "detail": type(exc).__name__ + ": " + str(exc)}
    content_type = response.headers.get("content-type", "")
    try:
        body: Any = response.json() if "json" in content_type or response.text else {}
    except ValueError:
        body = response.text[:500]
    result: dict[str, Any] = {
        "ok": 200 <= response.status_code < 300,
        "status": response.status_code,
    }
    if isinstance(body, dict):
        if "code" in body:
            result["binance_code"] = body.get("code")
        if "msg" in body:
            result["binance_msg"] = body.get("msg")
        if response.status_code < 400:
            result["sample"] = summarize_success(path, body)
    else:
        result["detail"] = body
    return sanitize_payload(result)


def summarize_success(path: str, body: dict[str, Any]) -> Any:
    if path.endswith("/time"):
        return {"serverTime": body.get("serverTime")}
    if path.endswith("/exchangeInfo"):
        symbols = body.get("symbols", [])
        return {"symbols": len(symbols), "first": symbols[0].get("symbol") if symbols else ""}
    if "bookTicker" in path:
        return {key: body.get(key) for key in ("symbol", "bidPrice", "askPrice")}
    if "ticker/24hr" in path:
        return {key: body.get(key) for key in ("symbol", "lastPrice", "quoteVolume")}
    if path.endswith("/account"):
        return {
            "canTrade": body.get("canTrade"),
            "assets": len(body.get("assets", [])),
            "positions": len(body.get("positions", [])),
        }
    if "positionRisk" in path:
        return {"positions": len(body) if isinstance(body, list) else 0}
    if "openOrders" in path:
        return {"openOrders": len(body) if isinstance(body, list) else 0}
    if "listenKey" in path:
        return {"listenKey": bool(body.get("listenKey"))}
    if "order/test" in path:
        return "accepted"
    return "ok"


async def diagnose_base(base_url: str, key: SavedKey | None, symbol: str) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=base_url, timeout=12.0, trust_env=True) as client:
        time_result = await request(client, "GET", "/fapi/v1/time")
        server_time = None
        if time_result["ok"]:
            raw_time = await client.get("/fapi/v1/time")
            server_time = int(raw_time.json()["serverTime"])
        checks = {
            "time": time_result,
            "exchangeInfo": await request(client, "GET", "/fapi/v1/exchangeInfo"),
            "bookTicker": await request(client, "GET", "/fapi/v1/ticker/bookTicker", params={"symbol": symbol}),
            "ticker24hr": await request(client, "GET", "/fapi/v1/ticker/24hr", params={"symbol": symbol}),
            "account": await request(client, "GET", "/fapi/v2/account", key=key, signed=True, server_time=server_time),
            "positionRisk": await request(
                client,
                "GET",
                "/fapi/v2/positionRisk",
                params={"symbol": symbol},
                key=key,
                signed=True,
                server_time=server_time,
            ),
            "openOrders": await request(
                client,
                "GET",
                "/fapi/v1/openOrders",
                params={"symbol": symbol},
                key=key,
                signed=True,
                server_time=server_time,
            ),
            "listenKey": await request(client, "POST", "/fapi/v1/listenKey", key=key, api_key_only=True),
        }
    return {"base_url": base_url, "checks": checks}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--base", action="append", default=[])
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    env, key = load_saved_key()
    bases = args.base or DEFAULT_BASES
    report = {
        "environment": {
            "frontend": "http://127.0.0.1:18081",
            "backend": "http://127.0.0.1:18080",
            "database_url": get_settings().database_url,
            "configured_base": get_settings().binance_rest_base,
            "active_env": env,
            "key": {
                "configured": key is not None,
                "masked": mask_key(key.api_key) if key else "",
                "label": key.label if key else "",
                "created_at": key.created_at if key else "",
            },
        },
        "results": [await diagnose_base(base, key, args.symbol.upper()) for base in bases],
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    asyncio.run(main())
