# -*- coding: utf-8 -*-
"""
ParsecVDD 虚拟显示器控制面板
============================
一个可视化小工具，用来管理 Parsec 虚拟显示器：
  * 查看驱动 / 虚拟显示器 / 保活进程 状态
  * 调整虚拟显示器的分辨率与刷新率
  * 「跟随 Moonlight」模式：串流时由 Sunshine 按客户端请求自动设置分辨率
  * 一键在 真实显示器 / 虚拟显示器 / 扩展 之间切换
  * 检查并一键写入 Sunshine 的推荐显示配置（需要管理员）

直接用 pythonw 运行即可；也可用 PyInstaller 打包成 exe。
"""

import ctypes
import json
import os
import subprocess
import sys
import time
import tkinter as tk
from ctypes import wintypes
from tkinter import ttk

# ---------------------------------------------------------------- 路径常量
BASE = r"C:\VirtualDisplay"
SETTINGS = os.path.join(BASE, "gui_settings.json")
REALONLY_FLAG = os.path.join(BASE, "realonly.flag")
DAEMON = os.path.join(BASE, "vdd-keepalive.py")
GUARDIAN = os.path.join(BASE, "vdd-guardian.py")
SWITCH = os.path.join(BASE, "vdd-switch.py")
PID_FILE = os.path.join(BASE, "pid.txt")
GPID_FILE = os.path.join(BASE, "guardian_pid.txt")
PYTHON = r"C:\Program Files\Python312\python.exe"
PYTHONW = r"C:\Program Files\Python312\pythonw.exe"
SUNSHINE_CONF = r"C:\Program Files\Sunshine\config\sunshine.conf"

APP_TITLE = "ParsecVDD 虚拟显示器控制面板"

# ---------------------------------------------------------------- VDD 协议
IFACE_GUID = "{00b41627-04c4-429e-a26e-0265cf50c8fa}"
IOCTL_ADD = 0x0022E004
IOCTL_REMOVE = 0x0022A008
IOCTL_UPDATE = 0x0022A00C
IOCTL_VERSION = 0x0022E010
MAX_INDEX = 16

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_RW = 0x00000003
OPEN_EXISTING = 3
OPEN_FLAGS = 0x00000080 | 0x40000000 | 0x80000000
ERROR_IO_PENDING = 997
INVALID_HANDLE = wintypes.HANDLE(-1).value

DWORD = wintypes.DWORD
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
u32 = ctypes.WinDLL("user32", use_last_error=True)

k32.CreateFileW.restype = wintypes.HANDLE
k32.CreateFileW.argtypes = [wintypes.LPCWSTR, DWORD, DWORD, ctypes.c_void_p,
                            DWORD, DWORD, wintypes.HANDLE]
k32.DeviceIoControl.argtypes = [wintypes.HANDLE, DWORD, ctypes.c_void_p, DWORD,
                                ctypes.c_void_p, DWORD, ctypes.POINTER(DWORD), ctypes.c_void_p]
k32.DeviceIoControl.restype = wintypes.BOOL
k32.CreateEventW.restype = wintypes.HANDLE
k32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
k32.GetOverlappedResult.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
                                    ctypes.POINTER(DWORD), wintypes.BOOL]
k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, DWORD]
k32.CloseHandle.argtypes = [wintypes.HANDLE]
k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenProcess.argtypes = [DWORD, wintypes.BOOL, DWORD]


class OVERLAPPED(ctypes.Structure):
    _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p),
                ("Offset", DWORD), ("OffsetHigh", DWORD), ("hEvent", wintypes.HANDLE)]


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [("cb", DWORD), ("DeviceName", ctypes.c_wchar * 32),
                ("DeviceString", ctypes.c_wchar * 128), ("StateFlags", DWORD),
                ("DeviceID", ctypes.c_wchar * 128), ("DeviceKey", ctypes.c_wchar * 128)]


class DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", ctypes.c_wchar * 32), ("dmSpecVersion", wintypes.WORD),
        ("dmDriverVersion", wintypes.WORD), ("dmSize", wintypes.WORD),
        ("dmDriverExtra", wintypes.WORD), ("dmFields", DWORD),
        ("dmOrientation", ctypes.c_short), ("dmPaperSize", ctypes.c_short),
        ("dmPaperLength", ctypes.c_short), ("dmPaperWidth", ctypes.c_short),
        ("dmScale", ctypes.c_short), ("dmCopies", ctypes.c_short),
        ("dmDefaultSource", ctypes.c_short), ("dmPrintQuality", ctypes.c_short),
        ("dmColor", ctypes.c_short), ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short), ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short), ("dmFormName", ctypes.c_wchar * 32),
        ("dmLogPixels", wintypes.WORD), ("dmBitsPerPel", DWORD),
        ("dmPelsWidth", DWORD), ("dmPelsHeight", DWORD), ("dmDisplayFlags", DWORD),
        ("dmDisplayFrequency", DWORD), ("dmICMMethod", DWORD), ("dmICMIntent", DWORD),
        ("dmMediaType", DWORD), ("dmDitherType", DWORD), ("dmReserved1", DWORD),
        ("dmReserved2", DWORD), ("dmPanningWidth", DWORD), ("dmPanningHeight", DWORD)]

DM_PELSWIDTH = 0x00080000
DM_PELSHEIGHT = 0x00100000
DM_DISPLAYFREQUENCY = 0x00400000
ENUM_CURRENT = 0xFFFFFFFF
STATE_ATTACHED = 0x1


# ---------------------------------------------------------------- VDD 操作
def vdd_open():
    cands = []
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"SYSTEM\CurrentControlSet\Control\DeviceClasses\\" + IFACE_GUID)
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(key, i)
                i += 1
            except OSError:
                break
            if sub.startswith("##?#"):
                sub = sub[4:]
            cands.append("\\\\?\\" + sub)
    except OSError:
        pass
    cands.append("\\\\?\\ROOT#DISPLAY#0000#" + IFACE_GUID)
    for path in cands:
        h = k32.CreateFileW(path, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_RW,
                            None, OPEN_EXISTING, OPEN_FLAGS, None)
        if h != INVALID_HANDLE:
            return h
    return None


def vdd_ioctl(h, code, data=None, timeout_ms=5000):
    inbuf = ctypes.create_string_buffer(32)
    if data:
        ctypes.memmove(inbuf, data, min(len(data), 32))
    out = DWORD(0)
    ov = OVERLAPPED()
    ov.hEvent = k32.CreateEventW(None, True, False, None)
    if not ov.hEvent:
        return None
    try:
        ok = k32.DeviceIoControl(h, code, inbuf, 32, ctypes.byref(out), 4, None, ctypes.byref(ov))
        if not ok:
            err = ctypes.get_last_error()
            if err != ERROR_IO_PENDING:
                return None
            if k32.WaitForSingleObject(ov.hEvent, timeout_ms) != 0:
                return None
            n = DWORD(0)
            if not k32.GetOverlappedResult(h, ctypes.byref(ov), ctypes.byref(n), False):
                return None
        return out.value
    finally:
        k32.CloseHandle(ov.hEvent)


def vdd_version():
    h = vdd_open()
    if not h:
        return None
    try:
        return vdd_ioctl(h, IOCTL_VERSION)
    finally:
        k32.CloseHandle(h)


def vdd_plug():
    """确保至少有 1 台虚拟显示器。返回是否成功。"""
    h = vdd_open()
    if not h:
        return False
    try:
        if vdd_ioctl(h, IOCTL_VERSION) is None:
            return False
        vdd_ioctl(h, IOCTL_ADD)
        vdd_ioctl(h, IOCTL_UPDATE)
        time.sleep(1.0)
        return True
    finally:
        k32.CloseHandle(h)


def vdd_unplug_all():
    h = vdd_open()
    if not h:
        return False
    try:
        for i in range(MAX_INDEX):
            if virtual_count() == 0:
                break
            data = bytes([((i >> 8) & 0xFF), (i & 0xFF)])
            vdd_ioctl(h, IOCTL_REMOVE, data)
            vdd_ioctl(h, IOCTL_UPDATE)
            time.sleep(0.2)
        return True
    finally:
        k32.CloseHandle(h)


# ---------------------------------------------------------------- 显示操作
def adapters():
    out = []
    i = 0
    while True:
        d = DISPLAY_DEVICEW()
        d.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        if not u32.EnumDisplayDevicesW(None, i, ctypes.byref(d), 0):
            break
        has_mon = False
        j = 0
        while True:
            m = DISPLAY_DEVICEW()
            m.cb = ctypes.sizeof(DISPLAY_DEVICEW)
            if not u32.EnumDisplayDevicesW(d.DeviceName, j, ctypes.byref(m), 0):
                break
            has_mon = True
            j += 1
        out.append({"name": d.DeviceName, "string": d.DeviceString or "",
                    "flags": d.StateFlags, "has_monitor": has_mon})
        i += 1
    return out


