"""
Parsec VDD keep-alive daemon
============================
Creates virtual display(s) through the signed Parsec Virtual Display Driver
and pings the driver every ~70 ms so they stay plugged in.

Uses ONLY the signed Parsec driver - no third-party companion app required.
The device handle opens without administrator rights.

Protocol reference: nomi-san/parsec-vdd, core/parsec-vdd.h

Modes
-----
  run      (default) run in the foreground as the daemon
  start              spawn a detached hidden copy of 'run' and exit
  stop               ask the daemon to exit, then unplug everything
  clean              unplug all Parsec virtual displays (no daemon needed)
  status             report driver version, monitors and virtual display count

Options
-------
  --duration N       (run only) exit after N seconds - for testing
  --displays N       (run only) keep N virtual displays plugged (default 1)
  --resolution WxH@R (run only) force the virtual display mode, e.g. 2560x1440@60
"""

import ctypes
import json
import os
import subprocess
import sys
import time
import traceback
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "vdd-keepalive.log")
ERRLOG = os.path.join(HERE, "vdd-keepalive.err")
STOP_FLAG = os.path.join(HERE, "stop.flag")
PID_FILE = os.path.join(HERE, "pid.txt")
SETTINGS = os.path.join(HERE, "gui_settings.json")
REALONLY_FLAG = os.path.join(HERE, "realonly.flag")
MUTEX_NAME = "Global\\ParsecVDD_KeepAlive_WB"
PYTHONW = r"C:\Program Files\Python312\pythonw.exe"
PYTHON = r"C:\Program Files\Python312\python.exe"


def load_settings():
    """读取 GUI 写入的设置。返回 (resolution_or_None, follow_bool)。"""
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None, False
    follow = bool(data.get("follow_moonlight"))
    if follow:
        return None, True
    txt = (data.get("resolution") or "").strip()
    if not txt:
        return None, False
    try:
        wh, _, hz = txt.partition("@")
        w, _, h = wh.partition("x")
        return (int(w), int(h), int(hz) if hz else 60), False
    except ValueError:
        return None, False

IFACE_GUID = "{00b41627-04c4-429e-a26e-0265cf50c8fa}"
IOCTL_ADD = 0x0022E004
IOCTL_REMOVE = 0x0022A008
IOCTL_UPDATE = 0x0022A00C
IOCTL_VERSION = 0x0022E010

PING_INTERVAL = 0.07
REPORT_EVERY = 15.0
MIN_ADD_GAP = 8.0
MAX_INDEX = 16
MAX_LOG_BYTES = 1024 * 1024
# 自愈：added 且 ping 正常时 attached 掉到 0，说明显示器被外部切离桌面
# （Sunshine 的 dd_*、别的程序改拓扑）。连续 N 个报告周期才动手，防抖。
HEAL_AFTER_CYCLES = 2
HEAL_MAX_ATTEMPTS = 6          # 一轮故障最多试 N 次，之后放弃并日志说明
HEAL_BACKOFF = 30.0            # 重连失败后的退避基数（秒），逐次翻倍

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
u32 = ctypes.WinDLL("user32", use_last_error=True)

k32.CreateFileW.restype = wintypes.HANDLE
k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
k32.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                ctypes.c_void_p, wintypes.DWORD,
                                ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
k32.DeviceIoControl.restype = wintypes.BOOL
k32.CreateEventW.restype = wintypes.HANDLE
k32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
k32.GetOverlappedResult.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
                                    ctypes.POINTER(wintypes.DWORD), wintypes.BOOL]
k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
k32.CloseHandle.argtypes = [wintypes.HANDLE]
k32.CreateMutexW.restype = wintypes.HANDLE
k32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]

INVALID_HANDLE = wintypes.HANDLE(-1).value
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_RW = 0x00000001 | 0x00000002
OPEN_EXISTING = 3
OPEN_FLAGS = 0x00000080 | 0x40000000 | 0x80000000   # NORMAL | OVERLAPPED | WRITE_THROUGH
ERROR_IO_PENDING = 997


