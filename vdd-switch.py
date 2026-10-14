"""
Display switcher for the Parsec virtual display setup
=====================================================
One-click switching between "real monitor only" and "virtual display only"
using the built-in DisplaySwitch.exe.

Modes
-----
  toggle   (default)  flip between real-only and virtual-only
  real                activate only the real monitor
  virtual             activate only the virtual display
  both                extend (both active)
  status              show which displays are currently active

Flags used (swap them here if the toggle ever goes the wrong way):
  /internal = PC screen only  -> the first display (the real monitor)
  /external = Second screen only -> the second display (the virtual one)
"""

import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
REALONLY_FLAG = os.path.join(HERE, "realonly.flag")

DWORD = wintypes.DWORD
u32 = ctypes.WinDLL("user32", use_last_error=True)

DISPLAYSWITCH = os.path.join(os.environ.get("WINDIR", r"C:\Windows"),
                             "System32", "DisplaySwitch.exe")
FLAG_REAL = "/internal"
FLAG_VIRTUAL = "/external"
FLAG_BOTH = "/extend"

STATE_ATTACHED = 0x1
STATE_PRIMARY = 0x2


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [("cb", DWORD), ("DeviceName", ctypes.c_wchar * 32),
                ("DeviceString", ctypes.c_wchar * 128), ("StateFlags", DWORD),
                ("DeviceID", ctypes.c_wchar * 128), ("DeviceKey", ctypes.c_wchar * 128)]


def scan():
    """Return (active_real, active_virtual, real_exists) - names included."""
    real = None
    virt = None
    real_exists = False
    i = 0
    while True:
        d = DISPLAY_DEVICEW()
        d.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        if not u32.EnumDisplayDevicesW(None, i, ctypes.byref(d), 0):
            break
        name = d.DeviceName
        desc = d.DeviceString or ""
        is_parsec = "Parsec" in desc
        attached = bool(d.StateFlags & STATE_ATTACHED)
        # does this adapter have a real monitor object attached right now?
        has_mon = False
        j = 0
        while True:
            m = DISPLAY_DEVICEW()
            m.cb = ctypes.sizeof(DISPLAY_DEVICEW)
            if not u32.EnumDisplayDevicesW(name, j, ctypes.byref(m), 0):
                break
            has_mon = True
            j += 1
        if is_parsec:
            if attached:
                virt = name
        else:
            if attached:
                real = name
            if has_mon:
                real_exists = True
        i += 1
    return real, virt, real_exists


def run_flag(flag):
    if not os.path.exists(DISPLAYSWITCH):
        print("DisplaySwitch.exe not found at", DISPLAYSWITCH)
        return False
    subprocess.run([DISPLAYSWITCH, flag], capture_output=True)
    time.sleep(2.0)
    return True


def mark_realonly(on):
    """告诉保活进程用户是否主动选了"仅真实显示器"（是的话自愈不抢回）。"""
    try:
        if on:
            open(REALONLY_FLAG, "w").close()
        elif os.path.exists(REALONLY_FLAG):
            os.remove(REALONLY_FLAG)
    except OSError:
        pass


def banner(real, virt, real_exists):
    print("  真实显示器 : %s" % (real if real else
                                ("未激活（%s）" % ("已连接" if real_exists else "未连接/已断电"))))
    print("  虚拟显示器 : %s" % (virt if virt else "未激活"))


def do_status():
    real, virt, real_exists = scan()
    print("=== 当前显示器状态 ===")
    banner(real, virt, real_exists)
    return 0


def switch(target):
    real, virt, real_exists = scan()
    print("=== 切换前 ===")
    banner(real, virt, real_exists)
    print()

    if target == "toggle":
        target = "virtual" if real else "real"
        print("   -> 目标：%s" % ("虚拟显示器" if target == "virtual" else "真实显示器"))

    if target == "real":
        if not real_exists:
            print("!! 提示：检测不到真实显示器（可能已断电）。")
            print("   如果切过去是黑的，按 Win+P 再选一次就能切回来。")
        mark_realonly(True)
        ok = run_flag(FLAG_REAL)
    elif target == "virtual":
        mark_realonly(False)
        if not virt:
            # virtual display not present -> ask the daemon to plug it in
            print("!! 虚拟显示器当前不存在，尝试启动保活进程 ...")
            try:
                exe = r"C:\Program Files\Python312\python.exe"
                sc = os.path.join(HERE, "vdd-keepalive.py")
                # 不带 --resolution：分辨率以 gui_settings.json 为准
                subprocess.run([exe, sc, "start"],
                               capture_output=True)
                time.sleep(6)
            except Exception as exc:
                print("   启动失败:", exc)
            real, virt, real_exists = scan()
            if not virt:
                print("!! 虚拟显示器仍然不存在，请先双击 Start-VirtualDisplay.bat")
                return 1
        ok = run_flag(FLAG_VIRTUAL)
    elif target == "both":
        mark_realonly(False)
        ok = run_flag(FLAG_BOTH)
    else:
        print("unknown target:", target)
        return 2

    if not ok:
        return 1

    real, virt, real_exists = scan()
    print()
    print("=== 切换后 ===")
    banner(real, virt, real_exists)
    print()
    if target == "real" and real and not virt:
        print("OK - 桌面现在只在真实显示器上")
    elif target == "virtual" and virt and not real:
        print("OK - 桌面现在只在虚拟显示器上（物理屏可以关掉）")
    else:
        print("提示：如果结果不对，可能是 /internal 与 /external 的对应反了，")
        print("      在 vdd-switch.py 顶部把 FLAG_REAL 与 FLAG_VIRTUAL 互换即可。")
    return 0


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith("-")]
    mode = argv[0].lower() if argv else "toggle"
    if mode in ("status", "s"):
        return do_status()
    if mode in ("toggle", "real", "virtual", "both"):
        return switch(mode)
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
