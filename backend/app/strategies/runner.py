import json
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.exchanges.binance import BinanceClient
from app.models import Strategy, StrategyRun
from app.schemas import FloatingOrderRequest, LaddersConfig
from app.trading.floating import submit_floating_order


SUPPORTED_STRATEGIES = {"grid", "ma_cross", "ai_signal"}


def validate_stoploss_config(config: dict) -> None:
    if not config:
        raise ValueError("stoploss_config is required")
    mode = config.get("mode")
    if mode not in {"pct", "price", "atr", "amount"}:
        raise ValueError("stoploss_config.mode must be one of pct, price, atr, amount")


def validate_strategy(strategy_type: str, stoploss_config: dict) -> None:
    if strategy_type not in SUPPORTED_STRATEGIES:
        raise ValueError(f"unsupported strategy type: {strategy_type}")
    validate_stoploss_config(stoploss_config)


async def create_strategy_run(*, session: AsyncSession, strategy: Strategy) -> StrategyRun:
    validate_strategy(strategy.type, json.loads(strategy.stoploss_config or "{}"))
    run = StrategyRun(strategy_id=strategy.id, status="running")
    session.add(run)
    await session.commit()
    return run


def build_strategy_order_request(strategy: Strategy, last_price: Decimal) -> FloatingOrderRequest | None:
    params = json.loads(strategy.params or "{}")
    stoploss = json.loads(strategy.stoploss_config or "{}")
    tp_pct = Decimal(str(params.get("tp_pct", params.get("take_profit_pct", "0.5"))))
    sl_value = Decimal(str(stoploss.get("value", params.get("sl_pct", "0.3"))))
    qty = Decimal(str(params.get("qty_usdt", params.get("qty", "100"))))

    if strategy.type == "grid":
        lower = Decimal(str(params.get("lower", last_price * Decimal("0.99"))))
        upper = Decimal(str(params.get("upper", last_price * Decimal("1.01"))))
        if last_price <= lower:
            side = "long"
            float_pct = Decimal("-0.05")
        elif last_price >= upper:
            side = "short"
            float_pct = Decimal("0.05")
        else:
            return None
        return FloatingOrderRequest(
            symbol=strategy.symbol,
            side=side,
            action="open",
            float_pct=float_pct,
            qty_mode="usdt",
            qty=qty,
            tp_pct=tp_pct,
            sl_pct=sl_value,
            ladders=LaddersConfig(count=int(params.get("ladders", 1)), spacing_pct=Decimal(str(params.get("spacing_pct", "0.05")))),
        )

    if strategy.type == "ma_cross":
        signal = params.get("signal", "hold")
        if signal not in {"long", "short"}:
            return None
        return FloatingOrderRequest(
            symbol=strategy.symbol,
            side="long" if signal == "long" else "short",
            action="open",
            float_pct=Decimal(str(params.get("float_pct", "-0.05" if signal == "long" else "0.05"))),
            qty_mode="usdt",
            qty=qty,
            tp_pct=tp_pct,
            sl_pct=sl_value,
        )

    if strategy.type == "ai_signal":
        ai_action = params.get("ai_action", "hold")
        if ai_action not in {"long", "short"}:
            return None
        return FloatingOrderRequest(
            symbol=strategy.symbol,
            side="long" if ai_action == "long" else "short",
            action="open",
            float_pct=Decimal(str(params.get("float_pct", "-0.05" if ai_action == "long" else "0.05"))),
            qty_mode="usdt",
            qty=qty,
            tp_pct=tp_pct,
            sl_pct=sl_value,
        )

    return None


async def run_strategy_once(
    *,
    session: AsyncSession,
    strategy: Strategy,
    execute: bool = False,
    client: BinanceClient | None = None,
) -> dict[str, Any]:
    validate_strategy(strategy.type, json.loads(strategy.stoploss_config or "{}"))
    client = client or BinanceClient()
    ticker = await client.ticker_24hr(strategy.symbol)
    last_price = Decimal(str(ticker.get("lastPrice", "0")))
    request = build_strategy_order_request(strategy, last_price)
    if request is None:
        return {"signal": "hold", "last_price": str(last_price), "executed": False}
    if not execute:
        return {"signal": "order", "last_price": str(last_price), "executed": False, "order": request.model_dump(mode="json")}
    orders = await submit_floating_order(payload=request, session=session, client=client)
    return {"signal": "order", "last_price": str(last_price), "executed": True, "orders": orders}
