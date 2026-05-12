# W7 Activity Workbench

Date: 2026-05-11

## Scope

W7 starts turning the UI into a real trading workbench. The first step is local activity visibility: orders, order events, monitor events, and strategy runs can now be queried and displayed.

## Backend

- `GET /api/v1/orders`
- `GET /api/v1/orders/events`
- `GET /api/v1/orders/protections`
- `DELETE /api/v1/orders/{client_order_id}`
- `GET /api/v1/monitors/events`
- `GET /api/v1/monitors/alerts`
- `POST /api/v1/monitors/alerts/{alert_id}/ack`
- `GET /api/v1/strategies/runs`
- `GET /api/v1/activity/recent`

`/api/v1/activity/recent` is the preferred UI endpoint. It aggregates recent local trading activity, protection orders, monitor events, and strategy runs into one response so the frontend does not need to poll multiple endpoints.

Cancelable local orders are marked in the activity stream. Actual cancellation still goes to Binance and requires a second PIN.

Triggered monitor rules now create local alerts. Alerts are local state only; they do not pause strategies or block trading.

## Frontend

- Added an activity panel to the right-side workbench.
- Added a position snapshot panel using Binance account positions.
- Added a cancel action for cancelable order rows.
- Activity is refreshed every 4 seconds after login.
- TradingView remains visual-only. Activity data comes from the local database and Binance-driven backend flows.

## Next

- Add retry actions for local order rows.
- Add protection order manual re-attach from failed protection rows.
