"""
VirtualDisplay panel - backend bridge.

Deliberately thin: it does NOT reimplement anything. It imports vdd_core
straight out of C:\\VirtualDisplay\\vdd_core.py, so the panel, the CLI and
any script share exactly one implementation.

The panel binary therefore carries no logic of its own - updating
vdd_core.py changes the panel's behaviour without a rebuild.
"""

import os
import sys

ROOT = r"C:\VirtualDisplay"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    import vdd_core as core
    CORE_ERROR = ""
except Exception as exc:                                       # noqa: BLE001
    core = None
    CORE_ERROR = "%s: %s" % (type(exc).__name__, exc)


def core_available():
    return core is not None


# --------------------------------------------------------------------------- #
# read-only queries
# --------------------------------------------------------------------------- #

def status(light=False):
    """Everything the UI needs. Never raises.

    light=True is for the UI's polling timer: it skips the pnputil subprocess
    (162ms -> 22ms), which would otherwise stutter every poll.
    """
    if core is None:
        return {"available": False, "error": CORE_ERROR}
    try:
        s = core.status(light=light)
        s["available"] = True
        return s
    except Exception as exc:                                   # noqa: BLE001
        return {"available": False, "error": str(exc)}


def modes():
    if core is None:
        return []
    try:
        vds = core.virtual_displays()
        return core.available_modes(vds[0]["device"]) if vds else []
    except Exception:                                          # noqa: BLE001
        return []


# --------------------------------------------------------------------------- #
# actions - all return {"ok": bool, "out": str, "error": str}
# --------------------------------------------------------------------------- #

def _ok(out=""):
    return {"ok": True, "out": out, "error": ""}


def _err(msg):
    return {"ok": False, "out": "", "error": msg}


def set_mode(width, height, hz):
    """Change the active mode of the virtual display."""
    if core is None:
        return _err(CORE_ERROR)
    vds = core.virtual_displays()
    if not vds:
        return _err("没有检测到虚拟显示器（驱动是否已安装？）")
    r = core.set_mode(vds[0]["device"], int(width), int(height), int(hz))
    return {"ok": r.get("ok", False), "out": r.get("out", ""),
            "error": r.get("error", "")}


def set_count(n):
    """Change how many virtual displays the driver creates."""
    if core is None:
        return _err(CORE_ERROR)
    try:
        cfg = core.read_config()
        cfg["count"] = max(1, min(8, int(n)))
        core.write_config(cfg)
        return _ok("count = %d（需重载驱动生效）" % cfg["count"])
    except Exception as exc:                                   # noqa: BLE001
        return _err(str(exc))


def add_resolution(width, height, hz):
    if core is None:
        return _err(CORE_ERROR)
    try:
        cfg = core.read_config()
        m = (int(width), int(height), int(hz))
        if m in cfg["resolutions"]:
            return _ok("%dx%d@%d 已在列表中" % m)
        cfg["resolutions"].append(m)
        core.write_config(cfg)
        return _ok("已添加 %dx%d@%d（需重载驱动生效）" % m)
    except Exception as exc:                                   # noqa: BLE001
        return _err(str(exc))


def remove_resolution(width, height, hz):
    if core is None:
        return _err(CORE_ERROR)
    try:
        cfg = core.read_config()
        m = (int(width), int(height), int(hz))
        if m not in cfg["resolutions"]:
            return _err("%dx%d@%d 不在列表中" % m)
        if len(cfg["resolutions"]) <= 1:
            return _err("这是最后一个分辨率，不能删")

        # Refuse to remove the mode the virtual display is using right now.
        # Reloading with it gone would silently drop the display onto some
        # other mode, which looks like the panel "lost" the setting.
        vds = core.virtual_displays()
        if vds:
            vd = vds[0]
            if (vd["width"], vd["height"], vd["hz"]) == m:
                return _err(
                    "%dx%d@%d 正是虚拟屏当前使用的分辨率。"
                    "请先在上面「虚拟屏分辨率」里切到别的，再回来移除。" % m)

        cfg["resolutions"].remove(m)
        core.write_config(cfg)
        return _ok("已移除 %dx%d@%d（需重载驱动生效）" % m)
    except Exception as exc:                                   # noqa: BLE001
        return _err(str(exc))


def reload_driver():
    """Apply config changes. Needs admin - caller should elevate first."""
    if core is None:
        return _err(CORE_ERROR)
    if not core.is_admin():
        return _err("需要管理员权限")
    r = core.reload_driver()
    return {"ok": r.get("ok", False), "out": r.get("out", ""),
            "error": r.get("error", "")}


# --------------------------------------------------------------------------- #
# multi-monitor layout
# --------------------------------------------------------------------------- #

def set_topology(name):
    """Switch display topology: extend / virtual / physical / clone.

    "virtual" turns the physical monitor off - the caller must warn first.
    """
    if core is None:
        return _err(CORE_ERROR)
    r = core.set_topology(name)
    return {"ok": r.get("ok", False), "out": r.get("out", ""),
            "error": r.get("error", "")}


def place_beside(side):
    """Move the virtual display next to the physical one."""
    if core is None:
        return _err(CORE_ERROR)
    vds = core.virtual_displays()
    if not vds:
        return _err("没有检测到虚拟显示器")
    r = core.place_beside(vds[0]["device"], side)
    return {"ok": r.get("ok", False), "out": r.get("out", ""),
            "error": r.get("error", "")}


def make_primary(which):
    """which: 'physical' or 'virtual'."""
    if core is None:
        return _err(CORE_ERROR)
    target = None
    for d in core.list_displays():
        if not d["attached"]:
            continue
        if which == "virtual" and d["virtual"]:
            target = d
        elif which == "physical" and not d["virtual"]:
            target = d
    if target is None:
        return _err("找不到%s显示器" % ("虚拟" if which == "virtual" else "物理"))
    r = core.make_primary(target["device"])
    return {"ok": r.get("ok", False), "out": r.get("out", ""),
            "error": r.get("error", "")}


def open_windows_display_settings():
    """Per-monitor scaling has no supported Win32 setter, so hand it off."""
    try:
        os.startfile("ms-settings:display")
        return _ok("已打开 Windows 显示设置")
    except Exception as exc:                                   # noqa: BLE001
        return _err(str(exc))


# --------------------------------------------------------------------------- #
# misc
# --------------------------------------------------------------------------- #

def is_admin():
    try:
        return bool(core and core.is_admin())
    except Exception:                                          # noqa: BLE001
        return False


def elevate_and_rerun():
    """Re-launch the panel elevated. Returns False if UAC was declined."""
    import ctypes
    # lpParameters must NOT include the executable itself, only arguments
    args = " ".join('"%s"' % a for a in sys.argv[1:])
    rc = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, args, None, 1)
    return int(rc) > 32


def open_path(path):
    try:
        os.startfile(path)
        return _ok(path)
    except Exception as exc:                                   # noqa: BLE001
        return _err(str(exc))


def open_config_dir():
    return open_path(os.path.dirname(core.CONFIG_PATH) if core
                     else r"C:\VirtualDisplayDriver")


def open_project_dir():
    return open_path(ROOT)


def start_install():
    """Run the driver installer bat (it self-elevates)."""
    bat = os.path.join(ROOT, "install-driver.bat")
    if not os.path.exists(bat):
        return _err("not found: %s" % bat)
    return open_path(bat)
