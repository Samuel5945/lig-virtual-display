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

# vdd_core is loaded from the project directory when this machine has one
# (single source of truth: editing it changes the CLI and the panel together),
# and falls back to the copy bundled inside this exe otherwise - that is what
# makes the exe usable when it is copied to another PC.
_here = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
for _cand in (ROOT, _here):
    if os.path.exists(os.path.join(_cand, "vdd_core.py")):
        if _cand not in sys.path:
            sys.path.insert(0, _cand)
        break

try:
    import vdd_core as core
    CORE_ERROR = ""
except Exception as exc:                                       # noqa: BLE001
    core = None
    CORE_ERROR = "%s: %s" % (type(exc).__name__, exc)

# True when this machine has the full project (scripts, docs); a shared exe on
# a fresh PC will not, and the panel hides the project-specific actions.
HAS_PROJECT = os.path.isdir(ROOT)


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


def create_default_config():
    """Write the driver's vdd_settings.xml when it is missing.

    Needs admin (the driver's config dir sits under the drive root), so the
    panel offers this from the banner and surfaces the permission error.
    """
    if core is None:
        return _err(CORE_ERROR)
    try:
        wrote = core.ensure_config()
        if wrote is None:
            return _ok("配置文件已存在，无需创建")
        return _ok("已创建 %s（需重载驱动生效）" % wrote)
    except PermissionError:
        return _err("写入需要管理员权限（驱动配置目录受系统保护）")
    except Exception as exc:                                   # noqa: BLE001
        return _err(str(exc))


def install_driver_bundled():
    """Install the MttVDD driver from the files carried in this exe.

    Idempotent (no-ops when the device is already installed) and needs admin,
    so the panel runs it through _need_admin.
    """
    if core is None:
        return _err(CORE_ERROR)
    r = core.install_driver_bundled()
    return {"ok": r.get("ok", False), "out": r.get("out", ""),
            "error": r.get("error", "")}


def sunshine_status():
    """Everything the streaming card needs. Read-only."""
    if core is None:
        return {"available": False}
    return {
        "installed": core.sunshine_installed(),
        "conf_path": core.sunshine_conf_path(),
        "settings": (core.read_conf_pairs(core.sunshine_conf_path())
                     if core.sunshine_conf_path() else {}),
        "virtual_device_id": core.sunshine_virtual_device_id(),
    }


def capture_target(settings, displays):
    """Which screen the phone will see. The rule lives in vdd_core so the CLI
    and streamcheck can state the same thing."""
    if core is None:
        return {}
    try:
        return core.capture_target(settings=settings, displays=displays)
    except Exception:                                          # noqa: BLE001
        return {}


def side_position(virtual, ref, side):
    """(x, y) the virtual screen would land on for that side - used by the
    schematic to draw the ghost before the click happens."""
    if core is None or virtual is None or ref is None:
        return None
    try:
        return core.side_position(virtual, ref, side)
    except Exception:                                          # noqa: BLE001
        return None


def describe_display(d):
    if core is None:
        return "无"
    try:
        return core.describe_display(d)
    except Exception:                                          # noqa: BLE001
        return "无"


def configure_sunshine():
    """Point Sunshine at the virtual display (needs admin to write)."""
    if core is None:
        return _err(CORE_ERROR)
    r = core.configure_sunshine_streaming()
    return {"ok": r.get("ok", False), "out": r.get("out", ""),
            "error": r.get("error", "")}


def restart_sunshine_service():
    if core is None:
        return _err(CORE_ERROR)
    if not is_admin():
        return _err("需要管理员权限")
    r = core.restart_sunshine()
    return {"ok": r.get("ok", False), "out": r.get("out", ""),
            "error": r.get("error", "")}


def configure_sunshine_follow():
    """Let Windows decide what Sunshine captures (needs admin to write)."""
    if core is None:
        return _err(CORE_ERROR)
    r = core.configure_sunshine_follow_display()
    return {"ok": r.get("ok", False), "out": r.get("out", ""),
            "error": r.get("error", "")}


def set_stream_target(kind):
    """Switch what the phone sees.

    'virtual' forces the VDD display and blanks the physical monitor for the
    duration of a stream; anything else hands the choice back to Windows.
    Either way Sunshine has to restart before it re-reads the config.
    """
    r = configure_sunshine() if kind == "virtual" else configure_sunshine_follow()
    if not r.get("ok"):
        return r
    rr = restart_sunshine_service()
    if not rr.get("ok"):
        r["out"] += "（配置已写入，请手动重启 Sunshine：托盘退出 -> 重开）"
    else:
        r["out"] += "，Sunshine 已重启"
    return r


def configure_sunshine_and_restart():
    """Kept for callers that only ever wanted the virtual-display target."""
    return set_stream_target("virtual")


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
    if not os.path.isdir(ROOT):
        return _err("本机没有 %s（这是共享出去的副本）" % ROOT)
    return open_path(ROOT)


def start_install():
    """Run the driver installer bat (it self-elevates)."""
    if not HAS_PROJECT:
        return _err("本机没有项目目录，无法运行安装脚本；"
                    "请先按 README 安装 MttVDD 驱动")
    bat = os.path.join(ROOT, "install-driver.bat")
    if not os.path.exists(bat):
        return _err("not found: %s" % bat)
    return open_path(bat)
