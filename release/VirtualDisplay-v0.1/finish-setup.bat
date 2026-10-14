@echo off
setlocal EnableDelayedExpansion
title Finish Setup - remove duplicate, reload driver

net session >nul 2>&1
if errorlevel 1 (
  echo Requesting administrator, click YES on UAC...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList 'elevated' -Verb RunAs"
  exit /b
)

set "DRV=C:\VirtualDisplay\driver"
set "CFGDIR=C:\VirtualDisplayDriver"
set "KEEP=ROOT\DISPLAY\0001"
set "DUP=ROOT\DISPLAY\0002"

echo ================================================================
echo   Finish setup  (v2)
echo     [1] remove duplicate MttVDD device
echo     [2] make sure the old Parsec device is gone
echo     [3] drop the old Parsec driver package if still present
echo     [4] refresh config and reload the driver
echo     [5] rescan and report
echo ================================================================
echo.

echo --- before ---
powershell -NoProfile -Command "Get-PnpDevice -Class Display -ErrorAction SilentlyContinue | Sort-Object InstanceId | ForEach-Object { '   ' + $_.Status.PadRight(9) + $_.FriendlyName + '   [' + $_.InstanceId + ']' }"
echo.

echo [1/5] removing duplicate device %DUP%
pnputil /remove-device "%DUP%"
timeout /t 3 /nobreak >nul
echo.

echo [2/5] removing Parsec device ROOT\DISPLAY\0000 if still present
pnputil /remove-device "ROOT\DISPLAY\0000"
timeout /t 2 /nobreak >nul
echo.

echo [3/5] removing Parsec driver package oem67.inf if still present
pnputil /delete-driver oem67.inf /uninstall /force
timeout /t 2 /nobreak >nul
echo.

echo [4/5] refreshing config and reloading the driver
if not exist "%CFGDIR%" mkdir "%CFGDIR%"
copy /y "%DRV%\vdd_settings.xml" "%CFGDIR%\vdd_settings.xml" >nul
echo    config refreshed from %DRV%\vdd_settings.xml
echo    reloading %KEEP% ...
pnputil /disable-device "%KEEP%"
timeout /t 3 /nobreak >nul
pnputil /enable-device "%KEEP%"
timeout /t 6 /nobreak >nul
echo.

echo [5/5] rescanning
pushd "%DRV%"
devcon.exe rescan >nul 2>&1
popd
timeout /t 5 /nobreak >nul
echo.

echo --- after : display adapters ---
powershell -NoProfile -Command "Get-PnpDevice -Class Display -ErrorAction SilentlyContinue | Sort-Object InstanceId | ForEach-Object { '   ' + $_.Status.PadRight(9) + $_.FriendlyName + '   [' + $_.InstanceId + ']' }"
echo.
echo --- after : real pixel modes ---
powershell -NoProfile -Command "Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue | Where-Object { $_.CurrentHorizontalResolution } | ForEach-Object { '   ' + $_.Name.PadRight(32) + $_.CurrentHorizontalResolution + 'x' + $_.CurrentVerticalResolution + ' @ ' + $_.CurrentRefreshRate + 'Hz' }"
echo.
echo ================================================================
echo   Done. Press any key to close.
echo ================================================================
pause >nul
