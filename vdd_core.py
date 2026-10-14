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
import re
import subprocess
import xml.etree.ElementTree as ET
from ctypes import wintypes

ROOT = r"C:\VirtualDisplay"
DRIVER_DIR = os.path.join(ROOT, "driver")
CONFIG_PATH = r"C:\VirtualDisplayDriver\vdd_settings.xml"
# The device instance number (ROOT\DISPLAY\0001 on this machine) is assigned
# when the driver is installed and differs from machine to machine, so it must
# be discovered rather than hardcoded - otherwise a panel copied to another PC
# looks for an instance that does not exist there.
DEVICE_STARTED_MARKS = ("\u5df2\u542f\u52a8", "Started")   # 已启动 / Started


def find_device():
    """Instance id of the running MttVDD device, or None.

    Matches on the driver's own friendly name, "Virtual Display Driver", which
    is English whatever the OS language is (pnputil's labels are localised, the
    device description is not).
    """
    rc, out, _ = _run(["pnputil", "/enum-devices", "/class", "Display"])
    if rc != 0:
        return None
    for blk in re.split(r"\n\s*\n", out):
        if DRIVER_MATCH not in blk:
            continue
        m = re.search(r"ROOT\\DISPLAY\\\d+", blk)
        if not m:
            continue
        if any(k in blk for k in DEVICE_STARTED_MARKS):
            return m.group(0)
    return None
DRIVER_MATCH = "Virtual Display Driver"    # DeviceString the driver reports

# ---------------- Win32 ----------------

_user32 = ctypes.windll.user32


def _ensure_dpi_awareness():
    """Declare this process DPI aware, once, at import.

    Without it Windows virtualises DPI and GetDpiForMonitor cheerfully reports
    96 for every monitor - i.e. every display looks like 100% scaling, which is
    exactly how this was first misread. Best effort: whoever set awareness
    first wins, and a failure here is not fatal.
    """
    try:
        DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
        if _user32.SetProcessDpiAwarenessContext(
                DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2):
            return True
    except Exception:                                          # noqa: BLE001
        pass
    try:
        if ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0:  # per-monitor
            return True
    except Exception:                                          # noqa: BLE001
        pass
    try:
        return bool(_user32.SetProcessDPIAware())
    except Exception:                                          # noqa: BLE001
        return False