class OVERLAPPED(ctypes.Structure):
    _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p),
                ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD),
                ("hEvent", wintypes.HANDLE)]


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD),
                ("DeviceName", ctypes.c_wchar * 32),
                ("DeviceString", ctypes.c_wchar * 128),
                ("StateFlags", wintypes.DWORD),
                ("DeviceID", ctypes.c_wchar * 128),
                ("DeviceKey", ctypes.c_wchar * 128)]


class DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", ctypes.c_wchar * 32), ("dmSpecVersion", wintypes.WORD),
        ("dmDriverVersion", wintypes.WORD), ("dmSize", wintypes.WORD),
        ("dmDriverExtra", wintypes.WORD), ("dmFields", wintypes.DWORD),
        ("dmOrientation", ctypes.c_short), ("dmPaperSize", ctypes.c_short),
        ("dmPaperLength", ctypes.c_short), ("dmPaperWidth", ctypes.c_short),
        ("dmScale", ctypes.c_short), ("dmCopies", ctypes.c_short),
        ("dmDefaultSource", ctypes.c_short), ("dmPrintQuality", ctypes.c_short),
        ("dmColor", ctypes.c_short), ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short), ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short), ("dmFormName", ctypes.c_wchar * 32),
        ("dmLogPixels", wintypes.WORD), ("dmBitsPerPel", wintypes.DWORD),
        ("dmPelsWidth", wintypes.DWORD), ("dmPelsHeight", wintypes.DWORD),
        ("dmDisplayFlags", wintypes.DWORD), ("dmDisplayFrequency", wintypes.DWORD),
        ("dmICMMethod", wintypes.DWORD), ("dmICMIntent", wintypes.DWORD),
        ("dmMediaType", wintypes.DWORD), ("dmDitherType", wintypes.DWORD),
        ("dmReserved1", wintypes.DWORD), ("dmReserved2", wintypes.DWORD),
        ("dmPanningWidth", wintypes.DWORD), ("dmPanningHeight", wintypes.DWORD)]

DM_PELSWIDTH = 0x00080000
DM_PELSHEIGHT = 0x00100000
DM_DISPLAYFREQUENCY = 0x00400000
ENUM_CURRENT_SETTINGS = 0xFFFFFFFF


def virtual_device_name():
    """Device name (e.g. \\\\.\\DISPLAY22) of the running Parsec display, or None."""
    for a, s, m in adapters():
        if m and "Parsec" in (s or ""):
            return a
    return None


def current_mode(dev):
    dm = DEVMODEW()
    dm.dmSize = ctypes.sizeof(DEVMODEW)
    if u32.EnumDisplaySettingsW(dev, ENUM_CURRENT_SETTINGS, ctypes.byref(dm)):
        return dm.dmPelsWidth, dm.dmPelsHeight, dm.dmDisplayFrequency
    return None


def set_mode(dev, width, height, hz):
    dm = DEVMODEW()
    dm.dmSize = ctypes.sizeof(DEVMODEW)
    if not u32.EnumDisplaySettingsW(dev, ENUM_CURRENT_SETTINGS, ctypes.byref(dm)):
        return False, "EnumDisplaySettings failed (display not ready)"
    if (dm.dmPelsWidth, dm.dmPelsHeight, dm.dmDisplayFrequency) == (width, height, hz):
        return True, 0
    dm.dmPelsWidth = width
    dm.dmPelsHeight = height
    dm.dmDisplayFrequency = hz
    dm.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT | DM_DISPLAYFREQUENCY
    rc = u32.ChangeDisplaySettingsExW(dev, ctypes.byref(dm), None, 0, None)
    return rc == 0, rc


def log(msg):
    line = "[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > MAX_LOG_BYTES:
            os.replace(LOG, LOG + ".old")
    except OSError:
        pass
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    try:
        print(line, flush=True)
    except Exception:
        pass


