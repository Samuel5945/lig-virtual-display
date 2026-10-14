<#
.SYNOPSIS
  Unified control entry for the virtual display.

.DESCRIPTION
  Single entry point for everything virtual-display related. Everything lives
  in C:\VirtualDisplay - no other directory, no second process, no duplicate
  executables.

  Subcommands:
    start        start the keep-alive daemon (single process, self-healing)
    stop         stop the daemon and unplug the virtual display
    restart      stop then start
    status       show driver / display / daemon state
    switch       switch the desktop between real / virtual / both (menu)
    resolution   set the virtual display resolution, e.g. 2560x1440@60
    clean        force-remove leftover virtual displays
    reset        reset the Parsec driver (clears stale slots) then start  [needs admin]
    panel        open the GUI panel
    autostart    install or remove the single logon scheduled task  [needs admin]
    help         this text

  No administrator rights needed except for 'reset' and 'autostart'.
#>

param(
  [Parameter(Position = 0)]
  [string]$Cmd = 'help',
  [Parameter(Position = 1)]
  [string]$Arg
)

$ErrorActionPreference = 'Stop'
$Root = 'C:\VirtualDisplay'
$Py = 'C:\Program Files\Python312\python.exe'
$KeepAlive = Join-Path $Root 'vdd-keepalive.py'
$Switcher = Join-Path $Root 'vdd-switch.py'
$Panel = Join-Path $Root 'VirtualDisplayPanel.exe'
$TaskName = 'VirtualDisplay'

function Need-File([string]$p) {
  if (-not (Test-Path $p)) { Write-Host "[FAIL] missing: $p"; exit 1 }
}

Need-File $KeepAlive

switch ($Cmd.ToLower()) {

  'start' {
    $res = $Arg
    if ($res) {
      & $Py $KeepAlive start --resolution $res
    } else {
      & $Py $KeepAlive start
    }
  }

  'stop' { & $Py $KeepAlive stop }

  'restart' {
    & $Py $KeepAlive stop
    Start-Sleep -Seconds 2
    if ($Arg) { & $Py $KeepAlive start --resolution $Arg } else { & $Py $KeepAlive start }
  }

  'status' { & $Py $KeepAlive status }

  'clean' { & $Py $KeepAlive clean }

  'reset' {
    # The Parsec driver keeps an internal slot table. A long add/remove thrash
    # (e.g. 672 self-heal cycles) leaves stale slots behind: new ADDs land in
    # them but never materialise as a monitor. Disable/enable of the adapter
    # resets the table without a reboot.
    $id = 'ROOT\DISPLAY\0000'
    Write-Host "[1/4] stopping keep-alive ..."
    & $Py $KeepAlive stop
    Start-Sleep -Seconds 2

    Write-Host "[2/4] disabling $id (clears the stale slot table) ..."
    & pnputil /disable-device $id
    Start-Sleep -Seconds 3

    Write-Host "[3/4] re-enabling ..."
    & pnputil /enable-device $id
    Start-Sleep -Seconds 5

    Write-Host "[4/4] starting keep-alive ..."
    & $Py $KeepAlive start
    Start-Sleep -Seconds 6
    Write-Host ""
    Write-Host "--- status ---"
    & $Py $KeepAlive status
  }

  'resolution' {
    if (-not $Arg) { Write-Host "usage: vdd.ps1 resolution <WxH@Hz>   e.g. 2560x1440@60"; exit 1 }
    & $Py $KeepAlive start --resolution $Arg
    Write-Host "resolution set to $Arg (daemon restarted)"
  }

  'switch' {
    Need-File $Switcher
    if (-not $Arg) {
      Write-Host ""
      Write-Host "  Which display should the desktop show?"
      Write-Host "    1) real only      (physical monitor)"
      Write-Host "    2) virtual only   (virtual display)"
      Write-Host "    3) both (extend)"
      Write-Host "    4) toggle to the other one"
      Write-Host "    5) just show status"
      $sel = Read-Host "  pick [1-5]"
      switch ($sel) {
        '1' { $Arg = 'real' }
        '2' { $Arg = 'virtual' }
        '3' { $Arg = 'both' }
        '4' { $Arg = 'toggle' }
        default { $Arg = 'status' }
      }
    }
    & $Py $Switcher $Arg
  }

  'panel' {
    Need-File $Panel
    Start-Process $Panel
  }

  'autostart' {
    $mode = if ($Arg) { $Arg.ToLower() } else { 'install' }

    if ($mode -eq 'remove' -or $mode -eq 'uninstall') {
      Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
      Write-Host "scheduled task '$TaskName' removed"
    }
    else {
      $action = New-ScheduledTaskAction -Execute $Py -Argument "`"$KeepAlive`" start" -WorkingDirectory $Root
      $trigger = New-ScheduledTaskTrigger -AtLogOn
      $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit (New-TimeSpan -Seconds 0)
      $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

      Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal -Description "Virtual display keep-alive (single process, self-healing)" | Out-Null

      Write-Host "scheduled task '$TaskName' installed (runs at logon, auto-restarts on failure)"
      Write-Host "  -> replaces the old guardian process: the task's own restart-on-failure does that job now"
    }
  }

  default {
    Write-Host ""
    Write-Host "  VirtualDisplay control - everything lives in $Root"
    Write-Host ""
    Write-Host "    start [WxH@Hz]   start the keep-alive daemon"
    Write-Host "    stop             stop and unplug the virtual display"
    Write-Host "    restart          stop then start"
    Write-Host "    status           driver / display / daemon state"
    Write-Host "    switch [mode]    real | virtual | both | toggle | status (no arg = menu)"
    Write-Host "    resolution X     set resolution, e.g. 2560x1440@60"
    Write-Host "    clean            force-remove leftover virtual displays"
    Write-Host "    reset            reset the Parsec driver, then start  [admin]"
    Write-Host "    panel            open the GUI"
    Write-Host "    autostart [rm]   install / remove the logon scheduled task  [admin]"
    Write-Host ""
    Write-Host "  root dir : $Root"
    Write-Host "  log      : $(Join-Path $Root 'vdd-keepalive.log')"
    Write-Host ""
  }
}
