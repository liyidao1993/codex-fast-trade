# W8 AI Integration

Date: 2026-05-11

## Scope

W8 adds the AI trading workflow while keeping execution under local control.

AI does not trade directly. AI creates drafts. Drafts must pass local validation and require a PIN before approval or execution.

## Backend

- `POST /api/v1/ai/analyze`
- `GET /api/v1/ai/drafts`
- `POST /api/v1/ai/trade-drafts`
- `POST /api/v1/ai/drafts/{draft_id}/validate`
- `POST /api/v1/ai/drafts/{draft_id}/approve`

`AI_PROVIDER=mock` is the default provider. It uses Binance ticker data and creates local drafts only. This keeps W8 testable without external LLM credentials.

## Validation

AI order drafts must pass:

- confidence >= `AI_MIN_CONFIDENCE`
- non-hold action has a suggested order
- hard guard symbol/notional checks
- required `sl_pct`
- explicit PIN on approval

If `execute=false`, approval only marks the draft approved and returns the normalized order request.

If `execute=true`, approval submits a floating LIMIT order through the existing Binance order path. It still goes through local guard and Binance precision/order handling.

## Boundaries

- AI does not bypass guard checks.
- AI does not bypass PIN.
- AI does not use TradingView data for trading.
- AI does not create a circuit breaker, global pause, or strategy shutdown.
