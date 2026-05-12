import hashlib
import hmac
import time
import uuid
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import get_settings


class BinanceError(RuntimeError):
    pass


class BinanceClient:
    def __init__(self, *, api_key: str | None = None, api_secret: str | None = None, base_url: str | None = None) -> None:
        self.settings = get_settings()
        self.base_url = (base_url or self.settings.binance_rest_base).rstrip("/")
        self.api_key = api_key if api_key is not None else self.settings.binance_api_key
        self.api_secret = api_secret if api_secret is not None else self.settings.binance_api_secret

    async def exchange_info(self) -> dict[str, Any]:
        return await self._request("GET", "/fapi/v1/exchangeInfo", signed=False)

    async def book_ticker(self, symbol: str) -> dict[str, Any]:
        return await self._request("GET", "/fapi/v1/ticker/bookTicker", params={"symbol": symbol.upper()}, signed=False)

    async def ticker_24hr(self, symbol: str) -> dict[str, Any]:
        return await self._request("GET", "/fapi/v1/ticker/24hr", params={"symbol": symbol.upper()}, signed=False)

    async def account(self) -> dict[str, Any]:
        return await self._request("GET", "/fapi/v2/account", signed=True)

    async def positions(self) -> list[dict[str, Any]]:
        account = await self.account()
        return [p for p in account.get("positions", []) if Decimal(str(p.get("positionAmt", "0"))) != 0]

    async def open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        params = {"symbol": symbol.upper()} if symbol else {}
        return await self._request("GET", "/fapi/v1/openOrders", params=params, signed=True)

    async def query_order(self, *, symbol: str, client_order_id: str | None = None, order_id: int | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"symbol": symbol.upper()}
        if client_order_id is not None:
            params["origClientOrderId"] = client_order_id
        if order_id is not None:
            params["orderId"] = order_id
        if client_order_id is None and order_id is None:
            raise ValueError("client_order_id or order_id is required")
        return await self._request("GET", "/fapi/v1/order", params=params, signed=True)

    async def cancel_order(self, *, symbol: str, order_id: int | None = None, client_order_id: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"symbol": symbol.upper()}
        if order_id is not None:
            params["orderId"] = order_id
        if client_order_id is not None:
            params["origClientOrderId"] = client_order_id
        if order_id is None and client_order_id is None:
            raise ValueError("order_id or client_order_id is required")
        return await self._request("DELETE", "/fapi/v1/order", params=params, signed=True)

    async def cancel_all_open_orders(self, symbol: str) -> dict[str, Any]:
        return await self._request("DELETE", "/fapi/v1/allOpenOrders", params={"symbol": symbol.upper()}, signed=True)

    async def place_algo_order(
        self,
        *,
        symbol: str,
        side: str,
        order_type: str,
        trigger_price: Decimal,
        quantity: Decimal | None = None,
        position_side: str = "BOTH",
        working_type: str | None = None,
        price_protect: bool | None = None,
        reduce_only: bool = False,
        close_position: bool = False,
        client_algo_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "algoType": "CONDITIONAL",
            "symbol": symbol.upper(),
            "side": side,
            "type": order_type,
            "triggerPrice": str(trigger_price),
            "clientAlgoId": client_algo_id or f"ao-{uuid.uuid4().hex[:24]}",
        }
        if position_side != "BOTH":
            params["positionSide"] = position_side
        if quantity is not None:
            params["quantity"] = str(quantity)
        if working_type:
            params["workingType"] = working_type
        if price_protect is not None:
            params["priceProtect"] = "true" if price_protect else "false"
        if reduce_only:
            params["reduceOnly"] = "true"
        if close_position:
            params["closePosition"] = "true"
        return await self._request("POST", "/fapi/v1/algoOrder", params=params, signed=True)

    async def cancel_algo_order(self, *, algo_id: int | None = None, client_algo_id: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if algo_id is not None:
            params["algoId"] = algo_id
        if client_algo_id is not None:
            params["clientAlgoId"] = client_algo_id
        if algo_id is None and client_algo_id is None:
            raise ValueError("algo_id or client_algo_id is required")
        return await self._request("DELETE", "/fapi/v1/algoOrder", params=params, signed=True)

    async def open_algo_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        params = {"symbol": symbol.upper()} if symbol else {}
        return await self._request("GET", "/fapi/v1/openAlgoOrders", params=params, signed=True)

    async def start_user_stream(self) -> dict[str, Any]:
        return await self._api_key_request("POST", "/fapi/v1/listenKey")

    async def keepalive_user_stream(self, listen_key: str) -> dict[str, Any]:
        return await self._api_key_request("PUT", "/fapi/v1/listenKey", params={"listenKey": listen_key})

    async def close_user_stream(self, listen_key: str) -> dict[str, Any]:
        return await self._api_key_request("DELETE", "/fapi/v1/listenKey", params={"listenKey": listen_key})

    async def place_order(
        self,
        *,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Decimal | None = None,
        position_side: str = "BOTH",
        post_only: bool = False,
        reduce_only: bool = False,
        stop_price: Decimal | None = None,
        working_type: str | None = None,
        price_protect: bool | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "symbol": symbol.upper(),
            "side": side,
            "type": order_type,
            "quantity": str(quantity),
            "newClientOrderId": client_order_id or f"co-{uuid.uuid4().hex[:24]}",
        }
        if position_side != "BOTH":
            params["positionSide"] = position_side
        elif reduce_only:
            params["reduceOnly"] = "true"
        if order_type == "LIMIT":
            if price is None:
                raise ValueError("LIMIT order requires price")
            params["price"] = str(price)
            params["timeInForce"] = "GTX" if post_only else "GTC"
        if order_type in {"STOP_MARKET", "TAKE_PROFIT_MARKET"}:
            if stop_price is None:
                raise ValueError(f"{order_type} requires stop_price")
            params["stopPrice"] = str(stop_price)
            if working_type:
                params["workingType"] = working_type
            if price_protect is not None:
                params["priceProtect"] = "TRUE" if price_protect else "FALSE"
        return await self._request("POST", "/fapi/v1/order", params=params, signed=True)

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        signed: bool,
    ) -> Any:
        params = dict(params or {})
        headers = {}
        async with httpx.AsyncClient(base_url=self.base_url, timeout=10.0) as client:
            if signed:
                if not self.api_key or not self.api_secret:
                    raise BinanceError("BINANCE_API_KEY and BINANCE_API_SECRET are required for signed requests")
                headers["X-MBX-APIKEY"] = self.api_key
                params["timestamp"] = await self._server_timestamp(client)
                params["recvWindow"] = self.settings.binance_recv_window
                query = urlencode(params)
                params["signature"] = hmac.new(
                    self.api_secret.encode("utf-8"),
                    query.encode("utf-8"),
                    hashlib.sha256,
                ).hexdigest()
            response = await client.request(method, path, params=params, headers=headers)
        if response.status_code >= 400:
            raise BinanceError(f"Binance {response.status_code}: {response.text}")
        return response.json()

    async def _server_timestamp(self, client: httpx.AsyncClient) -> int:
        try:
            response = await client.get("/fapi/v1/time")
            response.raise_for_status()
            return int(response.json()["serverTime"]) - 250
        except Exception:
            return int(time.time() * 1000)

    async def _api_key_request(self, method: str, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self.api_key:
            raise BinanceError("BINANCE_API_KEY is required")
        async with httpx.AsyncClient(base_url=self.base_url, timeout=10.0) as client:
            response = await client.request(
                method,
                path,
                params=dict(params or {}),
                headers={"X-MBX-APIKEY": self.api_key},
            )
        if response.status_code >= 400:
            raise BinanceError(f"Binance {response.status_code}: {response.text}")
        if response.text:
            return response.json()
        return {}


def map_order_intent(side: str, action: str) -> tuple[str, str]:
    if side == "long" and action == "open":
        return "BUY", "BOTH"
    if side == "long" and action == "close":
        return "SELL", "BOTH"
    if side == "short" and action == "open":
        return "SELL", "BOTH"
    if side == "short" and action == "close":
        return "BUY", "BOTH"
    raise ValueError(f"Unsupported order intent: {side}/{action}")
