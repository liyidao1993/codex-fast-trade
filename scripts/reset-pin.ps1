param(
  [Parameter(Mandatory = $true)]
  [ValidatePattern('^\d{4,12}$')]
  [string]$Pin
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$EnvPath = Join-Path $Root ".env"

if (-not (Test-Path $EnvPath)) {
  throw ".env 不存在，请先运行 scripts\start-dev.ps1 初始化本地环境。"
}

$lines = Get-Content $EnvPath
$hasPin = $false
$hasHash = $false
$updated = foreach ($line in $lines) {
  if ($line -like "APP_PIN=*") {
    $hasPin = $true
    "APP_PIN=$Pin"
  } elseif ($line -like "APP_PIN_HASH=*") {
    $hasHash = $true
    "APP_PIN_HASH="
  } else {
    $line
  }
}
if (-not $hasPin) {
  $updated += "APP_PIN=$Pin"
}
if (-not $hasHash) {
  $updated += "APP_PIN_HASH="
}

Set-Content -Encoding UTF8 -Path $EnvPath -Value $updated

$backend = Get-NetTCPConnection -LocalPort 18080 -State Listen -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique
$backend | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }

Start-Process `
  -FilePath "uv" `
  -ArgumentList @("run", "--python", "3.11", "--with-editable", ".", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "18080") `
  -WorkingDirectory (Join-Path $Root "backend") `
  -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $Root "backend.log") `
  -RedirectStandardError (Join-Path $Root "backend.err.log")

Write-Host "PIN 已重置。后端已重启：http://127.0.0.1:18080"
