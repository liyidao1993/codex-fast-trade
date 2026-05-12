from decimal import Decimal

from app.config import get_settings
from app.exchanges.binance import BinanceClient
from app.schemas import AiTradeDraftRequest


def decide_action(price_change_pct: Decimal) -> tuple[str, Decimal, str]:
    if price_change_pct >= Decimal("1.5"):
        return "long_open", Decimal("0.72"), "币安 24 小时行情显示正向动量。"
    if price_change_pct <= Decimal("-1.5"):
        return "short_open", Decimal("0.72"), "币安 24 小时行情显示负向动量。"
    return "hold", Decimal("0.5"), "本地行情暂无强信号。"


async def analyze_with_mock_provider(symbol: str, client: BinanceClient | None = None) -> AiTradeDraftRequest:
    settings = get_settings()
    client = client or BinanceClient()
    ticker = await client.ticker_24hr(symbol)
    price_change_pct = Decimal(str(ticker.get("priceChangePercent", "0")))
    action, confidence, rationale = decide_action(price_change_pct)
    suggested_order = {}
    if action != "hold":
        suggested_order = {
            "qty_mode": "usdt",
            "qty": settings.ai_default_qty_usdt,
            "float_pct": "-0.05" if action == "long_open" else "0.05",
            "tp_pct": settings.ai_default_tp_pct,
            "sl_pct": settings.ai_default_sl_pct,
            "post_only": True,
        }
    return AiTradeDraftRequest(
        symbol=symbol,
        action=action,
        confidence=confidence,
        rationale=f"{rationale} 24 小时涨跌幅={price_change_pct}",
        suggested_order=suggested_order,
    )


async def analyze_market(symbol: str, client: BinanceClient | None = None) -> AiTradeDraftRequest:
    settings = get_settings()
    if settings.ai_provider != "mock":
        raise ValueError(f"unsupported AI provider: {settings.ai_provider}")
    return await analyze_with_mock_provider(symbol, client=client)
