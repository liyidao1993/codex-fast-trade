$ErrorActionPreference = "Stop"

$OpenBrowser = $args -contains "-OpenBrowser"
$Restart = $args -contains "-Restart"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$BackendPort = if ($env:CODEX_BACKEND_PORT) { $env:CODEX_BACKEND_PORT } else { "18080" }
$FrontendPort = if ($env:CODEX_FRONTEND_PORT) { $env:CODEX_FRONTEND_PORT } else { "18081" }
$DatabasePath = (Join-Path $Root "data\app.db").Replace("\", "/")

$env:APP_PIN = if ($env:APP_PIN) { $env:APP_PIN } else { "123456" }
$env:DATABASE_URL = if ($env:DATABASE_URL) { $env:DATABASE_URL } else { "sqlite+aiosqlite:///$DatabasePath" }

function Get-ListenerPids([string]$Port) {
  @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique)
}

function Is-CodexProcess([int]$ProcessId) {
  $process = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
  return $process -and $process.CommandLine -and $process.CommandLine.Contains($Root)
}

function Stop-CodexListeners([string]$Port) {
  foreach ($processId in Get-ListenerPids $Port) {
    if (Is-CodexProcess $processId) {
      Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
  }
}

function Assert-PortAvailable([string]$Port, [string]$Name) {
  $pids = Get-ListenerPids $Port
  if ($pids.Count -eq 0) {
    return
  }
  foreach ($processId in $pids) {
    if (Is-CodexProcess $processId) {
      return
    }
  }
  throw "$Name port $Port is already used by another program. Codex will not touch it."
}

function Wait-HttpOk([string]$Url, [int]$TimeoutSec) {
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  do {
    try {
      $response = Invoke-WebRequest -UseBasicParsing $Url -TimeoutSec 2
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
        return $true
      }
    } catch {
      Start-Sleep -Milliseconds 400
    }
  } while ((Get-Date) -lt $deadline)
  return $false
}

if ($Restart) {
  Stop-CodexListeners $BackendPort
  Stop-CodexListeners $FrontendPort
  Start-Sleep -Seconds 1
}

Assert-PortAvailable $BackendPort "Backend"
Assert-PortAvailable $FrontendPort "Frontend"

if ((Get-ListenerPids $BackendPort).Count -eq 0) {
  Start-Process `
    -FilePath "uv" `
    -ArgumentList @("run", "--python", "3.11", "--with-editable", ".", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", $BackendPort) `
    -WorkingDirectory $Backend `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $Root "backend.log") `
    -RedirectStandardError (Join-Path $Root "backend.err.log")
}

if ((Get-ListenerPids $FrontendPort).Count -eq 0) {
  Start-Process `
    -FilePath "npm.cmd" `
    -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1", "--port", $FrontendPort, "--strictPort") `
    -WorkingDirectory $Frontend `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $Root "frontend.log") `
    -RedirectStandardError (Join-Path $Root "frontend.err.log")
}

Write-Host "Backend:  http://127.0.0.1:$BackendPort"
Write-Host "Frontend: http://127.0.0.1:$FrontendPort"

$backendOk = Wait-HttpOk "http://127.0.0.1:$BackendPort/healthz" 20
$frontendOk = Wait-HttpOk "http://127.0.0.1:$FrontendPort/" 30

if (-not $backendOk) {
  Write-Warning "Backend did not become ready. Check backend.err.log."
}
if (-not $frontendOk) {
  Write-Warning "Frontend did not become ready. Check frontend.err.log."
}
if ($OpenBrowser -and $frontendOk) {
  Start-Process "http://127.0.0.1:$FrontendPort/"
}