def adapters():
    """Return [(adapter_name, adapter_string, monitor_name_or_None), ...]"""
    out = []
    i = 0
    while True:
        d = DISPLAY_DEVICEW()
        d.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        if not u32.EnumDisplayDevicesW(None, i, ctypes.byref(d), 0):
            break
        j = 0
        found = False
        while True:
            m = DISPLAY_DEVICEW()
            m.cb = ctypes.sizeof(DISPLAY_DEVICEW)
            if not u32.EnumDisplayDevicesW(d.DeviceName, j, ctypes.byref(m), 0):
                break
            out.append((d.DeviceName, d.DeviceString, m.DeviceName))
            found = True
            j += 1
        if not found:
            out.append((d.DeviceName, d.DeviceString, None))
        i += 1
    return out


def virtual_count():
    """⚠ 注意：只要有 ping 会话，Parsec 驱动会把全部 16 个插槽都报成"有监视器对象"（驱动怪癖）。
    所以这个数字**不能**用来判断"有没有显示器"或"是不是多了"，只适合调试打印。
    真正有意义的指标是 attached_parsec()。"""
    return sum(1 for _, s, m in adapters() if m and "Parsec" in (s or ""))


def parsec_adapter_entries():
    r"""适配器级的 Parsec 条目名列表。

    这个计数是可靠的：每 ADD 一个显示器就多一条 \\.\DISPLAYn。
    注意适配器级的 StateFlags 永远是 0x0（bit0 ATTACHED_TO_DESKTOP 不置位），
    所以这里只数条目，绝不看 flags。"""
    names = []
    i = 0
    while True:
        d = DISPLAY_DEVICEW()
        d.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        if not u32.EnumDisplayDevicesW(None, i, ctypes.byref(d), 0):
            break
        if "Parsec" in (d.DeviceString or ""):
            names.append(d.DeviceName)
        i += 1
        if i > 256:
            break
    return names


def _enum_attached(parsec):
    """两级枚举，返回挂到桌面的设备名列表。

    关键：EnumDisplayDevicesW(None, i) 枚举的是**适配器**，其 StateFlags 的
    bit0 不可靠（实测 Parsec 适配器条目恒为 0x0）。必须再用适配器名做第二遍
    枚举才是监视器级，bit0 在那一级才可信。旧版只在适配器级看 bit0，导致
    attached_parsec() 恒为 0，健康检查与「显示器过多」护栏同时失效，
    自愈无限触发、显示器无限累积（2026-10-14 实测定性）。"""
    out = []
    ai = 0
    while True:
        ad = DISPLAY_DEVICEW()
        ad.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        if not u32.EnumDisplayDevicesW(None, ai, ctypes.byref(ad), 0):
            break
        is_parsec = "Parsec" in (ad.DeviceString or "")
        if parsec and not is_parsec:
            ai += 1
            continue
        if (not parsec) and is_parsec:
            ai += 1
            continue
        mi = 0
        while True:
            mo = DISPLAY_DEVICEW()
            mo.cb = ctypes.sizeof(DISPLAY_DEVICEW)
            if not u32.EnumDisplayDevicesW(ad.DeviceName, mi, ctypes.byref(mo), 0):
                break
            if mo.StateFlags & 0x1:
                out.append(mo.DeviceName or ad.DeviceName)
            mi += 1
            if mi > 32:
                break
        ai += 1
        if ai > 64:
            break
    return out


def attached_parsec():
    """挂到桌面的 Parsec 显示器数量 —— 真正参与桌面的数量。"""
    return len(_enum_attached(parsec=True))


def real_attached_count():
    """挂到桌面上的真实（非 Parsec）显示器数量。"""
    return len(_enum_attached(parsec=False))


