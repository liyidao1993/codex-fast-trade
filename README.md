# Codex Fast Trade

Isolated Codex workspace for the lightweight Binance futures fast-trade executor.

This directory is intentionally separate from `../binance-fast-trade`, which is reserved for Kiro work.

## W1 Scope

- FastAPI backend skeleton.
- SQLite async storage with WAL enabled.
- Local PIN login with cookie session.
- Binance Futures Testnet REST wrapper.
- Decimal precision handling for `tickSize`, `stepSize`, and `minNotional`.
- Hard guard checks only. No circuit breaker, no daily loss fuse, no automatic strategy shutdown.
- W2 backend endpoints for floating orders, close-all, and reverse.
- W3 backend cores for TP/SL protection orders, chase decisions, and reconciliation planning.
- Monitoring, strategy, and AI draft foundations. Strategy execution requires explicit PIN when it places orders.
- W6 lightweight workers for monitor scans, scheduled strategy checks, and Binance user-stream order updates.
  Workers are disabled by default and can be inspected at `/api/v1/workers/status`.
- W7 activity workbench with local order, monitor, and strategy run streams under `/api/v1/activity/recent`.
- W8 AI draft workflow with local provider abstraction, validation, PIN approval, and optional execution through the existing floating-order path.
- W9 browser Settings panel for Binance Futures Testnet API Key setup and connection testing without editing files.

## Local Development

Double-click `START_Codex_Fast_Trade.bat` to start the backend, frontend, and browser in one step.
Use `RESTART_Codex_Fast_Trade.bat` if you want to force-restart only the Codex services.

```powershell
cd D:\AI\JY20026\codex-fast-trade\backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy ..\.env.example ..\.env
pytest
uvicorn app.main:app --reload --host 127.0.0.1 --port 18080
```

Open `http://127.0.0.1:18080/docs`.

Frontend dev server uses `http://127.0.0.1:18081` to stay isolated from Kiro or other Vite projects on `5173`.

If the local PIN is forgotten, reset it without editing files:

```powershell
cd D:\AI\JY20026\codex-fast-trade
.\scripts\reset-pin.ps1 -Pin 123456
```

## GitHub Backup Sync

Use the backup sync script to initialize Git and push this workspace to a private GitHub repository:

```powershell
cd D:\AI\JY20026\codex-fast-trade
.\scripts\github-backup-sync.ps1 -RemoteUrl git@github.com:YOUR_USER/codex-fast-trade-backup.git
```

After the first run, use `.\scripts\github-backup-sync.ps1` to commit and push later changes. See `docs/github-backup-sync.md` for options and safety notes.

## Principles

- Manual fast order path stays short: no queue, no AI, no heavy risk scoring.
- Trading decisions use Binance data only.
- All prices, quantities, and notionals use `Decimal`; never use `float` for order math.
- TP/SL protection and reconciliation are W2/W3 priorities.