def virtual_count():
    """⚠ 驱动怪癖：只要有 ping 会话，它会把全部 16 个插槽都报成"有监视器对象"。
    这个数字只能当调试参考，不能用来判断有没有显示器。用 attached_parsec()。"""
    return sum(1 for a in adapters() if a["has_monitor"] and "Parsec" in a["string"])


def attached_parsec():
    """挂到桌面的 Parsec 显示器数量 —— 真正参与桌面的数量。"""
    return sum(1 for a in adapters()
               if "Parsec" in a["string"] and (a["flags"] & STATE_ATTACHED))


def virtual_device_name():
    """优先返回"挂到桌面"的那台 Parsec 显示器名，否则退回任意一台。"""
    fallback = None
    for a in adapters():
        if a["has_monitor"] and "Parsec" in a["string"]:
            if a["flags"] & STATE_ATTACHED:
                return a["name"]
            fallback = fallback or a["name"]
    return fallback


def real_device_name():
    for a in adapters():
        if a["has_monitor"] and "Parsec" not in a["string"] and (a["flags"] & STATE_ATTACHED):
            return a["name"]
    return None


def list_modes(dev):
    """返回 [(w, h, hz), ...] 全部可用模式。"""
    modes = set()
    i = 0
    while True:
        dm = DEVMODEW()
        dm.dmSize = ctypes.sizeof(DEVMODEW)
        if not u32.EnumDisplaySettingsW(dev, i, ctypes.byref(dm)):
            break
        modes.add((dm.dmPelsWidth, dm.dmPelsHeight, dm.dmDisplayFrequency))
        i += 1
    return sorted(modes, key=lambda t: (-t[0], -t[1], -t[2]))


def current_mode(dev):
    dm = DEVMODEW()
    dm.dmSize = ctypes.sizeof(DEVMODEW)
    if u32.EnumDisplaySettingsW(dev, ENUM_CURRENT, ctypes.byref(dm)):
        return (dm.dmPelsWidth, dm.dmPelsHeight, dm.dmDisplayFrequency)
    return None


def set_mode(dev, w, h, hz):
    dm = DEVMODEW()
    dm.dmSize = ctypes.sizeof(DEVMODEW)
    if not u32.EnumDisplaySettingsW(dev, ENUM_CURRENT, ctypes.byref(dm)):
        return False
    if (dm.dmPelsWidth, dm.dmPelsHeight, dm.dmDisplayFrequency) == (w, h, hz):
        return True
    dm.dmPelsWidth = w
    dm.dmPelsHeight = h
    dm.dmDisplayFrequency = hz
    dm.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT | DM_DISPLAYFREQUENCY
    return u32.ChangeDisplaySettingsExW(dev, ctypes.byref(dm), None, 0, None) == 0


def display_switch(flag):
    exe = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "DisplaySwitch.exe")
    try:
        subprocess.run([exe, flag], capture_output=True, timeout=10)
        time.sleep(2.0)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- 进程 / 设置
def pid_alive(pid):
    if not pid:
        return False
    h = k32.OpenProcess(0x1000, False, int(pid))
    if not h:
        return False
    k32.CloseHandle(h)
    return True


def read_pid(path):
    try:
        return int(open(path).read().strip())
    except Exception:
        return None


GHEARTBEAT = os.path.join(BASE, "guardian_heartbeat.txt")


def guardian_running():
    """守护是否在跑：pid 文件 或 心跳新鲜（<150s）都算。"""
    if pid_alive(read_pid(GPID_FILE)):
        return True
    try:
        age = time.time() - float(open(GHEARTBEAT).read().strip())
        return age < 150
    except Exception:
        return False


