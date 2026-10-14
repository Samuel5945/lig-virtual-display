# Configure Sunshine to stream FROM the MttVDD virtual display, with the
# physical monitor switched off during the session.
#
# Why this is needed at all: with dd_configuration_option left at "disabled",
# Sunshine captures the primary display (the physical monitor) and only falls
# back to the virtual one after the physical disappears - that fallback costs
# an encoder rebuild mid-session. And "ensure_only_display" alone is not safe
# either: without output_name Sunshine would keep the display it captures
# (the physical) and deactivate the virtual one, i.e. exactly the opposite of
# what we want. So output_name must point at the virtual display first.
#
# output_name needs the display's *device_id* (a Sunshine/libdisplaydevice
# stable id like {2bdc1e09-...}), NOT its \\.\DISPLAYn name - the display name
# is tied to the current active topology and changes when displays are added,
# removed or switched, which is exactly the drift seen here (DISPLAY22 -> 38
# -> 91). Feeding a display name would fail the mapping and silently fall back
# to the default display. The only way to learn the id is to read Sunshine's
# own "Currently available display devices" list, which it writes to the log
# at startup.
#
# Restarting Sunshine needs admin, so this script is run elevated. The
# service restart proved unreliable through the API (one run left the app
# untouched), so the script asks the user to do it manually and simply waits
# for the fresh device list to appear - that signal cannot lie.

$ErrorActionPreference = 'Stop'
$cfgDir = 'C:\Program Files\Sunshine\config'
$conf   = Join-Path $cfgDir 'sunshine.conf'
$log    = Join-Path $cfgDir 'sunshine.log'
$svc    = 'SunshineService'
$MARK   = 'Currently available display devices:'

function Say($t) { Write-Host $t }

function BlockCount {
    try {
        ([regex]::Matches((Get-Content -LiteralPath $log -Raw), [regex]::Escape($MARK))).Count
    } catch { 0 }
}

function Wait-FreshList {
    param([int]$Before, [int]$Seconds = 120)
    Say '      waiting for a fresh device list in the log ...'
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 2
        if ((BlockCount) -gt $Before) { return $true }
    }
    return $false
}

function Ask-ManualRestart {
    Say ''
    Say '  >>> Please restart Sunshine by hand now:'
    Say '        right-click the Sunshine tray icon  ->  Quit'
    Say '        then start Sunshine again from the Start menu'
    Say '      (a Moonlight client will be dropped; that is expected)'
    Read-Host '  Press Enter once Sunshine is running again'
    if (-not (Wait-FreshList -Before (BlockCount) -Seconds 120)) {
        Say '      still no fresh device list - giving up.'
        exit 4
    }
}

function Try-ServiceRestart {
    Say '      trying Restart-Service ...'
    try {
        Restart-Service -Name $svc -Force -ErrorAction Stop
        return $true
    } catch {
        Say ('      Restart-Service failed: ' + $_.Exception.Message)
        return $false
    }
}

Say '================================================================'
Say '  Sunshine + MttVDD virtual display  -  setup'
Say '================================================================'
Say ''

# ---- 1. back up ---------------------------------------------------------
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$bak = "$conf.bak-vdd-$stamp"
Copy-Item -LiteralPath $conf -Destination $bak -Force
Say "[1/4] config backed up -> $(Split-Path $bak -Leaf)"

# ---- 2. get a fresh display list ---------------------------------------
$before = BlockCount
Say "[2/4] need a fresh device list from the log (current: $before)"

$ok = $false
if (Try-ServiceRestart) { $ok = Wait-FreshList -Before $before }
if (-not $ok) { Ask-ManualRestart }
Say '      fresh device list found.'

# ---- 3. parse it and write the config ----------------------------------
$txt = Get-Content -LiteralPath $log -Raw
$all = [regex]::Matches($txt, [regex]::Escape($MARK) + '\s*(\[.*?\n\])', 'Singleline')
$block = $all[$all.Count - 1].Groups[1].Value
$devices = @($block | ConvertFrom-Json)
Say ("      {0} display(s) in the latest list" -f $devices.Count)
foreach ($d in $devices) {
    $edid = $d.edid
    Say ("        - {0}  {1}  [{2}/{3}]" -f $d.display_name, $d.friendly_name,
         $(if ($edid) { $edid.manufacturer_id } else { '?' }),
         $d.device_id)
}

# MttVDD reports itself with EDID manufacturer "MTT" (product 1337) and the
# friendly name "VDD by MTT", so match on either.
$vd = @($devices | Where-Object {
    ($_.edid -and $_.edid.manufacturer_id -eq 'MTT') -or
    ($_.friendly_name -match 'MTT|VDD by')
}) | Select-Object -First 1

if (-not $vd) {
    Say ''
    Say 'FAILED: no MttVDD virtual display in the list above.'
    Say 'Nothing was changed - the config is untouched apart from the backup.'
    exit 3
}
Say ''
Say "[3/4] virtual display found: $($vd.friendly_name)  $($vd.device_id)"

$lines = Get-Content -LiteralPath $conf
# Only these two. Everything else is left exactly as it was: the default
# revert behaviour already restores the display when the last session ends,
# which is what we want, and every extra key is one more chance to get a
# value format wrong (dd_config_revert_on_disconnect, for instance, takes
# true/false rather than the enabled/disabled used elsewhere).
$want = @{
    'output_name'             = $vd.device_id
    'dd_configuration_option' = 'ensure_only_display'
}
$seen = @{}
$out = foreach ($line in $lines) {
    $m = [regex]::Match($line, '^\s*([a-z_]+)\s*=')
    if ($m.Success -and $want.ContainsKey($m.Groups[1].Value)) {
        $k = $m.Groups[1].Value
        $seen[$k] = $true
        "$k = $($want[$k])"
    } else {
        $line
    }
}
foreach ($k in $want.Keys) {
    if (-not $seen.ContainsKey($k)) { $out += "$k = $($want[$k])" }
}

$utf8bom = New-Object System.Text.UTF8Encoding $true
[System.IO.File]::WriteAllLines($conf, [string[]]$out, $utf8bom)
Say '      config updated:'
Say "        output_name = $($vd.device_id)"
Say '        dd_configuration_option = ensure_only_display'

# ---- 4. restart to apply -----------------------------------------------
Say "[4/4] restart Sunshine once more to apply."
if (-not (Try-ServiceRestart)) { Ask-ManualRestart }

Say ''
Say '----------------------------------------------------------------'
Say 'Done. Current config:'
Get-Content -LiteralPath $conf | ForEach-Object { Say "   $_" }
Say '----------------------------------------------------------------'
Say ''
Say 'Next: start a stream from Moonlight. The physical monitor should'
Say 'switch off for the duration and come back when you disconnect.'
Say 'If it does not come back, use Win+P or the panel Layout card.'
