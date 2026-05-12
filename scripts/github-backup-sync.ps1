param(
    [string]$RemoteUrl = $env:GITHUB_BACKUP_REMOTE,
    [string]$RemoteName = $env:GITHUB_BACKUP_REMOTE_NAME,
    [string]$Branch = $env:GITHUB_BACKUP_BRANCH,
    [string]$Message = "",
    [switch]$InitOnly,
    [switch]$AllowSecretFiles
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $RepoRoot

if ([string]::IsNullOrWhiteSpace($RemoteName)) {
    $RemoteName = "backup"
}
if ([string]::IsNullOrWhiteSpace($Branch)) {
    $Branch = "main"
}
if ([string]::IsNullOrWhiteSpace($Message)) {
    $Message = "backup: sync $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
}

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$GitArgs)
    & git @GitArgs
    if ($LASTEXITCODE -ne 0) {
        throw "git $($GitArgs -join ' ') failed with exit code $LASTEXITCODE"
    }
}

function Test-CommandAvailable {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Assert-NoSecretFilesStaged {
    if ($AllowSecretFiles) {
        return
    }

    $staged = & git diff --cached --name-only
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect staged files."
    }

    $blocked = @()
    foreach ($path in $staged) {
        $normalized = $path -replace "\\", "/"
        $name = Split-Path -Leaf $normalized
        if ($name -eq ".env.example") {
            continue
        }
        if (
            $normalized -match '(^|/)\.env($|[./])' -or
            $normalized -match '(^|/)data/' -or
            $normalized -match '\.db($|[-.])' -or
            $normalized -match '\.log$' -or
            $normalized -match 'node_modules/' -or
            $normalized -match '(^|/)dist/'
        ) {
            $blocked += $path
        }
    }

    if ($blocked.Count -gt 0) {
        Write-Host "Blocked staged files:" -ForegroundColor Yellow
        $blocked | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
        throw "Refusing to sync likely local, generated, or secret files. Fix .gitignore or rerun with -AllowSecretFiles if this is intentional."
    }
}

if (-not (Test-CommandAvailable "git")) {
    throw "Git is required but was not found in PATH."
}

if (-not (Test-Path ".git")) {
    Write-Host "Initializing Git repository at $RepoRoot"
    & git init -b $Branch
    if ($LASTEXITCODE -ne 0) {
        Invoke-Git init
        Invoke-Git checkout -B $Branch
    }
} else {
    $currentBranch = (& git branch --show-current).Trim()
    if ([string]::IsNullOrWhiteSpace($currentBranch)) {
        Invoke-Git checkout -B $Branch
    }
}

if (-not [string]::IsNullOrWhiteSpace($RemoteUrl)) {
    $existingRemote = @(& git remote) | Where-Object { $_ -eq $RemoteName }
    if ($existingRemote.Count -eq 0) {
        Invoke-Git remote add $RemoteName $RemoteUrl
    } else {
        Invoke-Git remote set-url $RemoteName $RemoteUrl
    }
}

Write-Host "Repository status before sync:"
Invoke-Git status --short

if ($InitOnly) {
    Write-Host "Init-only mode complete. No files were committed or pushed."
    exit 0
}

if ([string]::IsNullOrWhiteSpace($RemoteUrl)) {
    $configuredRemotes = @(& git remote)
    if ($configuredRemotes -notcontains $RemoteName) {
        Write-Host "No GitHub backup remote is configured. Pass -RemoteUrl or set GITHUB_BACKUP_REMOTE." -ForegroundColor Yellow
        exit 2
    }
    $remoteUrlFromGit = (& git remote get-url $RemoteName).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($remoteUrlFromGit)) {
        Write-Host "GitHub backup remote '$RemoteName' exists but has no usable URL." -ForegroundColor Yellow
        exit 2
    }
}

Invoke-Git add -A
Assert-NoSecretFilesStaged

$null = & git diff --cached --quiet
$hasStagedChanges = $LASTEXITCODE -ne 0
if ($hasStagedChanges) {
    Invoke-Git commit -m $Message
} else {
    Write-Host "No changes to commit."
}

$activeBranch = (& git branch --show-current).Trim()
if ([string]::IsNullOrWhiteSpace($activeBranch)) {
    $activeBranch = $Branch
    Invoke-Git checkout -B $activeBranch
}

Invoke-Git push -u $RemoteName "${activeBranch}:$Branch"
Write-Host "GitHub backup sync complete: $RemoteName/$Branch"