def reattach_desktop():
    """虚拟显示器还在驱动里（ping 会话活着）却被切离桌面时，把它接回桌面。

    **不能**用 IOCTL_ADD：那会再插一台，造成"重复添加 -> remove(0) 全清 ->
    掉到 0"的抖动（09-30 13:56 踩过）。用 DisplaySwitch，且必须两步走
    （10-01 09:48 实测）：
      1. /external —— 从未激活过的监视器对象只有这一招能点亮；
         直接 /extend 反而会把监视器对象整个弄没。
      2. 如果桌面上原本有真实显示器，再补一发 /extend 恢复扩展布局
         （虚拟屏激活过一次之后 /extend 才有效）。
    """
    had_real = real_attached_count() > 0
    exe = os.path.join(os.environ.get("WINDIR", r"C:\Windows"),
                       "System32", "DisplaySwitch.exe")
    log("self-heal: DisplaySwitch /external（had_real=%s）" % had_real)
    try:
        subprocess.run([exe, "/external"], capture_output=True, timeout=10)
    except Exception as exc:
        log("self-heal: DisplaySwitch failed: %r" % (exc,))
        return False
    time.sleep(2.5)
    if attached_parsec() > 0 and had_real:
        log("self-heal: virtual display 已激活 - 补 /extend 恢复扩展")
        try:
            subprocess.run([exe, "/extend"], capture_output=True, timeout=10)
        except Exception:
            pass
        time.sleep(2.5)
    return attached_parsec() > 0


def find_device_path():
    candidates = []
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            "SYSTEM\\CurrentControlSet\\Control\\DeviceClasses\\" + IFACE_GUID)
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(key, i)
                i += 1
            except OSError:
                break
            if sub.startswith("##?#"):
                sub = sub[4:]
            candidates.append("\\\\?\\" + sub)
    except OSError:
        pass
    candidates.append("\\\\?\\ROOT#DISPLAY#0000#" + IFACE_GUID)
    candidates.append("\\\\?\\ROOT#DISPLAY#0000#" + IFACE_GUID.lower())
    for path in candidates:
        h = k32.CreateFileW(path, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_RW,
                            None, OPEN_EXISTING, OPEN_FLAGS, None)
        if h != INVALID_HANDLE:
            return path, h
    return None, None


def ioctl(h, code, data=None, timeout_ms=5000):
    inbuf = ctypes.create_string_buffer(32)
    if data:
        ctypes.memmove(inbuf, data, min(len(data), 32))
    out = wintypes.DWORD(0)
    ov = OVERLAPPED()
    ov.hEvent = k32.CreateEventW(None, True, False, None)
    if not ov.hEvent:
        return None, ctypes.get_last_error()
    try:
        ok = k32.DeviceIoControl(h, code, inbuf, 32, ctypes.byref(out), 4, None,
                                 ctypes.byref(ov))
        if not ok:
            err = ctypes.get_last_error()
            if err != ERROR_IO_PENDING:
                return None, err
            if k32.WaitForSingleObject(ov.hEvent, timeout_ms) != 0:
                return None, -2
            n = wintypes.DWORD(0)
            if not k32.GetOverlappedResult(h, ctypes.byref(ov), ctypes.byref(n), False):
                return None, ctypes.get_last_error()
        return out.value, 0
    finally:
        k32.CloseHandle(ov.hEvent)


def remove_index(h, index):
    # driver expects the index as a 16-bit big-endian value
    data = bytes([((index >> 8) & 0xFF), (index & 0xFF)])
    ioctl(h, IOCTL_REMOVE, data)
    ioctl(h, IOCTL_UPDATE)


def remove_all(h):
    """一次清空。实测 REMOVE(index 0) 能清掉全部，不必逐个索引试。
    返回值用适配器条目数判定，不用 attached_parsec()（无桌面挂载时也是 0，
    分不清"清干净了"和"本来就没挂"）。"""
    remove_index(h, 0)
    time.sleep(1.0)
    return 0 if not parsec_adapter_entries() else -1


def apply_resolution(resolution, logf=None):
    """Wait for the virtual display to appear, then force the wanted mode."""
    w, h, hz = resolution
    for _ in range(12):
        dev = virtual_device_name()
        if dev:
            ok, rc = set_mode(dev, w, h, hz)
            if logf:
                logf("display mode %dx%d@%d on %s -> %s"
                     % (w, h, hz, dev, "ok" if ok else "failed rc=%s" % rc))
            return ok
        time.sleep(0.5)
    if logf:
        logf("virtual display not found - cannot set its mode")
    return False


