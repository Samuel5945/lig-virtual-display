"""
VirtualDisplay panel - backend.

Thin wrapper around the proven engine scripts. The panel never reimplements
driver logic; it shells out to vdd-keepalive.py / vdd-switch.py so there is
exactly one implementation of the tricky parts.

All methods are synchronous and safe to call from a worker thread. They return
plain dicts so the same code works under --selftest (no GUI) and in the app.
"""

import json
import os
import re
import subprocess
import sys

ROOT = r"C:\VirtualDisplay"
PYTHON = r"C:\Program Files\Python312\python.exe"
PYTHONW = r"C:\Program Files\Python312\pythonw.exe"
KEEPALIVE = os.path.join(ROOT, "vdd-keepalive.py")
SWITCHER = os.path.join(ROOT, "vdd-switch.py")
SETTINGS = os.path.join(ROOT, "gui_settings.json")
LOG = os.path.join(ROOT, "vdd-keepalive.log")
DEVICE_ID = r"ROOT\DISPLAY\0000"
TASK_NAME = "VirtualDisplay"

# resolution presets offered in the UI; any "WxH@Hz" string is also accepted
RESOLUTIONS = [
    "1920x1080@60",
    "1920x1080@120",
    "1920x1080@144",
    "2560x1440@60",
    "2560x1440@120",
    "2560x1440@144",
    "3440x1440@60",
    "3840x2160@60",
    "3840x2160@120",
]

SWITCH_MODES = ["real", "virtual", "both", "toggle"]


def _run(args, timeout=90):
    """Run a command, return (rc, stdout, stderr). Never raises."""
    try:
        p = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout,
            cwd=ROOT, creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        return p.returncode, p.stdout or "", p.stderr or ""
    except subprocess.TimeoutExpired:
        return 124, "", "timeout after %ss" % timeout
    except Exception as exc:                                  # noqa: BLE001
        return 1, "", str(exc)


def _ka(*args):
    return _run([PYTHON, KEEPALIVE] + list(args))


def _sw(*args):
    return _run([PYTHON, SWITCHER] + list(args))


# --------------------------------------------------------------------------- #
# status
# --------------------------------------------------------------------------- #

def _physical_mode():
    """(w, h, hz, name) of the real monitor, via WMI. Returns None on failure."""
    ps = (
        "Get-CimInstance Win32_VideoController | "
        "Where-Object { $_.Name -notlike '*Parsec*' -and $_.Name -notlike '*Basic Render*' } | "
        "ForEach-Object { '{0}|{1}|{2}|{3}' -f $_.CurrentHorizontalResolution, "
        "$_.CurrentVerticalResolution, $_.CurrentRefreshRate, $_.Name }"
    )
    rc, out, _ = _run(["powershell", "-NoProfile", "-Command", ps], timeout=30)
    if rc != 0 or not out.strip():
        return None
    parts = out.strip().splitlines()[0].split("|")
    if len(parts) < 4:
        return None
    try:
        return int(parts[0]), int(parts[1]), int(parts[2]), parts[3]
    except ValueError:
        return None


def status():
    """Collect everything the UI needs in one dict."""
    rc, out, err = _ka("status")

    s = {
        "ok": rc == 0,
        "error": err.strip() if rc != 0 else "",
        "raw": out,
        "driver_version": None,
        "driver_error": None,
        "daemon_running": False,
        "daemon_pid": None,
        "virtual_count": 0,
        "virtual_displays": [],
        "orphan_entries": [],
        "physical": _physical_mode(),
        "configured_resolution": None,
        "follow_moonlight": False,
        "autostart_installed": None,
        "device_id": DEVICE_ID,
    }

    m = re.search(r"driver ver\s*:\s*(\d+)(?:\s*\(err\s*(\d+)\))?", out)
    if m:
        s["driver_version"] = int(m.group(1))
        s["driver_error"] = int(m.group(2)) if m.group(2) else 0

    m = re.search(r"daemon\s*:\s*(.+)", out)
    if m:
        txt = m.group(1).strip().lower()
        s["daemon_running"] = "not running" not in txt and txt != ""
        pm = re.search(r"pid\s*[=:]\s*(\d+)", m.group(1))
        if pm:
            s["daemon_pid"] = int(pm.group(1))

    m = re.search(r"virtual\s*:\s*(\d+)", out)
    if m:
        s["virtual_count"] = int(m.group(1))

    # every Parsec line that actually has a monitor attached
    for line in out.splitlines():
        if "Parsec Virtual Display Adapter" in line and "Monitor0" in line:
            nm = re.match(r"\s*(\\\\\.\\DISPLAY\d+)", line)
            if nm:
                s["virtual_displays"].append(nm.group(1))

    # orphan entries: adapter-level Parsec names with no monitor attached.
    # These are the residue of a runaway ADD loop - they occupy the driver's
    # slots so new displays never materialise. "未挂载" alone would mislead.
    for line in out.splitlines():
        if "Parsec Virtual Display Adapter" in line and "(no monitor)" in line:
            nm = re.match(r"\s*(\\\\\.\\DISPLAY\d+)", line)
            if nm:
                s["orphan_entries"].append(nm.group(1))

    # configured resolution / follow flag
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            cfg = json.load(f)
        s["configured_resolution"] = cfg.get("resolution")
        s["follow_moonlight"] = bool(cfg.get("follow_moonlight"))
    except Exception:                                          # noqa: BLE001
        pass

    # is the logon scheduled task registered?
    ps = (
        "if (Get-ScheduledTask -TaskName '%s' -ErrorAction SilentlyContinue) "
        "{ 'yes' } else { 'no' }" % TASK_NAME
    )
    rc2, out2, _ = _run(["powershell", "-NoProfile", "-Command", ps], timeout=30)
    if rc2 == 0:
        s["autostart_installed"] = out2.strip() == "yes"

    return s


