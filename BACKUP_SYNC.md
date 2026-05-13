# AI Backup Sync Guide

Use this file when an AI assistant or a human needs to upload the whole project state to GitHub.

## What "Full Upload" Means

The repository stores normal source files directly in Git.

Ignored local state is uploaded as an encrypted archive under `local-backups/`, including files such as:

- `.env`
- local SQLite databases under `data/` or `backend/data/`
- logs
- built frontend output such as `frontend/dist/`

The decrypt key is written beside the archive as `*.key.txt`, but it is ignored by Git and must stay local.

Dependency and cache folders are skipped by default because they are large and reproducible:

- `node_modules/`
- `.venv/`, `venv/`, `env/`
- `__pycache__/`
- pytest/ruff/mypy/vite caches
- `*.egg-info/`

Use `-IncludeDependencyCaches` only when a literal byte-for-byte local backup is required.

## One-Click Sync

```powershell
cd D:\AI\JY20026\codex-fast-trade
.\scripts\sync-full-backup.ps1
```

Custom message:

```powershell
.\scripts\sync-full-backup.ps1 -Message "backup: after feature update"
```

Run in the background:

```powershell
.\scripts\sync-full-backup.ps1 -Async
```

Skip encrypted local state and upload only tracked source changes:

```powershell
.\scripts\sync-full-backup.ps1 -SkipLocalState
```

Include dependency/cache directories in the encrypted archive:

```powershell
.\scripts\sync-full-backup.ps1 -IncludeDependencyCaches
```

## Restore Encrypted Local State

```powershell
cd D:\AI\JY20026\codex-fast-trade
.\scripts\restore-local-state-backup.ps1 `
  -BackupFile .\local-backups\<backup>.zip.aes `
  -KeyFile .\local-backups\<backup>.key.txt `
  -ExtractTo .\restored-local-state
```