def do_status():
    path, h = find_device_path()
    print("device path :", path)
    if not h:
        print("driver      : NOT REACHABLE")
        return 1
    ver, err = ioctl(h, IOCTL_VERSION)
    print("driver ver  :", ver, "(err %s)" % err)
    k32.CloseHandle(h)
    rows = adapters()
    print("monitors    : %d" % sum(1 for _, _, m in rows if m))
    for a, s, m in rows:
        if m or "Parsec" in (s or ""):
            print("   %-14s -> %-28s | %s" % (a, m or "(no monitor)", s))
    print("virtual     : %d" % virtual_count())
    running = os.path.exists(PID_FILE)
    print("daemon      :", "RUNNING (pid %s)" % open(PID_FILE).read().strip()
          if running else "not running")
    return 0


def do_clean():
    path, h = find_device_path()
    if not h:
        print("cannot open the driver")
        return 1
    # 用适配器条目数，不能用 virtual_count()：后者在无 ping 会话时恒为 0，
    # 会把清理动作整个 gate 掉（2026-10-14 实测定性，clean 一直是空转）。
    before = parsec_adapter_entries()
    print("parsec display entries before:", len(before))
    # 不要再先 ADD 一个"给驱动一个活句柄"——那对清孤儿适得其反。
    # REMOVE(index 0) 按驱动语义清空全部插槽，多试几轮配 UPDATE。
    for attempt in range(3):
        remove_index(h, 0)
        time.sleep(1.0)
        if not parsec_adapter_entries():
            break
    k32.CloseHandle(h)
    time.sleep(1.0)
    after = parsec_adapter_entries()
    print("parsec display entries after :", len(after))
    if after:
        print("remaining:", ", ".join(after))
    return 0 if len(after) < len(before) else 1


def do_stop():
    open(STOP_FLAG, "w").close()
    print("stop flag written - waiting for the daemon to exit ...")
    for _ in range(30):
        time.sleep(0.5)
        if not os.path.exists(PID_FILE):
            print("daemon stopped")
            break
    else:
        try:
            pid = open(PID_FILE).read().strip()
            subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True)
            print("daemon killed")
        except Exception as exc:
            print("taskkill failed:", exc)
    # 顺便结束 guardian，否则它会一直空转（虽然它会尊重 stop.flag 不重启）
    gpid_file = os.path.join(HERE, "guardian_pid.txt")
    try:
        gpid = open(gpid_file).read().strip()
        subprocess.run(["taskkill", "/PID", gpid, "/F"], capture_output=True)
        os.remove(gpid_file)
        print("guardian stopped (pid %s)" % gpid)
    except Exception:
        pass
    return do_clean()


def do_start(extra=None):
    if os.path.exists(STOP_FLAG):
        os.remove(STOP_FLAG)
    exe = PYTHONW if os.path.exists(PYTHONW) else PYTHON
    flags = 0x00000008 | 0x00000200          # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    cmd = [exe, os.path.abspath(__file__), "run"] + list(extra or [])
    subprocess.Popen(cmd, creationflags=flags, close_fds=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     cwd=HERE)
    print("keep-alive daemon launched with", exe)
    if extra:
        print("   extra args:", " ".join(extra))
    return 0


