# GitHub Backup Sync

This project includes a local backup sync script for pushing the current working tree to a private GitHub repository.

## One-time setup

Create an empty private repository on GitHub, then run:

```powershell
cd D:\AI\JY20026\codex-fast-trade
.\scripts\github-backup-sync.ps1 -RemoteUrl git@github.com:YOUR_USER/codex-fast-trade-backup.git
```

HTTPS remotes also work:

```powershell
.\scripts\github-backup-sync.ps1 -RemoteUrl https://github.com/YOUR_USER/codex-fast-trade-backup.git
```

The script initializes Git if needed, adds the remote as `backup`, commits non-ignored files, and pushes to `main`.

## Daily use

After the remote is configured once:

```powershell
cd D:\AI\JY20026\codex-fast-trade
.\scripts\github-backup-sync.ps1
```

Custom commit message:

```powershell
.\scripts\github-backup-sync.ps1 -Message "backup: W9 settings panel"
```

Custom branch or remote name:

```powershell
.\scripts\github-backup-sync.ps1 -Branch backup-main -RemoteName backup
```

## Environment variables

These variables can be set instead of passing parameters:

```powershell
$env:GITHUB_BACKUP_REMOTE = "git@github.com:YOUR_USER/codex-fast-trade-backup.git"
$env:GITHUB_BACKUP_REMOTE_NAME = "backup"
$env:GITHUB_BACKUP_BRANCH = "main"
```

## Safety

The script refuses to sync staged files that look like local secrets or generated runtime artifacts, including `.env`, `data/`, SQLite databases, logs, `node_modules/`, and `dist/`.

Use `-AllowSecretFiles` only if you intentionally want to bypass that guard.
