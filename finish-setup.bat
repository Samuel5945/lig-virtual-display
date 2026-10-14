@echo off
setlocal EnableDelayedExpansion
title Finish Setup - remove duplicates and old driver

net session >nul 2>&1
if errorlevel 1 (
  echo Requesting administrator, click YES on UAC...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList 'elevated' -Verb RunAs"
  exit /b
)

set "DRV=C:\VirtualDisplay\driver"

echo ================================================================
echo   Finish setup
echo     1. remove the duplicate MttVDD device (devcon ran twice)
echo     2. remove the broken Parsec VDD and its driver package
echo     3. rescan and report
echo ================================================================
echo.

echo --- before ---
powershell -NoProfile -Command "Get-PnpDevice -Class Display -ErrorAction SilentlyContinue | Sort-Object InstanceId | ForEach-Object { '   ' + $_.Status.PadRight(9) + $_.FriendlyName + '   [' + $_.InstanceId + ']' }"
echo.

echo [1/4] removing duplicate MttVDD device ROOT\DISPLAY\0002
pushd "%DRV%"
devcon.exe remove "ROOT\DISPLAY\0002"
popd
timeout /t 3 /nobreak >nul
echo.

echo [2/4] removing Parsec device ROOT\DISPLAY\0000
pushd "%DRV%"
devcon.exe remove "ROOT\DISPLAY\0000"
popd
timeout /t 3 /nobreak >nul
echo.

echo [3/4] deleting Parsec driver package oem67.inf
pnputil /delete-driver oem67.inf /uninstall /force
timeout /t 3 /nobreak >nul
echo.

echo [4/4] rescanning
pushd "%DRV%"
devcon.exe rescan
popd
timeout /t 5 /nobreak >nul
echo.

echo --- after ---
powershell -NoProfile -Command "Get-PnpDevice -Class Display -ErrorAction SilentlyContinue | Sort-Object InstanceId | ForEach-Object { '   ' + $_.Status.PadRight(9) + $_.FriendlyName + '   [' + $_.InstanceId + ']' }"
echo.
echo --- displays attached to the desktop ---
powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Screen]::AllScreens | ForEach-Object { '   ' + $_.DeviceName + '   ' + $_.Bounds.Width + 'x' + $_.Bounds.Height + '   primary=' + $_.Primary }"
echo.

echo ================================================================
echo   Done. Press any key to close.
echo ================================================================
pause >nul
