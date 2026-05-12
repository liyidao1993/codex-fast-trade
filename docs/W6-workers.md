# W6 Lightweight Workers

Date: 2026-05-11

## Scope

W6 adds in-process background workers for continuous monitoring, scheduled strategy checks, and Binance user-stream order updates. The design stays lightweight: no Redis, no Celery, no K8s, and no circuit breaker.

## Workers

- `monitor`: scans enabled monitor rules and records events from Binance 24h ticker data.
- `strategy`: scans enabled strategies and records one `strategy_runs` row per cycle.
- `user_stream`: opens a Binance listenKey WebSocket and feeds `ORDER_TRADE_UPDATE` events into the existing order update handler.

## Runtime Defaults

All workers are disabled by default in `.env.example`. Enable them explicitly:

```env
MONITOR_SCHEDULER_ENABLED=true
STRATEGY_SCHEDULER_ENABLED=true
USER_STREAM_ENABLED=true
```

Strategy execution is still separate:

```env
STRATEGY_SCHEDULER_EXECUTE=false
```

When `STRATEGY_SCHEDULER_EXECUTE=false`, the strategy worker only dry-runs and records signals. Set it to `true` only after testnet validation.

## API

- `GET /api/v1/workers/status`

The endpoint requires login and returns each worker's enabled/running state, iteration count, last success time, last error, and last event summary.

## Safety Boundaries

- No daily loss fuse.
- No global auto pause.
- No strategy auto shutdown.
- Strategy-level stoploss remains mandatory.
- AI remains draft-only and does not directly submit orders.
- TradingView remains visual-only; trading decisions use Binance data.
