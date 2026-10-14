@echo off
setlocal EnableDelayedExpansion
title Install MttVDD Virtual Display Driver

net session >nul 2>&1
if errorlevel 1 (
  echo Requesting administrator, click YES on UAC...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList 'elevated' -Verb RunAs"
  exit /b
)

set "DRV=C:\VirtualDisplay\driver"
set "CFGDIR=C:\VirtualDisplayDriver"

echo ================================================================
echo   MttVDD Virtual Display Driver  -  install
echo   source : %DRV%
echo   config : %CFGDIR%\vdd_settings.xml
echo ================================================================
echo.

if not exist "%DRV%\MttVDD.inf" (
  echo [FAIL] driver files not found in %DRV%
  pause & exit /b 1
)
if not exist "%DRV%\devcon.exe" (
  echo [FAIL] devcon.exe not found in %DRV%
  pause & exit /b 1
)

echo [0/4] current display adapters
echo ----------------------------------------------------------------
powershell -NoProfile -Command "Get-PnpDevice -Class Display -ErrorAction SilentlyContinue | ForEach-Object { '   ' + $_.Status + '  ' + $_.FriendlyName }"
echo.

echo [1/4] preparing config directory
if not exist "%CFGDIR%" mkdir "%CFGDIR%"
if exist "%CFGDIR%\vdd_settings.xml" (
  copy /y "%CFGDIR%\vdd_settings.xml" "%CFGDIR%\vdd_settings.xml.bak" >nul
  echo    existing config backed up to vdd_settings.xml.bak
)
copy /y "%DRV%\vdd_settings.xml" "%CFGDIR%\vdd_settings.xml" >nul
echo    config written
echo.

echo [2/4] installing driver  (devcon install MttVDD.inf Root\MttVDD)
echo ----------------------------------------------------------------
pushd "%DRV%"
devcon.exe install "MttVDD.inf" "Root\MttVDD"
set "RC=%errorlevel%"
popd
echo    devcon exit code = %RC%
echo.

echo [3/4] rescanning devices
devcon.exe rescan >nul 2>&1
timeout /t 4 /nobreak >nul
echo.

echo [4/4] result
echo ----------------------------------------------------------------
powershell -NoProfile -Command "Get-PnpDevice -Class Display -ErrorAction SilentlyContinue | ForEach-Object { '   ' + $_.Status + '  ' + $_.FriendlyName }"
echo.

echo ================================================================
echo   IF YOU GET A BLACK SCREEN:
echo     1. press  Win + P  and keep pressing Down then Enter
echo        to cycle display modes until the desktop returns
echo     2. if that fails, force-restart 3 times to enter Windows
echo        Recovery, then Safe Mode, and uninstall
echo        'Virtual Display Driver' in Device Manager
echo ================================================================
echo.
echo Done. Press any key to close.
pause >nul