DPI_AWARE = _ensure_dpi_awareness()


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
    """DEVMODE in its *display* form.

    dmOrientation..dmPrintQuality is a union: for display devices it holds
    dmPosition (POINTL) + dmDisplayOrientation + dmDisplayFixedOutput instead
    of the eight printer shorts. Reading positions is what lets us tell
    "extend" apart from "clone" and move a display around.
    """
    _fields_ = [
        ("dmDeviceName", ctypes.c_wchar * 32),
        ("dmSpecVersion", wintypes.WORD),
        ("dmDriverVersion", wintypes.WORD),
        ("dmSize", wintypes.WORD),
        ("dmDriverExtra", wintypes.WORD),
        ("dmFields", wintypes.DWORD),
        ("dmPositionX", ctypes.c_long),
        ("dmPositionY", ctypes.c_long),
        ("dmDisplayOrientation", wintypes.DWORD),
        ("dmDisplayFixedOutput", wintypes.DWORD),
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
CDS_SET_PRIMARY = 0x00000010
DISP_CHANGE_SUCCESSFUL = 0
DISP_CHANGE_BADMODE = -2
DISP_CHANGE_FAILED = -1

DM_POSITION = 0x00000020
DM_PELSWIDTH = 0x00080000
DM_PELSHEIGHT = 0x00100000
DM_DISPLAYFREQUENCY = 0x00400000

# SetDisplayConfig flags. Values matter: SDC_TOPOLOGY_SUPPLIED is 0x10, not
# 0x400 (that is SDC_ALLOW_CHANGES), and it may NOT be combined with the other
# topology flags - it means "caller supplies its own path array" and requires
# that array to be non-NULL.
SDC_TOPOLOGY_INTERNAL = 0x00000001
SDC_TOPOLOGY_CLONE = 0x00000002
SDC_TOPOLOGY_EXTEND = 0x00000004
SDC_TOPOLOGY_EXTERNAL = 0x00000008
SDC_VALIDATE = 0x00000040
SDC_APPLY = 0x00000080

TOPOLOGIES = {
    "extend":   (SDC_TOPOLOGY_EXTEND,   "扩展（物理屏 + 虚拟屏）"),
    "virtual":  (SDC_TOPOLOGY_EXTERNAL, "只用虚拟屏（关掉物理屏）"),
    "physical": (SDC_TOPOLOGY_INTERNAL, "只用物理屏"),
    "clone":    (SDC_TOPOLOGY_CLONE,    "复制（两块屏显示相同内容）"),
}


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
    return find_device() is not None


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
            "x": dm.dmPositionX,
            "y": dm.dmPositionY,
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
    dev = find_device()
    if not dev:
        return {"ok": False,
                "error": "no running MttVDD device found (is the driver installed?)"}
    rc1, _, e1 = _run(["pnputil", "/disable-device", dev])
    import time
    time.sleep(3)
    rc2, _, e2 = _run(["pnputil", "/enable-device", dev])
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


# ---------------- multi-monitor: topology, position, primary ----------------

_user32.SetDisplayConfig.argtypes = [wintypes.UINT, ctypes.c_void_p,
                                     wintypes.UINT, ctypes.c_void_p,
                                     wintypes.UINT]
_user32.SetDisplayConfig.restype = ctypes.c_long


def topology_valid(name):
    """True if Windows will accept this topology right now."""
    if name not in TOPOLOGIES:
        return False
    code = TOPOLOGIES[name][0]
    return _user32.SetDisplayConfig(0, None, 0, None, SDC_VALIDATE | code) == 0


def set_topology(name):
    """Switch between extend / only-virtual / only-physical / clone.

    NOTE for callers: "virtual" turns the physical monitor OFF. If the user is
    looking at this panel on the physical monitor, their screen goes dark until
    it is switched back - the UI must warn before offering it.
    """
    if name not in TOPOLOGIES:
        return {"ok": False, "error": "unknown topology: %s" % name}
    code, _label = TOPOLOGIES[name]
    rc = _user32.SetDisplayConfig(0, None, 0, None, SDC_APPLY | code)
    if rc != 0:
        return {"ok": False, "error": "SetDisplayConfig failed (code %d)" % rc}
    return {"ok": True, "out": "已切换到「%s」" % TOPOLOGIES[name][1]}


def current_topology():
    """Infer the active topology from what is actually on the desktop."""
    attached = [d for d in list_displays() if d["attached"]]
    vds = [d for d in attached if d["virtual"]]
    phys = [d for d in attached if not d["virtual"]]
    if not attached:
        return None
    if vds and not phys:
        return "virtual"
    if phys and not vds:
        return "physical"
    if vds and phys:
        v, p = vds[0], phys[0]
        same_place = (v["x"] == p["x"] and v["y"] == p["y"])
        same_size = (v["width"] == p["width"] and v["height"] == p["height"])
        return "clone" if (same_place and same_size) else "extend"
    return None


def set_position(device, x, y):
    """Move a display to (x, y) in the virtual desktop.

    Only virtual displays are accepted - a typo must never shove the physical
    monitor somewhere off-screen.
    """
    target = None
    for d in list_displays():
        if d["device"] == device and d["virtual"]:
            target = d
            break
    if target is None:
        return {"ok": False, "error": "%s is not a virtual display" % device}

    dm = DEVMODEW()
    dm.dmSize = ctypes.sizeof(DEVMODEW)
    _user32.EnumDisplaySettingsW(device, ENUM_CURRENT_SETTINGS, ctypes.byref(dm))
    dm.dmPositionX = int(x)
    dm.dmPositionY = int(y)
    dm.dmFields = DM_POSITION | DM_PELSWIDTH | DM_PELSHEIGHT | DM_DISPLAYFREQUENCY
    rc = _user32.ChangeDisplaySettingsExW(
        device, ctypes.byref(dm), None, CDS_UPDATEREGISTRY, None)
    if rc != DISP_CHANGE_SUCCESSFUL:
        return {"ok": False, "error": "move failed (code %d)" % rc}
    return {"ok": True, "out": "%s 移到 (%d, %d)" % (device, x, y)}


def place_beside(device, side):
    """Put the virtual display to the left/right/above/below the primary."""
    virtual = None
    for d in list_displays():
        if d["device"] == device and d["virtual"]:
            virtual = d
            break
    if virtual is None:
        return {"ok": False, "error": "%s is not a virtual display" % device}

    others = [d for d in list_displays() if d["attached"] and d["device"] != device]
    if not others:
        return {"ok": False, "error": "没有其它显示器可以参照"}
    ref = [d for d in others if d["primary"]] or others
    r = ref[0]

    if side == "right":
        pos = (r["x"] + r["width"], r["y"])
    elif side == "left":
        pos = (r["x"] - virtual["width"], r["y"])
    elif side == "above":
        pos = (r["x"], r["y"] - virtual["height"])
    elif side == "below":
        pos = (r["x"], r["y"] + r["height"])
    else:
        return {"ok": False, "error": "unknown side: %s" % side}
    return set_position(device, pos[0], pos[1])


def make_primary(device):
    """Make a display the primary one (origin 0,0)."""
    target = None
    for d in list_displays():
        if d["device"] == device:
            target = d
            break
    if target is None:
        return {"ok": False, "error": "no such display: %s" % device}

    dm = DEVMODEW()
    dm.dmSize = ctypes.sizeof(DEVMODEW)
    _user32.EnumDisplaySettingsW(device, ENUM_CURRENT_SETTINGS, ctypes.byref(dm))
    dm.dmPositionX = 0
    dm.dmPositionY = 0
    dm.dmFields = DM_POSITION
    rc = _user32.ChangeDisplaySettingsExW(
        device, ctypes.byref(dm), None,
        CDS_SET_PRIMARY | CDS_UPDATEREGISTRY, None)
    if rc != DISP_CHANGE_SUCCESSFUL:
        return {"ok": False, "error": "set primary failed (code %d)" % rc}
    return {"ok": True, "out": "%s 已设为主显示器" % device}


# ---------------- per-monitor scaling (read-only) ----------------

class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def get_scaling(device):
    """Effective DPI scale of a display, as a percentage (100, 125, 150...).

    Read-only on purpose. Windows keeps per-monitor scaling in an EDID-hashed
    registry key that a third-party app cannot derive reliably, and there is no
    supported Win32 call to change it - writing the wrong key would rescale the
    physical monitor. So the panel shows the value and hands changes off to
    Windows' own display settings.
    """
    target = None
    for d in list_displays():
        if d["device"] == device and d["attached"]:
            target = d
            break
    if target is None:
        return None
    try:
        shcore = ctypes.windll.shcore
        pt = _POINT(target["x"] + max(1, target["width"] // 2),
                    target["y"] + max(1, target["height"] // 2))
        MONITOR_DEFAULTTONEAREST = 2
        hmon = _user32.MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST)
        if not hmon:
            return None
        dx = wintypes.UINT()
        dy = wintypes.UINT()
        MDT_EFFECTIVE_DPI = 0
        if shcore.GetDpiForMonitor(hmon, MDT_EFFECTIVE_DPI,
                                   ctypes.byref(dx), ctypes.byref(dy)) != 0:
            return None
        return int(round(dx.value * 100.0 / 96.0))
    except Exception:                                          # noqa: BLE001
        return None


_last_device_installed = None


def status(light=False):
    """One call for the panel / CLI to render everything.

    light=True skips the pnputil subprocess, for UI polling loops where a
    ~200ms spawn every few seconds would show up as stutter. The driver
    presence flag is still reported, just taken from the cached last value.
    """
    global _last_device_installed
    if light and _last_device_installed is not None:
        # cached - the cheap path for the UI polling loop
        inst = _last_device_installed
    else:
        # cold cache: a light call must still answer correctly, otherwise the
        # panel would report "driver not installed" on its very first poll
        inst = device_installed()
        _last_device_installed = inst
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

    displays = list_displays()
    vd = None
    for d in displays:
        if d["virtual"] and d["attached"]:
            vd = d
            break

    phys = None
    for d in displays:
        if not d["virtual"] and d["attached"]:
            phys = d
            break

    return {
        "device_installed": inst,
        "device_id": find_device(),
        "config": cfg,
        "config_error": cfg_error,
        "config_path": CONFIG_PATH,
        "virtual": vd,
        "virtual_count": sum(1 for d in displays
                             if d["virtual"] and d["attached"]),
        "physical": phys,
        "displays": displays,
        "modes": available_modes(vd["device"]) if vd else [],
        "topology": current_topology(),
        "topology_labels": {k: v[1] for k, v in TOPOLOGIES.items()},
        "topology_valid": {k: topology_valid(k) for k in TOPOLOGIES},
        "scaling": {d["device"]: get_scaling(d["device"])
                    for d in displays if d["attached"]},
        "admin": is_admin(),
    }
