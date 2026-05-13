param(
    [string]$Message = "",
    [string]$RemoteName = "origin",
    [string]$Branch = "",
    [switch]$SkipLocalState,
    [switch]$IncludeDependencyCaches,
    [switch]$Async
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($Async) {
    $argsList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $PSCommandPath)
    if (-not [string]::IsNullOrWhiteSpace($Message)) { $argsList += @("-Message", $Message) }
    if (-not [string]::IsNullOrWhiteSpace($RemoteName)) { $argsList += @("-RemoteName", $RemoteName) }
    if (-not [string]::IsNullOrWhiteSpace($Branch)) { $argsList += @("-Branch", $Branch) }
    if ($SkipLocalState) { $argsList += "-SkipLocalState" }
    if ($IncludeDependencyCaches) { $argsList += "-IncludeDependencyCaches" }
    $logDir = Join-Path (Split-Path -Parent $PSCommandPath) "..\local-backups"
    $outLog = Join-Path $logDir "sync-full-backup.last.out.log"
    $errLog = Join-Path $logDir "sync-full-backup.last.err.log"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    Start-Process powershell.exe -ArgumentList $argsList -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog
    Write-Host "Started async backup sync. Logs: $outLog ; $errLog"
    exit 0
}

$ScriptDir = Split-Path -Parent $PSCommandPath
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $RepoRoot

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$GitArgs)
    & git @GitArgs
    if ($LASTEXITCODE -ne 0) {
        throw "git $($GitArgs -join ' ') failed with exit code $LASTEXITCODE"
    }
}

function Fill-RandomBytes {
    param([byte[]]$Bytes)
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($Bytes) } finally { $rng.Dispose() }
}

function Copy-LocalState {
    param([string]$StageDir, [string[]]$IgnoredPaths)
    $included = New-Object System.Collections.Generic.List[string]
    $excluded = New-Object System.Collections.Generic.List[string]

    foreach ($rel in $IgnoredPaths) {
        $normalized = ($rel -replace "\\", "/").TrimEnd("/")
        if ([string]::IsNullOrWhiteSpace($normalized)) { continue }
        $dependencyCache = $normalized -match '(^|/)(node_modules|\.venv|venv|env|__pycache__|\.pytest_cache|\.ruff_cache|\.mypy_cache|\.vite)(/|$)' -or $normalized -match '(^|/).*\.egg-info(/|$)'
        $internalBackup = $normalized -match '^local-backups/'
        $gitInternal = $normalized -match '^\.git(/|$)'
        if ($gitInternal -or $internalBackup -or ($dependencyCache -and -not $IncludeDependencyCaches)) {
            $excluded.Add($normalized) | Out-Null
            continue
        }

        $src = Join-Path $RepoRoot $rel
        if (-not (Test-Path -LiteralPath $src)) { continue }
        $dest = Join-Path $StageDir $rel
        $parent = Split-Path -Parent $dest
        if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
        Copy-Item -LiteralPath $src -Destination $dest -Recurse -Force
        $included.Add($normalized) | Out-Null
    }

    $manifest = @(
        "created_at=$(Get-Date -Format o)"
        "repo=$RepoRoot"
        "include_dependency_caches=$IncludeDependencyCaches"
        ""
        "[included]"
    ) + $included + @("", "[excluded]") + $excluded
    Set-Content -LiteralPath (Join-Path $StageDir "LOCAL_STATE_MANIFEST.txt") -Value $manifest -Encoding UTF8
    return $included.Count
}

