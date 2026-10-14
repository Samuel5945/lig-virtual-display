"""
MttVDD virtual display - core helpers.

Why this is small
-----------------
The previous Parsec VDD engine needed ~750 lines of driver IOCTL pinging,
a keepalive daemon and a guardian process, because Parsec only keeps a
display alive while something pings it.

MttVDD works the opposite way: it is **statically configured**. The driver
reads C:\\VirtualDisplayDriver\\vdd_settings.xml at load time and creates
the declared number of displays. They then simply persist.

So there is no daemon, no ping loop and no "driver wedged" state to recover
from. What is left to do is:

  * read / write the config XML
  * ask Windows what the driver actually exposes
  * reload the driver so config changes take effect
  * change the active mode of a virtual display

That is the whole surface, and it is all below.

Note on paths: C:\\VirtualDisplayDriver\\ is chosen by the driver, not by us.
It is the one location outside C:\\VirtualDisplay\\ and cannot be moved.
"""

import ctypes
import os
import subprocess
import xml.etree.ElementTree as ET
from ctypes import wintypes

ROOT = r"C:\VirtualDisplay"
DRIVER_DIR = os.path.join(ROOT, "driver")
CONFIG_PATH = r"C:\VirtualDisplayDriver\vdd_settings.xml"
DEVICE_ID = r"ROOT\DISPLAY\0001"          # the MttVDD device instance
DRIVER_MATCH = "Virtual Display Driver"    # DeviceString the driver reports

# ---------------- Win32 ----------------

_user32 = ctypes.windll.user32


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("DeviceName", ctypes.c_wchar * 32),
        ("DeviceString", ctypes.c_wchar * 128),
        ("StateFlags", wintypes.DWORD),
        ("DeviceID", ctypes.c_wchar * 128),
        ("DeviceKey", ctypes.c_wchar * 128),
    ]


class DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", ctypes.c_wchar * 32),
        ("dmSpecVersion", wintypes.WORD),
        ("dmDriverVersion", wintypes.WORD),
        ("dmSize", wintypes.WORD),
        ("dmDriverExtra", wintypes.WORD),
        ("dmFields", wintypes.DWORD),
        ("dmOrientation", ctypes.c_short),
        ("dmPaperSize", ctypes.c_short),
        ("dmPaperLength", ctypes.c_short),
        ("dmPaperWidth", ctypes.c_short),
        ("dmScale", ctypes.c_short),
        ("dmCopies", ctypes.c_short),
        ("dmDefaultSource", ctypes.c_short),
        ("dmPrintQuality", ctypes.c_short),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", ctypes.c_wchar * 32),
        ("dmLogPixels", wintypes.WORD),
        ("dmBitsPerPel", wintypes.DWORD),
        ("dmPelsWidth", wintypes.DWORD),
        ("dmPelsHeight", wintypes.DWORD),
        ("dmDisplayFlags", wintypes.DWORD),
        ("dmDisplayFrequency", wintypes.DWORD),
        ("dmICMMethod", wintypes.DWORD),
        ("dmICMIntent", wintypes.DWORD),
        ("dmMediaType", wintypes.DWORD),
        ("dmDitherType", wintypes.DWORD),
        ("dmReserved1", wintypes.DWORD),
        ("dmReserved2", wintypes.DWORD),
        ("dmPanningWidth", wintypes.DWORD),
        ("dmPanningHeight", wintypes.DWORD),
    ]


ENUM_CURRENT_SETTINGS = -1
CDS_UPDATEREGISTRY = 0x00000001
CDS_TEST = 0x00000002
DISP_CHANGE_SUCCESSFUL = 0
DISP_CHANGE_BADMODE = -2
DISP_CHANGE_FAILED = -1


def _decode(raw):
    """Console tools emit the OEM codepage (GBK on Chinese Windows);
    PowerShell leans UTF-8. Try both, never raise."""
    if not raw:
        return ""
    for enc in ("utf-8", "gbk", "cp936", "big5"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def _run(args, timeout=60):
    """Run a command -> (rc, stdout, stderr). Never raises."""
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout,
                           creationflags=0x08000000)  # CREATE_NO_WINDOW
        return p.returncode, _decode(p.stdout), _decode(p.stderr)
    except subprocess.TimeoutExpired:
        return 124, "", "timeout after %ss" % timeout
    except Exception as exc:                                  # noqa: BLE001
        return 1, "", str(exc)


