@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-dev.ps1" -OpenBrowser
if errorlevel 1 (
  echo.
  echo Start failed. Check backend.err.log and frontend.err.log.
  pause
)
