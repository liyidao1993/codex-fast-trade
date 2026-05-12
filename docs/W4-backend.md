# W4 Backend Notes

This iteration wires the remaining backend cores needed before a frontend panel.

## Done

- Binance REST wrapper now supports query order and listenKey start/keepalive/close helpers.
- `order_updates.py` handles Binance `ORDER_TRADE_UPDATE` payloads, updates local order fill state, and automatically attaches TP/SL protection for incremental fills.
- `reconcile.py` can apply reconciliation plans by marking local-missing orders as `NEED_RECONCILE` and recording exchange orphan orders.
- `chase_runner.py` executes a single deterministic chase replacement step against the exchange adapter.
- Tests use fake exchange clients, so no real Binance key is required.

## Still Pending

- Actual WebSocket user stream consumer.
- Long-running background supervisor for chase and reconciliation.
- Frontend trading panel.

