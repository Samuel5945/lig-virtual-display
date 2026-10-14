@echo off
setlocal
title Sunshine + virtual display setup

net session >nul 2>&1
if errorlevel 1 (
  echo Requesting administrator, click YES on UAC...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList 'elevated' -Verb RunAs"
  exit /b
)

echo ================================================================
echo   Point Sunshine at the MttVDD virtual display
echo ================================================================
echo.
echo   This will:
echo     1. back up sunshine.conf
echo     2. restart Sunshine so it publishes its display list
echo     3. find the virtual display's device_id
echo     4. set output_name + dd_configuration_option=ensure_only_display
echo     5. restart Sunshine again
echo.
echo   Any active Moonlight stream will be interrupted.
echo.
pause

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0sunshine-setup.ps1"
set RC=%errorlevel%

echo.
echo ================================================================
if "%RC%"=="0" (
  echo   Finished.
) else (
  echo   Stopped with code %RC%  -  see the messages above.
)
echo ================================================================
pause