# --------------------------------------------------------------------------- #
# actions
# --------------------------------------------------------------------------- #

def start(resolution=None):
    args = ["start"] + (["--resolution", resolution] if resolution else [])
    rc, out, err = _ka(*args)
    return {"ok": rc == 0, "out": out.strip(), "error": err.strip()}


def stop():
    rc, out, err = _ka("stop")
    return {"ok": rc == 0, "out": out.strip(), "error": err.strip()}


def restart(resolution=None):
    args = ["restart"] + (["--resolution", resolution] if resolution else [])
    rc, out, err = _ka(*args)
    return {"ok": rc == 0, "out": out.strip(), "error": err.strip()}


def clean():
    rc, out, err = _ka("clean")
    return {"ok": rc == 0, "out": out.strip(), "error": err.strip()}


def switch(mode):
    if mode not in SWITCH_MODES:
        return {"ok": False, "out": "", "error": "unknown mode: %s" % mode}
    rc, out, err = _sw(mode)
    return {"ok": rc == 0, "out": out.strip(), "error": err.strip()}


def set_resolution(value):
    """Persist the choice and restart the daemon so it takes effect."""
    if not re.match(r"^\d{3,5}x\d{3,5}@\d{2,3}$", value or ""):
        return {"ok": False, "out": "", "error": "bad format, expected WxH@Hz"}
    rc, out, err = _ka("start", "--resolution", value)
    return {"ok": rc == 0, "out": out.strip(), "error": err.strip()}


def reset_driver():
    """disable -> enable the adapter (clears the polluted slot table), then start."""
    _ka("stop")
    _run(["pnputil", "/disable-device", DEVICE_ID], timeout=60)
    _run(["pnputil", "/enable-device", DEVICE_ID], timeout=60)
    rc, out, err = _ka("start")
    return {"ok": rc == 0, "out": out.strip(), "error": err.strip()}


def autostart(install):
    """Install / remove the single logon scheduled task. Needs admin."""
    ps = (
        "$TaskName='{t}'; $Py='{py}'; $Ka='{ka}';"
        "if ('{flag}' -eq 'install') {{"
        "  $a=New-ScheduledTaskAction -Execute $Py -Argument \"`\"$Ka`\" start\" -WorkingDirectory '{root}';"
        "  $g=New-ScheduledTaskTrigger -AtLogOn;"
        "  $s=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
        "-RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Seconds 0);"
        "  $p=New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited;"
        "  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue;"
        "  Register-ScheduledTask -TaskName $TaskName -Action $a -Trigger $g -Settings $s -Principal $p "
        "-Description 'Virtual display keep-alive (single process, self-healing)' | Out-Null;"
        "  'installed'"
        "}} else {{"
        "  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue;"
        "  'removed'"
        "}}"
    ).format(t=TASK_NAME, py=PYTHON, ka=KEEPALIVE, root=ROOT,
             flag="install" if install else "remove")
    rc, out, err = _run(["powershell", "-NoProfile", "-Command", ps], timeout=60)
    return {"ok": rc == 0 and out.strip() in ("installed", "removed"),
            "out": out.strip(), "error": err.strip()}


def is_admin():
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:                                          # noqa: BLE001
        return False


def elevate_and_rerun():
    """Re-launch this program elevated. Returns False if UAC was declined."""
    import ctypes
    # lpParameters must NOT include the executable itself, only the arguments
    args = " ".join('"%s"' % a for a in sys.argv[1:])
    rc = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, args, None, 1)
    return int(rc) > 32


def log_tail(lines=40):
    try:
        with open(LOG, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-lines:])
    except Exception:                                          # noqa: BLE001
        return "(no log yet)"


def open_log():
    try:
        os.startfile(LOG)
        return {"ok": True, "out": "", "error": ""}
    except Exception as exc:                                  # noqa: BLE001
        return {"ok": False, "out": "", "error": str(exc)}