# ---------------- config ----------------

def read_config(path=CONFIG_PATH):
    """Read vdd_settings.xml into a plain dict.

    Returns {count, gpu, refresh_rates[], resolutions[(w,h,hz)], options{}}.
    Raises FileNotFoundError / ET.ParseError so callers can report precisely.
    """
    tree = ET.parse(path)
    r = tree.getroot()
    cfg = {
        "path": path,
        "count": int((r.findtext("monitors/count") or "1").strip()),
        "gpu": (r.findtext("gpu/friendlyname") or "default").strip(),
        "refresh_rates": [int(e.text) for e in r.findall("global/g_refresh_rate")],
        "resolutions": [],
        "options": {},
    }
    for res in r.findall("resolutions/resolution"):
        try:
            cfg["resolutions"].append((
                int(res.findtext("width")),
                int(res.findtext("height")),
                int(res.findtext("refresh_rate")),
            ))
        except (TypeError, ValueError):
            continue
    opts = r.find("options")
    if opts is not None:
        for o in opts:
            cfg["options"][o.tag] = (o.text or "").strip()
    return cfg


def write_config(cfg, path=CONFIG_PATH):
    """Write a dict produced by read_config() back out.

    Comments in the original file are not preserved (ElementTree drops them).
    That is deliberate: the file is machine-managed from here on, and the
    header comment in driver/vdd_settings.xml is the human reference.
    """
    lines = ["<?xml version='1.0' encoding='utf-8'?>", "<vdd_settings>",
             "    <monitors>",
             "        <count>%d</count>" % cfg.get("count", 1),
             "    </monitors>",
             "    <gpu>",
             "        <friendlyname>%s</friendlyname>" % cfg.get("gpu", "default"),
             "    </gpu>",
             "    <global>"]
    for rate in cfg.get("refresh_rates", []):
        lines.append("        <g_refresh_rate>%d</g_refresh_rate>" % rate)
    lines += ["    </global>", "    <resolutions>"]
    for w, h, hz in cfg.get("resolutions", []):
        lines += ["        <resolution>",
                  "            <width>%d</width>" % w,
                  "            <height>%d</height>" % h,
                  "            <refresh_rate>%d</refresh_rate>" % hz,
                  "        </resolution>"]
    lines += ["    </resolutions>", "    <options>"]
    for k, v in (cfg.get("options") or {}).items():
        lines.append("        <%s>%s</%s>" % (k, v, k))
    lines += ["    </options>", "</vdd_settings>", ""]

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(lines))
    return path


# ---------------- driver / display state ----------------

def device_installed():
    """True if the MttVDD device exists and is started."""
    rc, out, _ = _run(["pnputil", "/enum-devices", "/instanceid", DEVICE_ID])
    if rc != 0:
        return False
    return ("\u5df2\u542f\u52a8" in out) or ("Started" in out)


def list_displays():
    """Every attached display: (device_name, adapter, w, h, hz, is_virtual).

    Reads real pixel modes via EnumDisplaySettings, so a HiDPI physical
    monitor reports 3840x2160 and not the DPI-scaled 1920x1080.
    """
    out = []
    i = 0
    while True:
        ad = DISPLAY_DEVICEW()
        ad.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        if not _user32.EnumDisplayDevicesW(None, i, ctypes.byref(ad), 0):
            break
        i += 1
        if i > 64:
            break
        name = ad.DeviceName
        if not name:
            continue
        mon = DISPLAY_DEVICEW()
        mon.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        has_monitor = bool(_user32.EnumDisplayDevicesW(
            name, 0, ctypes.byref(mon), 0))
        dm = DEVMODEW()
        dm.dmSize = ctypes.sizeof(DEVMODEW)
        if not _user32.EnumDisplaySettingsW(name, ENUM_CURRENT_SETTINGS,
                                            ctypes.byref(dm)):
            continue
        attached = bool(ad.StateFlags & 0x1)
        out.append({
            "device": name,
            "adapter": ad.DeviceString or "",
            "monitor": mon.DeviceString if has_monitor else "",
            "width": dm.dmPelsWidth,
            "height": dm.dmPelsHeight,
            "hz": dm.dmDisplayFrequency,
            "attached": attached,
            "primary": bool(ad.StateFlags & 0x4),
            "virtual": DRIVER_MATCH in (ad.DeviceString or ""),
        })
    return out