def do_run(displays=1, duration=0, resolution=None):
    # 让任何未捕获异常都落到文件里（否则 pythonw + DEVNULL 会让异常彻底消失）
    try:
        _err = open(ERRLOG, "a", buffering=1, encoding="utf-8")
        sys.stderr = _err
    except OSError:
        pass
    sys.excepthook = lambda et, ev, tb: (
        sys.stderr.write("%s\n%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"),
                                       "".join(traceback.format_exception(et, ev, tb)))) if sys.stderr else None)

    mutex = k32.CreateMutexW(None, False, MUTEX_NAME)
    if ctypes.get_last_error() == 183:
        log("another instance is already running - exiting")
        return 0
    if os.path.exists(STOP_FLAG):
        os.remove(STOP_FLAG)
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass

    log("=== Parsec VDD keep-alive starting (pid %d, target %d display(s)) ==="
        % (os.getpid(), displays))
    log("self-heal enabled: attached 掉到 0 且 ping 正常时，会在 %d 个报告周期后用 "
        "DisplaySwitch 重新接回桌面（realonly.flag 存在则不抢回）" % HEAL_AFTER_CYCLES)

    h = None
    last_report = 0.0
    last_add = 0.0
    added = False            # 本句柄会话是否已经 ADD 过
    started = time.time()
    errors = 0
    zero_streak = 0          # added 后 attached==0 的连续报告周期数
    heal_attempts = 0        # 本轮故障已尝试重连的次数
    next_heal_at = 0.0       # 下次允许重连的时间（退避用）
    gave_up = False
    suppress_logged = False

    try:
        while True:
            if os.path.exists(STOP_FLAG):
                log("stop flag detected - shutting down")
                break
            if duration and time.time() - started >= duration:
                log("duration reached - shutting down")
                break

            if h is None:
                path, h = find_device_path()
                if not h:
                    log("cannot open the Parsec VDD device - retrying in 5 s")
                    h = None
                    time.sleep(5)
                    continue
                ver, err = ioctl(h, IOCTL_VERSION)
                log("device opened: %s  driver version=%s (err %s)" % (path, ver, err))
                last_report = 0.0

            now = time.time()
            if now - last_report >= REPORT_EVERY:
                last_report = now
                att = attached_parsec()
                log("alive - attached virtual displays: %d, added=%s (driver slots reported: %d)"
                    % (att, added, virtual_count()))

                # 只有"挂到桌面"的数量异常多才需要重置。
                # 驱动怪癖会让 slot 计数虚高到 16，那个数字不能当依据（09-13 踩过）
                if att > displays:
                    log("too many ATTACHED virtual displays (%d > %d) - resetting with remove(0)"
                        % (att, displays))
                    remove_index(h, 0)
                    time.sleep(1.5)
                    added = False
                    last_add = 0.0
                    continue

                if att > 0:
                    # 恢复健康：清空自愈计数
                    zero_streak = 0
                    heal_attempts = 0
                    next_heal_at = 0.0
                    gave_up = False
                    suppress_logged = False
                elif added:
                    # added 且 ping 正常但 attached==0：显示器被外部切离桌面。
                    # 老逻辑对这种情况无动于衷（added 是单向闩锁），会永远空转。
                    zero_streak += 1
                    if os.path.exists(REALONLY_FLAG):
                        if not suppress_logged:
                            log("attached=0 但 realonly.flag 存在"
                                "（用户主动选了仅真实显示器）- 不抢回")
                            suppress_logged = True
                    elif zero_streak >= HEAL_AFTER_CYCLES:
                        if heal_attempts >= HEAL_MAX_ATTEMPTS:
                            if not gave_up:
                                log("self-heal: 尝试 %d 次仍是 0 - 放弃，等显示器自己回来或重启保活"
                                    % heal_attempts)
                                gave_up = True
                        elif now >= next_heal_at:
                            heal_attempts += 1
                            if virtual_count() == 0:
                                # 驱动里已经没有监视器对象了（ping 还活着）：
                                # DisplaySwitch 接回不了不存在的东西，清闩锁走
                                # 正常 ADD 重插；ADD 后还没挂上的话，下一次
                                # 尝试会轮到 DisplaySwitch（面板手动恢复也是
                                # "ADD + 切换"两步走的）
                                log("self-heal: 驱动里没有监视器对象了 - 清闩锁重新 ADD"
                                    "（第 %d/%d 次）" % (heal_attempts, HEAL_MAX_ATTEMPTS))
                                added = False
                                last_add = 0.0
                            else:
                                log("self-heal: attached=0 已连续 %d 个周期且 ping 正常"
                                    " - 显示器疑似被外部切离，重新接回桌面（第 %d/%d 次）"
                                    % (zero_streak, heal_attempts, HEAL_MAX_ATTEMPTS))
                                reattach_desktop()
                            next_heal_at = time.time() + HEAL_BACKOFF * (2 ** (heal_attempts - 1))

                # 显示器与 ping 会话同生共死：句柄打开后 ADD 一次即可，
                # 之后全靠 ping 维持。只有句柄重开过才需要再 ADD。
                #
                # 硬护栏：适配器级条目数已经够了就绝不再 ADD。
                # 这条不依赖 StateFlags（那个在适配器级恒为 0x0，不可信），
                # 是独立的第二道保险 —— 即使健康检查再坏掉，也不会无限累积。
                if not added and now - last_add >= MIN_ADD_GAP:
                    existing = len(parsec_adapter_entries())
                    if existing >= max(displays, 1):
                        log("ADD skipped: %d parsec display(s) already exist "
                            "(target %d) - forcing reattach instead"
                            % (existing, displays))
                        added = True
                        reattach_desktop()
                    else:
                        idx, err = ioctl(h, IOCTL_ADD)
                        ioctl(h, IOCTL_UPDATE)
                        last_add = now
                        if err == 0:
                            added = True
                            log("virtual display added, driver index=%s" % idx)
                            time.sleep(1.5)
                            if resolution:
                                apply_resolution(resolution, log)
                        else:
                            log("IOCTL_ADD failed err=%s - reopening in 3 s" % err)
                            k32.CloseHandle(h)
                            h = None
                            added = False
                            time.sleep(3)
                            continue
                elif added and resolution and att >= 1:
                    dev = virtual_device_name()
                    if dev and current_mode(dev) != tuple(resolution):
                        log("mode is %s - re-applying %s" % (current_mode(dev), resolution))
                        apply_resolution(resolution, log)

            _, err = ioctl(h, IOCTL_UPDATE)
            if err != 0:
                errors += 1
                if errors >= 5:
                    log("ping failing (err=%s) - reopening the device" % err)
                    k32.CloseHandle(h)
                    h = None
                    added = False
                    errors = 0
                    time.sleep(1)
                    continue
            else:
                errors = 0

            time.sleep(PING_INTERVAL)
    except KeyboardInterrupt:
        log("interrupted")
    except Exception:
        log("FATAL exception in the main loop:\n%s" % traceback.format_exc())
    finally:
        if h:
            n = remove_all(h)
            log("unplugged %d virtual display(s)" % n)
            k32.CloseHandle(h)
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
        log("=== keep-alive stopped ===")
    return 0


