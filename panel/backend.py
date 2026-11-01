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
import time

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


def display_modes(device):
    """Every mode one screen reports, physical or virtual."""
    if core is None:
        return []
    try:
        return core.available_modes(str(device))
    except Exception:                                          # noqa: BLE001
        return []


def set_display_mode(device, width, height, hz):
    """Set the resolution of the screen selected in the layout card."""
    if core is None:
        return _err(CORE_ERROR)
    try:
        r = core.set_display_mode(str(device), int(width), int(height), int(hz))
        return {"ok": r.get("ok", False), "out": r.get("out", ""),
                "error": r.get("error", "")}
    except Exception as exc:                                   # noqa: BLE001
        return _err(str(exc))


def set_display_scaling(device, percent):
    """Set the scaling of the screen selected in the layout card."""
    if core is None:
        return _err(CORE_ERROR)
    try:
        r = core.set_scaling(str(device), int(percent))
        return {"ok": r.get("ok", False), "out": r.get("out", ""),
                "error": r.get("error", "")}
    except Exception as exc:                                   # noqa: BLE001
        return _err(str(exc))


def scale_options():
    """Windows' scaling ladder, for the layout card's dropdown."""
    if core is None:
        return [100, 125, 150, 175, 200, 225, 250, 300]
    return list(getattr(core, "SCALE_PCTS",
                        (100, 125, 150, 175, 200, 225, 250, 300)))


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


def move_display(device, x, y):
    """Put any non-primary display at an exact spot (dragged in the schematic).

    core.set_position refuses the pinned primary; physical second screens and
    virtual screens both go through the same call.
    """
    if core is None:
        return _err(CORE_ERROR)
    try:
        r = core.set_position(str(device), int(round(x)), int(round(y)))
        return {"ok": r.get("ok", False), "out": r.get("out", ""),
                "error": r.get("error", "")}
    except Exception as exc:                                   # noqa: BLE001
        return _err(str(exc))


def make_primary(which):
    """which: 'physical' (the first physical screen, i.e. the numbered one the
    panel names) or 'virtual' (the first virtual screen)."""
    if core is None:
        return _err(CORE_ERROR)
    target = None
    for d in core.list_displays():
        if not d["attached"]:
            continue
        if which == "virtual" and d["virtual"]:
            target = d
            break
        if which == "physical" and not d["virtual"]:
            target = d
            break
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
        "display_ids": core.sunshine_display_ids(),
        "targets": core.sunshine_targets(),
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


def set_stream_target(target, keep_others=True):
    """Choose which screen the phone sees, and what the others do.

    ``target``: 'system', a Sunshine device_id from sunshine_targets(), the
    legacy 'physical'/'virtual' aliases, or 'gdi:\\\\.\\DISPLAYn' for a screen
    Sunshine has not enumerated yet. ``keep_others``: True leaves the rest of
    the desktop alone; False makes Sunshine keep only the pinned screen active
    for the duration of the session (and revert when the last client leaves).
    'system' ignores it - handing the choice back to Windows means not
    managing the topology at all.

    Sunshine only reads the config and enumerates screens on start, so every
    path restarts it. A 'gdi:' target costs one extra restart: the first one
    lets Sunshine see the newly plugged screen, the second applies output_name.
    """
    if core is None:
        return _err(CORE_ERROR)
    try:
        if target == "system":
            dev = None
        elif target in ("physical", "virtual"):
            dev = core.sunshine_display_ids().get(target)
            if not dev:
                return _err("Sunshine 日志里还没有%s的 device_id —— 先重启一次 Sunshine"
                            % ("物理屏" if target == "physical" else "虚拟屏"))
        elif str(target).startswith("gdi:"):
            gdi = str(target)[4:]
            rr = restart_sunshine_service()
            if not rr.get("ok"):
                return _err("要让 Sunshine 认出这块屏，重启失败：%s"
                            % (rr.get("error") or "未知原因"))
            # the service returns before its device list reaches the log; give
            # it a few seconds rather than failing on a race we just created
            hit = None
            for _ in range(20):
                hit = next((t for t in core.sunshine_targets()
                            if t["gdi"] == gdi and t.get("key")), None)
                if hit:
                    break
                time.sleep(0.4)
            if hit is None:
                return _err("Sunshine 重启后仍没认出 %s（屏幕可能在休眠，"
                            "或已被拔掉）" % gdi)
            dev = hit["key"]
        else:
            valid = {t["key"] for t in core.sunshine_targets() if t.get("key")}
            if target not in valid:
                return _err("Sunshine 没有枚举到这块屏：%s" % target)
            dev = target
        dd = (core.STREAM_KEEP_OTHERS
              if target == "system" or keep_others
              else core.STREAM_BLANK_OTHERS)
    except Exception as exc:                                       # noqa: BLE001
        return _err(str(exc))
    r = core.set_stream_output(dev, dd)
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
