from decimal import Decimal

import pytest

from app.ai.provider import analyze_with_mock_provider, decide_action
from app.ai.trade_draft import draft_to_floating_order, validate_ai_draft_order, validate_ai_trade_draft
from app.models import AiTradeDraft
from app.schemas import AiTradeDraftRequest


def test_ai_trade_draft_requires_order_unless_hold() -> None:
    payload = AiTradeDraftRequest(symbol="BTCUSDT", action="long_open", confidence=Decimal("0.7"))
    with pytest.raises(ValueError, match="suggested_order"):
        validate_ai_trade_draft(payload)


def test_ai_trade_draft_allows_hold_without_order() -> None:
    payload = AiTradeDraftRequest(symbol="BTCUSDT", action="hold", confidence=Decimal("0.7"))
    validate_ai_trade_draft(payload)


def test_ai_trade_draft_confidence_range() -> None:
    payload = AiTradeDraftRequest(symbol="BTCUSDT", action="hold", confidence=Decimal("1.5"))
    with pytest.raises(ValueError, match="confidence"):
        validate_ai_trade_draft(payload)


def test_ai_draft_to_floating_order_requires_stoploss() -> None:
    draft = AiTradeDraft(
        symbol="BTCUSDT",
        action="long_open",
        confidence="0.8",
        payload='{"qty_mode":"usdt","qty":"50","float_pct":"-0.05","tp_pct":"0.5"}',
        status="draft",
    )
    with pytest.raises(ValueError, match="sl_pct"):
        validate_ai_draft_order(draft, min_confidence=Decimal("0.65"))


def test_ai_draft_to_floating_order() -> None:
    draft = AiTradeDraft(
        symbol="BTCUSDT",
        action="short_open",
        confidence="0.8",
        payload='{"qty_mode":"usdt","qty":"50","float_pct":"0.05","tp_pct":"0.5","sl_pct":"0.3"}',
        status="draft",
    )
    order = draft_to_floating_order(draft)
    assert order.symbol == "BTCUSDT"
    assert order.side == "short"
    assert order.action == "open"
    assert order.sl_pct == Decimal("0.3")


def test_decide_action() -> None:
    assert decide_action(Decimal("2"))[0] == "long_open"
    assert decide_action(Decimal("-2"))[0] == "short_open"
    assert decide_action(Decimal("0.1"))[0] == "hold"


class FakeTickerClient:
    async def ticker_24hr(self, symbol: str) -> dict:
        assert symbol == "BTCUSDT"
        return {"priceChangePercent": "2.1"}


@pytest.mark.asyncio
async def test_mock_provider_creates_order_draft() -> None:
    draft = await analyze_with_mock_provider("BTCUSDT", client=FakeTickerClient())
    assert draft.action == "long_open"
    assert draft.suggested_order["sl_pct"]
