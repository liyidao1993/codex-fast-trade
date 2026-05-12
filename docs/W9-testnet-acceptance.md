# W9 Testnet Acceptance

Date: 2026-05-11

## Goal

Run real Binance Futures Testnet acceptance from the browser without editing `.env`.

## Setup

1. Open the app.
2. Login with the local PIN.
3. Open `Settings`.
4. Paste Binance Futures Testnet API Key and Secret.
5. Click `Save key`.
6. Click `Test connection`.

The key is saved in local SQLite and masked in the UI. Signed Binance requests prefer this saved key over `.env`.

## Acceptance Order

Use small testnet size first.

1. Test connection.
2. Load positions.
3. Submit a tiny floating LIMIT order.
4. Cancel the order from Activity.
5. Submit a tiny order with TP/SL.
6. Confirm protection order status appears in Activity.
7. Run reconcile and user-stream checks when enabled.

## Boundaries

- Testnet only for W9.
- No mainnet key.
- No file editing required.
- No circuit breaker or automatic strategy pause added.
