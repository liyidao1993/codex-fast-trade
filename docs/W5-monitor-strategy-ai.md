# W5 Monitor / Strategy / AI Notes

This iteration adds lightweight foundations for the planned monitoring, strategy, and AI trade-draft functions.

## Monitoring

- `MonitorRule` stores custom symbol monitors such as quote volume thresholds.
- `MonitorEvent` records evaluations.
- Current metrics are explicit inputs to the evaluator; future work can feed them from Binance kline/ticker streams.
- `evaluate-live` now maps Binance 24hr ticker fields into monitor metrics.

## Strategy

- `Strategy` and `StrategyRun` store Freqtrade-style strategy definitions and runs.
- Supported starter types: `grid`, `ma_cross`, `ai_signal`.
- A `stoploss_config` is mandatory before a strategy can start.
- `run-once` can dry-run a strategy signal or execute one generated floating order when a valid PIN is supplied.
- No system-level fuse or auto-pause behavior is introduced.

## AI

- AI creates trade drafts only.
- AI drafts require a suggested order unless the action is `hold`.
- Drafts do not place orders; user confirmation or a later explicit execution endpoint is required.

## Data Boundary

- TradingView remains a visual chart only.
- Monitoring, strategy, and AI decisions must consume Binance-derived data.
