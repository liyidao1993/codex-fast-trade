import argparse
import asyncio
import hashlib
import hmac
import json
import sqlite3
import sys
import time
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.config import get_settings  # noqa: E402
from app.crypto import mask_key, reveal_secret  # noqa: E402


def load_key() -> tuple[str, str]:
    settings = get_settings()
    db_path = settings.database_url.rsplit("///", 1)[-1]
    con = sqlite3.connect(db_path)
    try:
        row = con.execute(
            "select key_encrypted, secret_encrypted from api_keys "
            "where exchange='binance' and env='testnet' order by id desc limit 1"
        ).fetchone()
    finally:
        con.close()
    if not row:
        raise RuntimeError("no saved Binance testnet key")
    return reveal_secret(row[0]), reveal_secret(row[1])


def q(value: Decimal, step: Decimal, mode: str) -> Decimal:
    rounding = ROUND_FLOOR if mode == "down" else ROUND_CEILING
    return (value / step).to_integral_value(rounding=rounding) * step


def parse_filters(symbol_info: dict[str, Any]) -> dict[str, Decimal]:
    filters = {item["filterType"]: item for item in symbol_info.get("filters", [])}
    price_filter = filters.get("PRICE_FILTER", {})
    lot_filter = filters.get("LOT_SIZE", {})
    notional_filter = filters.get("MIN_NOTIONAL") or filters.get("NOTIONAL") or {}
    return {
        "tick_size": Decimal(str(price_filter.get("tickSize", "0.01"))),
        "step_size": Decimal(str(lot_filter.get("stepSize", "0.001"))),
        "min_notional": Decimal(str(notional_filter.get("notional") or notional_filter.get("minNotional") or "5")),
    }


class SignedClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=12.0, trust_env=True)
        self.server_time: int | None = None

    async def close(self) -> None:
        await self.client.aclose()

    async def sync_time(self) -> None:
        response = await self.client.get("/fapi/v1/time")
        response.raise_for_status()
        self.server_time = int(response.json()["serverTime"])

    async def request(self, method: str, path: str, params: dict[str, Any] | None = None, signed: bool = False) -> Any:
        params = dict(params or {})
        headers = {}
        if signed:
            headers["X-MBX-APIKEY"] = self.api_key
            params["timestamp"] = self.server_time or int(time.time() * 1000)
            params["recvWindow"] = get_settings().binance_recv_window
            query = urlencode(params)
            params["signature"] = hmac.new(self.api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
        response = await self.client.request(method, path, params=params, headers=headers)
        if response.status_code >= 400:
            raise RuntimeError(f"Binance {response.status_code}: {response.text[:500]}")
        if response.text:
            return response.json()
        return {}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--notional", default="8")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    base_url = args.base or get_settings().binance_rest_base
    symbol = args.symbol.upper()
    report: dict[str, Any] = {
        "base_url": base_url,
        "symbol": symbol,
        "execute": args.execute,
        "steps": [],
    }

    try:
        api_key, api_secret = load_key()
    except Exception as exc:
        report["key_masked"] = ""
        report["steps"].append({"name": "load_key", "ok": False, "detail": str(exc)})
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
        print(text)
        return

    client = SignedClient(base_url, api_key, api_secret)
    placed_client_order_id = ""
    report["key_masked"] = mask_key(api_key)

    try:
        await client.sync_time()
        exchange_info = await client.request("GET", "/fapi/v1/exchangeInfo")
        symbol_info = next((item for item in exchange_info.get("symbols", []) if item.get("symbol") == symbol), None)
        if not symbol_info:
            raise RuntimeError(f"symbol not found: {symbol}")
        filters = parse_filters(symbol_info)
        ticker = await client.request("GET", "/fapi/v1/ticker/bookTicker", {"symbol": symbol})
        bid = Decimal(str(ticker["bidPrice"]))
        price = q(bid * Decimal("0.99"), filters["tick_size"], "down")
        target_notional = max(Decimal(args.notional), filters["min_notional"] * Decimal("1.2"))
        qty = q(target_notional / price, filters["step_size"], "up")
        notional = price * qty
        params = {
            "symbol": symbol,
            "side": "BUY",
            "type": "LIMIT",
            "timeInForce": "GTX",
            "quantity": str(qty),
            "price": str(price),
            "newClientOrderId": f"co-smoke-{int(time.time())}",
        }
        report["calculated_order"] = {"side": "BUY", "price": str(price), "qty": str(qty), "notional": str(notional)}
        await client.request("POST", "/fapi/v1/order/test", params, signed=True)
        report["steps"].append({"name": "order_test", "ok": True})
        if args.execute:
            result = await client.request("POST", "/fapi/v1/order", params, signed=True)
            placed_client_order_id = params["newClientOrderId"]
            report["steps"].append(
                {
                    "name": "place_limit_gtx",
                    "ok": True,
                    "status": result.get("status"),
                    "orderId": result.get("orderId"),
                    "clientOrderId": result.get("clientOrderId"),
                }
            )
            query = await client.request(
                "GET",
                "/fapi/v1/order",
                {"symbol": symbol, "origClientOrderId": placed_client_order_id},
                signed=True,
            )
            report["steps"].append({"name": "query_order", "ok": True, "status": query.get("status")})
            cancel = await client.request(
                "DELETE",
                "/fapi/v1/order",
                {"symbol": symbol, "origClientOrderId": placed_client_order_id},
                signed=True,
            )
            report["steps"].append({"name": "cancel_order", "ok": True, "status": cancel.get("status")})
            open_orders = await client.request("GET", "/fapi/v1/openOrders", {"symbol": symbol}, signed=True)
            still_open = [item.get("clientOrderId") for item in open_orders if item.get("clientOrderId") == placed_client_order_id]
            report["steps"].append({"name": "open_orders_cleanup", "ok": not still_open, "remaining": still_open})
    except Exception as exc:
        report["steps"].append({"name": "error", "ok": False, "detail": str(exc)})
        if placed_client_order_id:
            try:
                await client.request("DELETE", "/fapi/v1/order", {"symbol": symbol, "origClientOrderId": placed_client_order_id}, signed=True)
                report["steps"].append({"name": "cleanup_after_error", "ok": True})
            except Exception as cleanup_exc:
                report["steps"].append({"name": "cleanup_after_error", "ok": False, "detail": str(cleanup_exc)})
    finally:
        await client.close()

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    asyncio.run(main())