def main():
    argv = sys.argv[1:]
    mode = "run"
    if argv and not argv[0].startswith("-"):
        mode = argv.pop(0).lower()
    displays = 1
    duration = 0
    resolution = None
    fwd = []
    rest = list(argv)
    while rest:
        a = rest.pop(0)
        if a == "--duration" and rest:
            duration = int(rest.pop(0))
            fwd += ["--duration", str(duration)]
        elif a == "--displays" and rest:
            displays = int(rest.pop(0))
            fwd += ["--displays", str(displays)]
        elif a == "--resolution" and rest:
            txt = rest.pop(0)
            try:
                wh, _, hz = txt.partition("@")
                w, _, h = wh.partition("x")
                resolution = (int(w), int(h), int(hz) if hz else 60)
            except ValueError:
                print("bad --resolution value:", txt)
                return 2
            fwd += ["--resolution", txt]

    if mode in ("status", "-s"):
        return do_status()
    if mode in ("stop", "off"):
        return do_stop()
    if mode in ("clean",):
        return do_clean()
    if mode == "start":
        return do_start(fwd)
    if mode in ("run", "add"):
        # 没在命令行指定分辨率时，读 GUI 写的设置
        if resolution is None:
            resolution, follow = load_settings()
            if follow:
                log("settings: follow Moonlight is ON - the daemon will NOT force a resolution")
            elif resolution:
                log("settings: forcing %dx%d@%d from gui_settings.json" % resolution)
        return do_run(displays=displays, duration=duration, resolution=resolution)
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