function New-EncryptedZip {
    param([string]$InputDir, [string]$OutputFile, [string]$KeyFile)
    $tempZip = Join-Path $env:TEMP ("full-backup-" + [guid]::NewGuid().ToString("N") + ".zip")
    Compress-Archive -Path (Join-Path $InputDir "*") -DestinationPath $tempZip -Force
    $plain = [System.IO.File]::ReadAllBytes($tempZip)

    $master = [byte[]]::new(64); Fill-RandomBytes $master
    $encKey = [byte[]]::new(32); [Array]::Copy($master, 0, $encKey, 0, 32)
    $macKey = [byte[]]::new(32); [Array]::Copy($master, 32, $macKey, 0, 32)
    $iv = [byte[]]::new(16); Fill-RandomBytes $iv

    $aes = [System.Security.Cryptography.Aes]::Create()
    $aes.Mode = [System.Security.Cryptography.CipherMode]::CBC
    $aes.Padding = [System.Security.Cryptography.PaddingMode]::PKCS7
    $aes.KeySize = 256
    $aes.Key = $encKey
    $aes.IV = $iv
    try {
        $encryptor = $aes.CreateEncryptor()
        $cipher = $encryptor.TransformFinalBlock($plain, 0, $plain.Length)
    } finally {
        if ($encryptor) { $encryptor.Dispose() }
        $aes.Dispose()
    }

    $magic = [System.Text.Encoding]::ASCII.GetBytes("CFTAESCBC1")
    $data = [byte[]]::new($magic.Length + $iv.Length + $cipher.Length)
    [Array]::Copy($magic, 0, $data, 0, $magic.Length)
    [Array]::Copy($iv, 0, $data, $magic.Length, $iv.Length)
    [Array]::Copy($cipher, 0, $data, $magic.Length + $iv.Length, $cipher.Length)
    $hmac = [System.Security.Cryptography.HMACSHA256]::new($macKey)
    try { $tag = $hmac.ComputeHash($data) } finally { $hmac.Dispose() }

    $out = [byte[]]::new($data.Length + $tag.Length)
    [Array]::Copy($data, 0, $out, 0, $data.Length)
    [Array]::Copy($tag, 0, $out, $data.Length, $tag.Length)
    [System.IO.File]::WriteAllBytes($OutputFile, $out)

    $keyText = @(
        "backup_file=$([System.IO.Path]::GetFileName($OutputFile))"
        "algorithm=AES-256-CBC-HMAC-SHA256"
        "key_base64=$([Convert]::ToBase64String($master))"
        "created_at=$(Get-Date -Format o)"
        "restore_script=scripts/restore-local-state-backup.ps1"
    ) -join "`r`n"
    Set-Content -LiteralPath $KeyFile -Value $keyText -NoNewline -Encoding ASCII
    Remove-Item -Force -LiteralPath $tempZip
}

if (-not (Test-Path ".git")) { Invoke-Git init -b main }
if ([string]::IsNullOrWhiteSpace($Branch)) {
    $Branch = (& git branch --show-current).Trim()
    if ([string]::IsNullOrWhiteSpace($Branch)) { $Branch = "main" }
}
if ([string]::IsNullOrWhiteSpace($Message)) {
    $Message = "backup: full sync $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
}

if (-not $SkipLocalState) {
    $backupDir = Join-Path $RepoRoot "local-backups"
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $projectName = Split-Path -Leaf $RepoRoot
    $stage = Join-Path $env:TEMP "$projectName-full-state-$stamp"
    Remove-Item -Recurse -Force -LiteralPath $stage -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $stage | Out-Null
    $ignored = (& git status --ignored --porcelain=v1) | Where-Object { $_.StartsWith("!! ") } | ForEach-Object { $_.Substring(3) }
    $count = Copy-LocalState -StageDir $stage -IgnoredPaths $ignored
    if ($count -gt 0) {
        $encrypted = Join-Path $backupDir "$projectName-full-state-$stamp.zip.aes"
        $keyFile = Join-Path $backupDir "$projectName-full-state-$stamp.key.txt"
        New-EncryptedZip -InputDir $stage -OutputFile $encrypted -KeyFile $keyFile
        Write-Host "Encrypted local state: $encrypted"
        Write-Host "Local-only decrypt key: $keyFile"
    } else {
        Write-Host "No ignored local state to encrypt."
    }
    Remove-Item -Recurse -Force -LiteralPath $stage -ErrorAction SilentlyContinue
}

Invoke-Git add -A
Invoke-Git add -f local-backups/*.zip.aes
$stagedKeys = & git diff --cached --name-only | Where-Object { $_ -match '\.key\.txt$' }
if ($stagedKeys) {
    throw "Refusing to commit local decrypt key files: $($stagedKeys -join ', ')"
}

$null = & git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    Invoke-Git commit -m $Message
} else {
    Write-Host "No tracked changes to commit."
}

Invoke-Git push -u $RemoteName "${Branch}:$Branch"
Write-Host "Full backup sync complete."
