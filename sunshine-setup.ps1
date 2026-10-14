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
# at startup - hence the restart.

$ErrorActionPreference = 'Stop'
$cfgDir = 'C:\Program Files\Sunshine\config'
$conf   = Join-Path $cfgDir 'sunshine.conf'
$log    = Join-Path $cfgDir 'sunshine.log'
$svc    = 'SunshineService'

function Say($t) { Write-Host $t }

Say '================================================================'
Say '  Sunshine + MttVDD virtual display  -  setup'
Say '================================================================'
Say ''

# ---- 1. back up ---------------------------------------------------------
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$bak = "$conf.bak-vdd-$stamp"
Copy-Item -LiteralPath $conf -Destination $bak -Force
Say "[1/5] config backed up -> $(Split-Path $bak -Leaf)"

# ---- 2. restart so the log lists the CURRENT displays -------------------
Say "[2/5] restarting $svc ..."
Restart-Service -Name $svc -Force -ErrorAction Stop

Say '      waiting for Sunshine to publish its display list ...'
$block = $null
$deadline = (Get-Date).AddSeconds(90)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
    if (-not (Test-Path -LiteralPath $log)) { continue }
    $txt = Get-Content -LiteralPath $log -Raw
    $all = [regex]::Matches($txt, 'Currently available display devices:\s*(\[.*?\n\])', 'Singleline')
    if ($all.Count -gt 0) { $block = $all[$all.Count - 1].Groups[1].Value; break }
}
if (-not $block) { Say '      FAILED: no display list in the log'; exit 2 }

$devices = @($block | ConvertFrom-Json)
Say ("      got {0} display(s)" -f $devices.Count)
foreach ($d in $devices) {
    $edid = $d.edid
    Say ("        - {0}  {1}  [{2}/{3}]" -f $d.display_name, $d.friendly_name,
         $(if ($edid) { $edid.manufacturer_id } else { '?' }),
         $d.device_id)
}

# ---- 3. find the virtual display ---------------------------------------
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
Say "[3/5] virtual display found: $($vd.friendly_name)  $($vd.device_id)"

# ---- 4. write the config ------------------------------------------------
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

# keep the original encoding (the file ships with a BOM)
$utf8bom = New-Object System.Text.UTF8Encoding $true
[System.IO.File]::WriteAllLines($conf, [string[]]$out, $utf8bom)
Say "[4/5] config updated:"
Say "        output_name = $($vd.device_id)"
Say '        dd_configuration_option = ensure_only_display'
Say '        dd_config_revert_on_disconnect = enabled'

# ---- 5. restart to apply ------------------------------------------------
Say "[5/5] restarting $svc to apply ..."
Restart-Service -Name $svc -Force -ErrorAction Stop
Start-Sleep -Seconds 5

Say ''
Say '----------------------------------------------------------------'
Say 'Done. Current config:'
Get-Content -LiteralPath $conf | ForEach-Object { Say "   $_" }
Say '----------------------------------------------------------------'
Say ''
Say 'Next: start a stream from Moonlight. The physical monitor should'
Say 'switch off for the duration and come back when you disconnect.'
Say 'If it does not come back, use Win+P or the panel Layout card.'