def load_settings():
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(data):
    try:
        os.makedirs(BASE, exist_ok=True)
        with open(SETTINGS, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


def run_hidden(args):
    flags = 0x00000008 | 0x00000200
    try:
        subprocess.Popen(args, creationflags=flags, close_fds=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def daemon(action, extra=None):
    args = [PYTHON, DAEMON, action] + list(extra or [])
    try:
        r = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=60)
        return r.stdout or r.stderr or ""
    except Exception as exc:
        return "调用失败: %r" % (exc,)


def read_sunshine_conf():
    try:
        with open(SUNSHINE_CONF, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def patch_sunshine_conf():
    """从 sunshine.conf 移除 dd_*（显示设备管理）配置（需要管理员）。

    dd_configuration_option = ensure_only_display 会和虚拟显示器抢桌面：
    每次串流开始 Sunshine 都把桌面切回物理屏、拔下虚拟显示器，
    物理屏一断电串流就黑屏。桌面拓扑应当归虚拟显示器保活脚本管。
    """
    txt = read_sunshine_conf()
    if not txt:
        return False, "读不到 sunshine.conf"
    backup = SUNSHINE_CONF + ".bak"
    try:
        open(backup, "w", encoding="utf-8").write(txt)
    except OSError:
        pass
    out = []
    removed = []
    for ln in txt.splitlines():
        s = ln.strip()
        key = s.split("=")[0].strip() if "=" in s else ""
        if key.startswith("dd_") and not s.startswith("#"):
            removed.append(key)
        else:
            out.append(ln)
    if not removed:
        return True, "conf 里没有 dd_* 配置，无需修改"
    try:
        with open(SUNSHINE_CONF, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
        return True, ("已移除 %d 行 dd_* 配置（备份在 sunshine.conf.bak）。"
                      "重启 Sunshine 服务后生效。" % len(removed))
    except OSError as exc:
        return False, "写入失败: %r" % (exc,)


# ---------------------------------------------------------------- GUI
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("640x620")
        self.minsize(600, 560)
        try:
            self.iconbitmap(default="")
        except Exception:
            pass

        self.settings = load_settings()
        self.follow_var = tk.BooleanVar(value=bool(self.settings.get("follow_moonlight")))
        self.size_var = tk.StringVar()
        self.hz_var = tk.StringVar()
        self.all_modes = []

        self._build()
        self.refresh_lists()
        self.tick()
        self.log("控制面板已启动")

    # ---------------- 布局
    def _build(self):
        pad = {"padx": 12, "pady": 6}

        # --- 状态
        box = ttk.LabelFrame(self, text=" 状态 ")
        box.pack(fill="x", **pad)
        self.lbl_driver = ttk.Label(box, text="驱动版本：—")
        self.lbl_driver.grid(row=0, column=0, sticky="w", padx=10, pady=4)
        self.lbl_virtual = ttk.Label(box, text="虚拟显示器：—")
        self.lbl_virtual.grid(row=0, column=1, sticky="w", padx=10, pady=4)
        self.lbl_daemon = ttk.Label(box, text="保活进程：—")
        self.lbl_daemon.grid(row=1, column=0, sticky="w", padx=10, pady=4)
        self.lbl_guardian = ttk.Label(box, text="自愈守护：—")
        self.lbl_guardian.grid(row=1, column=1, sticky="w", padx=10, pady=4)
        self.lbl_mode = ttk.Label(box, text="当前分辨率：—")
        self.lbl_mode.grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=4)
        box.columnconfigure(0, weight=1)
        box.columnconfigure(1, weight=1)

        # --- 分辨率
        box2 = ttk.LabelFrame(self, text=" 虚拟显示器 ")
        box2.pack(fill="x", **pad)

        ttk.Label(box2, text="分辨率").grid(row=0, column=0, sticky="w", padx=10, pady=6)
        self.cb_size = ttk.Combobox(box2, textvariable=self.size_var, width=18, state="readonly")
        self.cb_size.grid(row=0, column=1, padx=6, pady=6, sticky="w")
        self.cb_size.bind("<<ComboboxSelected>>", lambda e: self.refresh_hz())

        ttk.Label(box2, text="刷新率").grid(row=0, column=2, sticky="w", padx=10, pady=6)
        self.cb_hz = ttk.Combobox(box2, textvariable=self.hz_var, width=10, state="readonly")
        self.cb_hz.grid(row=0, column=3, padx=6, pady=6, sticky="w")

        self.chk_follow = ttk.Checkbutton(
            box2, text="跟随 Moonlight（串流时由 Sunshine 按客户端分辨率自动设置）",
            variable=self.follow_var, command=self.on_follow_toggle)
        self.chk_follow.grid(row=1, column=0, columnspan=4, sticky="w", padx=10, pady=4)

        row = ttk.Frame(box2)
        row.grid(row=2, column=0, columnspan=4, sticky="w", padx=6, pady=8)
        ttk.Button(row, text="应用并重启保活", command=self.on_apply).pack(side="left", padx=4)
        ttk.Button(row, text="启动", command=self.on_start).pack(side="left", padx=4)
        ttk.Button(row, text="停止", command=self.on_stop).pack(side="left", padx=4)
        ttk.Button(row, text="刷新", command=self.refresh_lists).pack(side="left", padx=4)

        # --- 桌面切换
        box3 = ttk.LabelFrame(self, text=" 桌面显示在（切换） ")
        box3.pack(fill="x", **pad)
        r = ttk.Frame(box3)
        r.pack(anchor="w", padx=6, pady=8)
        ttk.Button(r, text="仅真实显示器", command=lambda: self.on_switch("real")).pack(side="left", padx=4)
        ttk.Button(r, text="仅虚拟显示器", command=lambda: self.on_switch("virtual")).pack(side="left", padx=4)
        ttk.Button(r, text="扩展（两者）", command=lambda: self.on_switch("both")).pack(side="left", padx=4)
        ttk.Label(box3, text="键盘备用方案：Win + P", foreground="#666").pack(anchor="w", padx=12, pady=(0, 8))

        # --- Sunshine
        box4 = ttk.LabelFrame(self, text=" Sunshine 集成 ")
        box4.pack(fill="x", **pad)
        self.lbl_sun = ttk.Label(box4, text="读取中…", justify="left")
        self.lbl_sun.pack(anchor="w", padx=12, pady=6)
        ttk.Button(box4, text="移除 Sunshine 冲突配置（需要管理员）",
                   command=self.on_patch_sunshine).pack(anchor="w", padx=12, pady=(0, 8))

        # --- 日志
        box5 = ttk.LabelFrame(self, text=" 日志 ")
        box5.pack(fill="both", expand=True, **pad)
        self.txt = tk.Text(box5, height=8, wrap="word", font=("Consolas", 9))
        self.txt.pack(fill="both", expand=True, padx=8, pady=6)

    # ---------------- 工具
    def log(self, msg):
        ts = time.strftime("%H:%M:%S")
        self.txt.insert("end", "[%s] %s\n" % (ts, msg))
        self.txt.see("end")

    def refresh_lists(self):
        dev = virtual_device_name()
        if not dev:
            # 不要在这里自动 ADD：保活进程自己会 ADD，两边都插会造成
            # "重复添加 -> remove(0) 全清 -> 掉到 0" 的抖动（09-30 13:56 踩过）
            self.log("虚拟显示器未挂到桌面；保活进程在跑的话会自动接回，否则点「启动」")
        if dev:
            self.all_modes = list_modes(dev)
            sizes = []
            for w, h, _ in self.all_modes:
                s = "%d x %d" % (w, h)
                if s not in sizes:
                    sizes.append(s)
            self.cb_size["values"] = sizes
            cur = current_mode(dev)
            if cur:
                target = "%d x %d" % (cur[0], cur[1])
                if target in sizes:
                    self.size_var.set(target)
                self.hz_var.set(str(cur[2]))
            self.refresh_hz()
            self.log("虚拟显示器：%s，可用模式 %d 种" % (dev, len(self.all_modes)))
        else:
            self.all_modes = []
            self.log("⚠ 虚拟显示器不可用，请点「启动」")
        self.update_sunshine()

    def refresh_hz(self):
        try:
            w, h = [int(x) for x in self.size_var.get().replace(" ", "").split("x")]
        except Exception:
            return
        hzs = [str(z) for (ww, hh, z) in self.all_modes if ww == w and hh == h]
        self.cb_hz["values"] = hzs
        if hzs and self.hz_var.get() not in hzs:
            self.hz_var.set(hzs[0])

    def update_sunshine(self):
        txt = read_sunshine_conf()
        if not txt:
            self.lbl_sun.config(text="读不到 sunshine.conf")
            return
        got = {}
        for ln in txt.splitlines():
            s = ln.strip()
            if "=" in s and not s.startswith("#"):
                k, _, v = s.partition("=")
                got[k.strip()] = v.strip()
        dd = got.get("dd_configuration_option", "(未设置)")
        lines = []
        if dd in ("(未设置)", "disabled"):
            lines.append("✅ 显示设备管理未启用（推荐）—— 桌面拓扑归虚拟显示器保活脚本管")
            for k in ("dd_resolution_option", "dd_refresh_rate_option"):
                if k in got:
                    lines.append("ℹ %s = %s（dd_configuration_option 未启用，此行不生效）"
                                 % (k, got[k]))
        elif dd == "verify_only":
            lines.append("ℹ verify_only：Sunshine 只校验拓扑不改动（可接受）")
        else:
            lines.append("⚠ dd_configuration_option = %s —— 与虚拟显示器冲突！" % dd)
            lines.append("   每次串流开始它都会把桌面切回物理屏并拔下虚拟显示器，")
            lines.append("   物理屏一断电串流就黑屏。点下面按钮移除，或手工删掉 conf 里的 dd_* 行。")
            for k in ("dd_resolution_option", "dd_refresh_rate_option"):
                if k in got:
                    lines.append("⚠ %s = %s（此时作用在物理屏上）" % (k, got[k]))
        self.lbl_sun.config(text="\n".join(lines))

    # ---------------- 动作
    def on_follow_toggle(self):
        follow = self.follow_var.get()
        state = "disabled" if follow else "readonly"
        self.cb_size.config(state=state)
        self.cb_hz.config(state=state)
        tip = "已开启：串流时由 Sunshine 设置分辨率" if follow else "已关闭：由上面的分辨率决定"
        self.log(tip)

    def on_apply(self):
        follow = self.follow_var.get()
        if follow:
            self.settings["follow_moonlight"] = True
            save_settings(self.settings)
            self.log("保存设置：跟随 Moonlight（不再强制分辨率）")
        else:
            s = self.size_var.get().replace(" ", "")
            hz = self.hz_var.get()
            if not s or not hz:
                self.log("⚠ 请先选择分辨率和刷新率")
                return
            self.settings["follow_moonlight"] = False
            self.settings["resolution"] = "%s@%s" % (s, hz)
            save_settings(self.settings)
            dev = virtual_device_name()
            if dev:
                try:
                    w, h = [int(x) for x in s.split("x")]
                    ok = set_mode(dev, w, h, int(hz))
                    self.log("立即设置 %s@%s -> %s" % (s, hz, "成功" if ok else "失败"))
                except Exception as exc:
                    self.log("设置失败: %r" % (exc,))
            self.log("保存设置：%s@%s" % (s, hz))
        self.log("重启保活进程 …")
        daemon("stop")
        time.sleep(1)
        run_hidden([PYTHON, DAEMON, "start"])
        time.sleep(6)
        self.tick()

    def on_start(self):
        self.log("启动保活进程（由它统一 ADD，避免重复添加）…")
        run_hidden([PYTHON, DAEMON, "start"])
        run_hidden([PYTHONW, GUARDIAN])
        time.sleep(6)
        self.refresh_lists()
        self.tick()

    def on_stop(self):
        self.log("停止并拔出虚拟显示器 …")
        out = daemon("stop")
        for line in (out or "").strip().splitlines()[-3:]:
            self.log("  " + line)
        self.tick()

    def on_switch(self, target):
        if not os.path.exists(SWITCH):
            self.log("⚠ 找不到 vdd-switch.py")
            return
        flag = {"real": "/internal", "virtual": "/external", "both": "/extend"}[target]
        # 告诉保活进程这是不是用户主动选的"仅真实显示器"（是的话它不抢回）
        if target == "real":
            try:
                open(REALONLY_FLAG, "w").close()
                self.log("已写 realonly 标记：保活自愈不会把虚拟屏抢回来")
            except OSError:
                pass
        else:
            try:
                os.remove(REALONLY_FLAG)
                self.log("已清除 realonly 标记：保活自愈恢复待命")
            except OSError:
                pass
        if target == "virtual" and not virtual_device_name():
            self.log("虚拟显示器不存在，先接入 …")
            vdd_plug()
            time.sleep(1)
        self.log("切换中 …")
        display_switch(flag)
        time.sleep(1)
        real = real_device_name()
        virt = virtual_device_name()
        self.log("切换后 → 真实：%s ／ 虚拟：%s" % (real or "未激活", virt or "未激活"))
        self.tick()

    def on_patch_sunshine(self):
        if not getattr(sys, "frozen", False):
            ok, msg = patch_sunshine_conf()
            self.log(("Sunshine 配置：%s" % msg) if ok else ("失败：%s" % msg))
            self.update_sunshine()
            return
        try:
            r = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable,
                                                    "--patch-sunshine", None, 1)
            if r > 32:
                self.log("已请求管理员权限写入 Sunshine 配置，完成后点「刷新」")
            else:
                self.log("提权被拒绝（返回 %d）" % r)
        except Exception as exc:
            self.log("提权失败：%r" % (exc,))

    # ---------------- 轮询
    def tick(self):
        try:
            ver = vdd_version()
            att = attached_parsec()
            dpid = read_pid(PID_FILE)
            gpid = read_pid(GPID_FILE)
            gok = guardian_running()
            daemon_ok = pid_alive(dpid)
            dev = virtual_device_name()

            self.lbl_driver.config(text="驱动版本：%s" % (ver if ver is not None else "未安装/不可用"))
            # 颜色/文案以 attached 为准（只看保活进程会出现
            # 绿色"已接入（挂到桌面 0 台）"的假象）
            if att >= 1:
                v_txt, v_col = "● 已挂到桌面（%d 台）" % att, "#0a7d33"
            elif daemon_ok:
                v_txt, v_col = "● 保活运行中，但未挂到桌面（被外部切离，等待自愈或手动切换）", "#b8860b"
            else:
                v_txt, v_col = "● 未接入（挂到桌面 0 台）", "#b3261e"
            self.lbl_virtual.config(text="虚拟显示器：%s" % v_txt, foreground=v_col)
            self.lbl_daemon.config(
                text="保活进程：%s" % ("● 运行中 (pid %s)" % dpid if daemon_ok else "● 未运行"),
                foreground="#0a7d33" if daemon_ok else "#b3261e")
            self.lbl_guardian.config(
                text="自愈守护：%s" % ("● 运行中%s" % (" (pid %s)" % gpid if pid_alive(gpid) else "")
                                       if gok else "● 未运行"),
                foreground="#0a7d33" if gok else "#b3261e")

            if dev:
                cur = current_mode(dev)
                if cur:
                    follow = self.follow_var.get()
                    tail = "（跟随 Moonlight 中）" if follow else ""
                    self.lbl_mode.config(text="当前分辨率：%d x %d @ %dHz  %s" % (cur[0], cur[1], cur[2], tail))
            else:
                self.lbl_mode.config(text="当前分辨率：—")
        except Exception as exc:
            self.lbl_mode.config(text="轮询出错：%r" % (exc,))
        self.after(2000, self.tick)


def selftest():
    """无窗口自检：把结果写到 gui_selftest.txt（因为 --windowed 没有控制台）。"""
    lines = []
    try:
        lines.append("BASE = %s" % BASE)
        lines.append("frozen = %s" % getattr(sys, "frozen", False))
        lines.append("executable = %s" % sys.executable)
        lines.append("driver version = %s" % vdd_version())
        lines.append("virtual count = %s" % virtual_count())
        dev = virtual_device_name()
        lines.append("virtual device = %s" % dev)
        if dev:
            lines.append("modes = %d" % len(list_modes(dev)))
            lines.append("current mode = %s" % (current_mode(dev),))
        lines.append("real device = %s" % real_device_name())
        dp = read_pid(PID_FILE)
        lines.append("daemon pid = %s alive = %s" % (dp, pid_alive(dp)))
        lines.append("guardian running = %s" % guardian_running())
        lines.append("settings = %s" % load_settings())
        lines.append("sunshine conf lines = %d" % len(read_sunshine_conf().splitlines()))
        lines.append("scripts exist: daemon=%s switch=%s" % (os.path.exists(DAEMON), os.path.exists(SWITCH)))
        lines.append("RESULT = OK")
    except Exception as exc:
        import traceback
        lines.append("RESULT = FAIL: %r" % (exc,))
        lines.append(traceback.format_exc())
    try:
        with open(os.path.join(BASE, "gui_selftest.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError:
        pass
    return 0


def main():
    if "--selftest" in sys.argv:
        return selftest()
    if "--patch-sunshine" in sys.argv:
        ok, msg = patch_sunshine_conf()
        ctypes.windll.user32.MessageBoxW(None, msg, "Sunshine 配置" + ("：成功" if ok else "：失败"), 0x40)
        return 0
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    app = App()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