def virtual_displays():
    """Just the MttVDD displays."""
    return [d for d in list_displays() if d["virtual"]]


def available_modes(device):
    """All modes the driver offers for one display, as sorted (w,h,hz)."""
    modes = set()
    i = 0
    while True:
        dm = DEVMODEW()
        dm.dmSize = ctypes.sizeof(DEVMODEW)
        if not _user32.EnumDisplaySettingsW(device, i, ctypes.byref(dm)):
            break
        modes.add((dm.dmPelsWidth, dm.dmPelsHeight, dm.dmDisplayFrequency))
        i += 1
        if i > 2000:
            break
    return sorted(modes)


def set_mode(device, width, height, hz):
    """Switch one display to a specific mode. Persists across reboots.

    Refuses to touch a display that is not an MttVDD one, so a typo can never
    change the physical monitor's mode.
    """
    target = None
    for d in list_displays():
        if d["device"] == device and d["virtual"]:
            target = d
            break
    if target is None:
        return {"ok": False, "error": "%s is not a virtual display" % device}
    if (width, height, hz) not in available_modes(device):
        return {"ok": False,
                "error": "%dx%d@%d is not offered by the driver"
                         % (width, height, hz)}

    dm = DEVMODEW()
    dm.dmSize = ctypes.sizeof(DEVMODEW)
    _user32.EnumDisplaySettingsW(device, ENUM_CURRENT_SETTINGS, ctypes.byref(dm))
    dm.dmPelsWidth = width
    dm.dmPelsHeight = height
    dm.dmDisplayFrequency = hz
    dm.dmFields = 0x80000 | 0x100000 | 0x400000   # WIDTH|HEIGHT|FREQUENCY

    # test first so we never leave the display in a broken state
    rc = _user32.ChangeDisplaySettingsExW(
        device, ctypes.byref(dm), None, CDS_TEST, None)
    if rc != DISP_CHANGE_SUCCESSFUL:
        return {"ok": False, "error": "mode rejected (code %d)" % rc}

    rc = _user32.ChangeDisplaySettingsExW(
        device, ctypes.byref(dm), None, CDS_UPDATEREGISTRY, None)
    if rc != DISP_CHANGE_SUCCESSFUL:
        return {"ok": False, "error": "apply failed (code %d)" % rc}
    return {"ok": True, "out": "%s -> %dx%d@%d" % (device, width, height, hz)}


def reload_driver():
    """Disable + enable the device so config changes take effect. Needs admin."""
    rc1, _, e1 = _run(["pnputil", "/disable-device", DEVICE_ID])
    import time
    time.sleep(3)
    rc2, _, e2 = _run(["pnputil", "/enable-device", DEVICE_ID])
    time.sleep(5)
    if rc1 != 0 or rc2 != 0:
        return {"ok": False,
                "error": "reload needs administrator (disable rc=%d, enable rc=%d)"
                         % (rc1, rc2)}
    return {"ok": True, "out": "driver reloaded"}


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:                                          # noqa: BLE001
        return False


def status():
    """One call for the panel / CLI to render everything."""
    inst = device_installed()
    vds = virtual_displays()
    vd = vds[0] if vds else None
    cfg = None
    cfg_error = ""
    try:
        cfg = read_config()
    except FileNotFoundError:
        cfg_error = "config not found: %s" % CONFIG_PATH
    except ET.ParseError as exc:
        cfg_error = "config parse error: %s" % exc
    except Exception as exc:                                   # noqa: BLE001
        cfg_error = str(exc)

    return {
        "device_installed": inst,
        "device_id": DEVICE_ID,
        "config": cfg,
        "config_error": cfg_error,
        "config_path": CONFIG_PATH,
        "virtual": vd,
        "virtual_count": len(vds),
        "displays": list_displays(),
        "modes": available_modes(vd["device"]) if vd else [],
        "admin": is_admin(),
    }
