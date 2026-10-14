"""
VirtualDisplay panel - modern Qt6 UI.

Dark, card-based layout. Every action shells out to the proven engine scripts
through backend.py; this file is presentation only.

    VirtualDisplayPanel.exe            open the panel
    VirtualDisplayPanel.exe --selftest run backend checks headless, print report
"""

import os
import sys

from PySide6.QtCore import (QThread, QPropertyAnimation, QEasingCurve,
                            QRect, Qt, Signal, QObject)
from PySide6.QtGui import QColor, QPainter, QPen, QBrush
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QComboBox, QLineEdit, QButtonGroup, QCheckBox, QTextEdit,
    QSizePolicy, QGraphicsDropShadowEffect, QScrollArea,
)

import backend

APP_NAME = "VirtualDisplay"

# --------------------------------------------------------------------------- #
# palette
# --------------------------------------------------------------------------- #

C = {
    "bg":          "#0f1115",
    "card":        "#171a21",
    "card_hover":  "#1c2029",
    "border":      "#262b35",
    "text":        "#e8ebf0",
    "muted":       "#8b93a1",
    "faint":       "#5c6472",
    "accent":      "#4fd1c5",
    "accent_dim":  "#2b6f68",
    "success":     "#4ade80",
    "warning":     "#fbbf24",
    "danger":      "#f87171",
    "danger_dim":  "#7a3030",
}

STYLE = """
QWidget#Root {
    background-color: %(bg)s;
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    font-size: 12px;
    color: %(text)s;
}

QLabel#Sub   { font-size: 11px; color: %(faint)s; }
QLabel#SectionTitle { font-size: 12.5px; font-weight: 600; color: %(text)s; }
QLabel#Hint  { font-size: 11px; color: %(muted)s; }
QLabel#Key   { font-size: 11.5px; color: %(muted)s; }
QLabel#Value { font-size: 11.5px; color: %(text)s; font-weight: 500; }
QLabel#Pill  { font-size: 11px; font-weight: 600; padding: 2px 10px;
               border-radius: 9px; background-color: #1e232c; }

QFrame#Card {
    background-color: %(card)s;
    border: 1px solid %(border)s;
    border-radius: 12px;
}
QFrame#CardDanger { background-color: %(card)s; border: 1px solid %(danger_dim)s; border-radius: 12px; }

QPushButton {
    background-color: #1f242e;
    border: 1px solid %(border)s;
    border-radius: 8px;
    color: %(text)s;
    padding: 7px 14px;
    font-size: 12px;
    min-width: 68px;
}
QPushButton:hover  { background-color: #262c38; border-color: #333a47; }
QPushButton:pressed{ background-color: #1a1f28; }
QPushButton:disabled{ color: %(faint)s; border-color: #22262f; background-color: #191d24; }

QPushButton#Primary {
    background-color: %(accent)s; border: 1px solid %(accent)s; color: #06231f; font-weight: 600;
}
QPushButton#Primary:hover  { background-color: #65ded3; border-color: #65ded3; }
QPushButton#Primary:pressed{ background-color: #3fb9ad; border-color: #3fb9ad; }
QPushButton#Primary:disabled{ background-color: #23343a; border-color: #23343a; color: #4a5a60; }

QPushButton#Danger { background-color: #2a1c1c; border: 1px solid %(danger_dim)s; color: %(danger)s; }
QPushButton#Danger:hover { background-color: #3a2222; border-color: #a04a4a; }

QPushButton#Seg {
    background-color: transparent; border: 1px solid %(border)s; color: %(muted)s;
    border-radius: 7px; padding: 6px 10px; min-width: 52px; font-size: 11px;
}
QPushButton#Seg:hover { color: %(text)s; background-color: #1e232c; }
QPushButton#Seg:checked { background-color: %(accent_dim)s; border-color: %(accent)s; color: #d7fbf6; font-weight: 600; }

QComboBox {
    background-color: #1f242e; border: 1px solid %(border)s; border-radius: 8px;
    color: %(text)s; padding: 6px 10px; min-width: 130px; font-size: 12px;
}
QComboBox:hover { border-color: #333a47; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox::down-arrow {
    image: none; width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid %(muted)s;
}
QComboBox:hover::down-arrow { border-top-color: %(text)s; }
QComboBox QAbstractItemView {
    background-color: #1f242e; border: 1px solid %(border)s; border-radius: 8px;
    color: %(text)s; selection-background-color: %(accent_dim)s; padding: 4px;
}

QLineEdit {
    background-color: #1f242e; border: 1px solid %(border)s; border-radius: 8px;
    color: %(text)s; padding: 6px 10px; font-size: 12px;
}
QLineEdit:focus { border-color: %(accent)s; }

QCheckBox { color: %(text)s; font-size: 12px; spacing: 8px; }
QCheckBox::indicator {
    width: 15px; height: 15px; border-radius: 4px;
    border: 1px solid %(border)s; background-color: #1f242e;
}
QCheckBox::indicator:checked { background-color: %(accent)s; border-color: %(accent)s; }

QTextEdit#Log {
    background-color: #10131a; border: 1px solid %(border)s; border-radius: 8px;
    color: %(muted)s; font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 10.5px; padding: 8px;
}
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }

QScrollBar:vertical   { background: transparent; width: 10px; margin: 3px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 3px; }
QScrollBar::handle:vertical   { background: #2f3641; border-radius: 5px; min-height: 32px; }
QScrollBar::handle:horizontal { background: #2f3641; border-radius: 5px; min-width: 32px; }
QScrollBar::handle:vertical:hover,
QScrollBar::handle:horizontal:hover { background: #414b59; }
QScrollBar::handle:pressed { background: #4a5563; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; border: none; background: none; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
""" % C


# --------------------------------------------------------------------------- #
# small widgets
# --------------------------------------------------------------------------- #

class Dot(QWidget):
    """Status dot with a soft pulse when 'on'."""

    def __init__(self, on=False, color=None, size=9, parent=None):
        super().__init__(parent)
        self._on = on
        self._color = QColor(color or C["success"])
        self._size = size
        self.setFixedSize(size + 8, size + 8)
        self._anim = None

    def set_on(self, on, color=None):
        self._on = on
        if color:
            self._color = QColor(color)
        if on and self._anim is None:
            self._anim = QPropertyAnimation(self, b"opacity", self)
            self._anim.setDuration(1400)
            self._anim.setStartValue(1.0)
            self._anim.setKeyValueAt(0.5, 0.35)
            self._anim.setEndValue(1.0)
            self._anim.setEasingCurve(QEasingCurve.InOutSine)
            self._anim.setLoopCount(-1)
            self._anim.start()
        elif not on and self._anim is not None:
            self._anim.stop()
            self._anim = None
            self._opacity = 1.0
        self.update()

    def get_opacity(self):
        return getattr(self, "_opacity", 1.0)

    def set_opacity(self, v):
        self._opacity = v
        self.update()

    opacity = property(get_opacity, set_opacity)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        op = getattr(self, "_opacity", 1.0)
        col = QColor(self._color)
        col.setAlphaF(op if self._on else 0.35)
        d = self._size
        x = (self.width() - d) // 2
        y = (self.height() - d) // 2
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(col))
        p.drawEllipse(x, y, d, d)


def card(title=None, danger=False, parent=None):
    f = QFrame(parent)
    f.setObjectName("CardDanger" if danger else "Card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(10)
    if title:
        t = QLabel(title)
        t.setObjectName("SectionTitle")
        lay.addWidget(t)
    return f, lay


def kv_row(key, value):
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(8)
    k = QLabel(key)
    k.setObjectName("Key")
    v = QLabel(value)
    v.setObjectName("Value")
    v.setTextInteractionFlags(Qt.TextSelectableByMouse)
    h.addWidget(k)
    h.addStretch(1)
    h.addWidget(v)
    return w, v


def hline():
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet("background-color: %s; border: none;" % C["border"])
    return f


def short(text, limit=30):
    """Truncate for display; the caller puts the full text in a tooltip."""
    t = str(text)
    return t if len(t) <= limit else t[: limit - 1] + "\u2026"


def dark_chrome(widget):
    """Ask DWM for a dark title bar and Win11 rounded corners.

    Without this the window frame keeps the Windows accent colour (green on
    this machine), which clashes badly with a dark app.
    """
    try:
        import ctypes
        hwnd = int(widget.winId())
        dwm = ctypes.windll.dwmapi
        yes = ctypes.c_int(1)
        # DWMWA_USE_DARK_MODE = 20  (Win10 20H1+ / Win11)
        dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(yes), ctypes.sizeof(yes))
        # DWMWA_WINDOW_CORNER_PREFERENCE = 33, DWMWCP_ROUND = 2  (Win11 only)
        rnd = ctypes.c_int(2)
        dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(rnd), ctypes.sizeof(rnd))
    except Exception:                                          # noqa: BLE001
        pass


# --------------------------------------------------------------------------- #
# worker
# --------------------------------------------------------------------------- #

class Worker(QObject):
    done = Signal(object)

    def __init__(self, fn, *args):
        super().__init__()
        self._fn = fn
        self._args = args

    def run(self):
        try:
            res = self._fn(*self._args)
        except Exception as exc:                              # noqa: BLE001
            res = {"ok": False, "out": "", "error": str(exc)}
        self.done.emit(res)


class ActionThread(QThread):
    def __init__(self, fn, *args):
        super().__init__()
        self.worker = Worker(fn, *args)

    def run(self):
        self.worker.run()


# --------------------------------------------------------------------------- #
# main window
# --------------------------------------------------------------------------- #

class Main(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumWidth(600)
        self.setMinimumHeight(780)
        self._threads = []
        self._build()
        self.reload_status()

    def showEvent(self, ev):
        super().showEvent(ev)
        dark_chrome(self)

    # ---------------- construction ----------------

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        # header - the window title bar already says "VirtualDisplay", so there
        # is no big in-app title; just the context line and the status pill
        head = QHBoxLayout()
        head.setSpacing(10)
        sub = QLabel("虚拟显示器 · 单一目录 · 单进程 · C:\\VirtualDisplay")
        sub.setObjectName("Sub")
        head.addWidget(sub)
        head.addStretch(1)
        self.dot = Dot(False, C["faint"], 9)
        head.addWidget(self.dot, 0, Qt.AlignVCenter)
        self.pill = QLabel("检测中")
        self.pill.setObjectName("Pill")
        head.addWidget(self.pill, 0, Qt.AlignVCenter)
        root.addLayout(head)
        root.addSpacing(4)

        # scrollable body - horizontal scrolling must never happen: a long value
        # label would otherwise widen the layout and pop both scrollbars out
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(12)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # ---- status card ----
        c, cl = card("状态")
        self.row_driver, self.val_driver = kv_row("驱动版本", "—")
        self.row_daemon, self.val_daemon = kv_row("保活进程", "—")
        self.row_phys, self.val_phys = kv_row("物理显示器", "—")
        self.row_virt, self.val_virt = kv_row("虚拟显示器", "—")
        self.row_auto, self.val_auto = kv_row("开机自启", "—")
        for w in (self.row_driver, self.row_daemon, self.row_phys,
                  self.row_virt, self.row_auto):
            cl.addWidget(w)
        bl.addWidget(c)

        # ---- virtual display card ----
        c2, c2l = card("虚拟显示器")
        r1 = QHBoxLayout()
        r1.setSpacing(8)
        r1.addWidget(QLabel("分辨率"), 0)
        self.cmb_res = QComboBox()
        self.cmb_res.addItems(backend.RESOLUTIONS)
        self.cmb_res.setEditable(True)
        r1.addWidget(self.cmb_res, 1)
        c2l.addLayout(r1)

        self.chk_follow = QCheckBox("跟随 Moonlight（不强制分辨率）")
        c2l.addWidget(self.chk_follow)

        r2 = QHBoxLayout()
        r2.setSpacing(8)
        self.btn_start = QPushButton("启动")
        self.btn_start.setObjectName("Primary")
        self.btn_stop = QPushButton("停止")
        self.btn_restart = QPushButton("重启")
        for b in (self.btn_start, self.btn_stop, self.btn_restart):
            r2.addWidget(b)
        r2.addStretch(1)
        self.btn_refresh = QPushButton("刷新")
        r2.addWidget(self.btn_refresh)
        c2l.addLayout(r2)
        bl.addWidget(c2)

        # ---- desktop target card ----
        c3, c3l = card("桌面显示在")
        seg = QHBoxLayout()
        seg.setSpacing(6)
        self.seg_group = QButtonGroup(self)
        self.seg_btns = {}
        for i, (label, mode) in enumerate([("仅真实", "real"), ("仅虚拟", "virtual"),
                                           ("扩展", "both"), ("切换", "toggle")]):
            b = QPushButton(label)
            b.setObjectName("Seg")
            b.setCheckable(True)
            self.seg_group.addButton(b, i)
            self.seg_btns[mode] = b
            seg.addWidget(b)
        seg.addStretch(1)
        c3l.addLayout(seg)
        hint = QLabel("切换后鼠标可能跑到看不见的屏幕，随时可按 Win + P 回来")
        hint.setObjectName("Hint")
        c3l.addWidget(hint)
        bl.addWidget(c3)

        # ---- maintenance card ----
        c4, c4l = card("维护")
        r4 = QHBoxLayout()
        r4.setSpacing(8)
        self.btn_log = QPushButton("打开日志")
        self.btn_clean = QPushButton("清理残留")
        r4.addWidget(self.btn_log)
        r4.addWidget(self.btn_clean)
        r4.addStretch(1)
        c4l.addLayout(r4)

        r5 = QHBoxLayout()
        r5.setSpacing(8)
        self.chk_auto = QCheckBox("开机自动启动")
        self.btn_auto = QPushButton("应用")
        r5.addWidget(self.chk_auto)
        r5.addWidget(self.btn_auto)
        r5.addStretch(1)
        c4l.addLayout(r5)
        bl.addWidget(c4)

        # ---- danger card ----
        c5, c5l = card("驱动重置", danger=True)
        d1 = QLabel("虚拟屏建不起来、出现一堆 DISPLAY38~53 幽灵条目时用。"
                    "会禁用再启用 Parsec 适配器以清空驱动槽位表，并自动验证结果，不需要重启电脑。")
        d1.setObjectName("Hint")
        d1.setWordWrap(True)
        c5l.addWidget(d1)
        r6 = QHBoxLayout()
        self.btn_reset = QPushButton("重置驱动并启动")
        self.btn_reset.setObjectName("Danger")
        self.btn_doctor = QPushButton("诊断驱动")
        r6.addWidget(self.btn_reset)
        r6.addWidget(self.btn_doctor)
        r6.addStretch(1)
        c5l.addLayout(r6)
        self.lbl_verdict = QLabel("")
        self.lbl_verdict.setObjectName("Hint")
        self.lbl_verdict.setWordWrap(True)
        self.lbl_verdict.setVisible(False)
        c5l.addWidget(self.lbl_verdict)
        bl.addWidget(c5)

        # ---- log ----
        c6, c6l = card("最近日志")
        self.txt_log = QTextEdit()
        self.txt_log.setObjectName("Log")
        self.txt_log.setReadOnly(True)
        self.txt_log.setFixedHeight(150)
        c6l.addWidget(self.txt_log)
        bl.addWidget(c6)

        bl.addStretch(1)

        # ---- signals ----
        self.btn_start.clicked.connect(lambda: self._act(backend.start, self._res()))
        self.btn_stop.clicked.connect(lambda: self._act(backend.stop))
        self.btn_restart.clicked.connect(lambda: self._act(backend.restart, self._res()))
        self.btn_refresh.clicked.connect(self.reload_status)
        self.btn_log.clicked.connect(lambda: self._act(backend.open_log))
        self.btn_clean.clicked.connect(lambda: self._act(backend.clean))
        self.btn_auto.clicked.connect(self._apply_autostart)
        self.btn_reset.clicked.connect(self._reset)
        self.btn_doctor.clicked.connect(self._doctor)
        self.seg_group.buttonClicked.connect(self._switch)
        self.chk_follow.stateChanged.connect(self._follow_changed)

    # ---------------- helpers ----------------

    def _res(self):
        return self.cmb_res.currentText().strip()

    def _act(self, fn, *args):
        """Run a backend action off the UI thread, then refresh."""
        self._set_busy(True)
        t = ActionThread(fn, *args)
        t.worker.done.connect(lambda _r: self._after(t, _r))
        t.finished.connect(lambda: self._set_busy(False))
        self._threads.append(t)
        t.start()

    def _after(self, thread, res):
        # surface a verdict line for the driver card
        if isinstance(res, dict) and "wedged" in res:
            if res.get("wedged"):
                self._show_verdict(
                    "驱动卡死：能接受指令但不创建显示器。"
                    "请先点「重置驱动并启动」；若仍卡死则需重启电脑。", C["danger"])
            elif res.get("healthy"):
                self._show_verdict("驱动正常 ✓", C["success"])
            elif res.get("not_attached"):
                self._show_verdict(
                    "驱动正常，显示器已创建但未挂到桌面 —— 用上面的「仅虚拟」切换接上。",
                    C["warning"])
            else:
                self._show_verdict(res.get("verdict") or "诊断完成", C["muted"])
        elif isinstance(res, dict) and not res.get("ok") and res.get("error"):
            self._show_verdict("失败：" + res["error"], C["danger"])

        if res.get("ok"):
            self.txt_log.setPlainText(backend.log_tail(30))
        else:
            detail = res.get("out") or ""
            self.txt_log.setPlainText(
                "ERROR: %s\n\n%s\n\n%s"
                % (res.get("error", ""), detail, backend.log_tail(20)))
        self.reload_status()

    def _set_busy(self, busy):
        for b in (self.btn_start, self.btn_stop, self.btn_restart,
                  self.btn_clean, self.btn_reset, self.btn_auto):
            b.setEnabled(not busy)
        self.btn_refresh.setEnabled(True)

    # ---------------- actions ----------------

    def reload_status(self):
        s = backend.status()
        self._st = s

        self.val_driver.setText(
            "v%s（err %s）" % (s["driver_version"], s["driver_error"])
            if s["driver_version"] is not None else "未检测到")

        if s["daemon_running"]:
            pid = " PID %s" % s["daemon_pid"] if s["daemon_pid"] else ""
            self.val_daemon.setText("运行中%s" % pid)
            self.val_daemon.setStyleSheet("color:%s;font-weight:600;" % C["success"])
        else:
            self.val_daemon.setText("未运行")
            self.val_daemon.setStyleSheet("color:%s;font-weight:600;" % C["warning"])

        p = s["physical"]
        if p:
            full = "%dx%d @ %dHz" % (p[0], p[1], p[2])
            self.val_phys.setText(short(full, 26))
            self.val_phys.setToolTip("%s\n%s" % (full, p[3]))
        else:
            self.val_phys.setText("—")
            self.val_phys.setToolTip("")

        vd = s["virtual_displays"]
        orphans = s.get("orphan_entries") or []
        if not vd and orphans:
            # nothing attached AND orphans present: the orphans are the blocker,
            # so say that instead of a bare "未挂载"
            self.val_virt.setText("未挂载（%d 个残留条目挡路）" % len(orphans))
            self.val_virt.setStyleSheet("color:%s;font-weight:600;" % C["danger"])
            self.val_virt.setToolTip(
                "检测到 %d 个残留的虚拟显示器条目：\n%s\n\n"
                "它们占着驱动插槽，新的显示器建不起来。\n"
                "点最下面「重置驱动并启动」清空（自动提权，不用重启电脑）。\n"
                "重置不掉就重启一次电脑。"
                % (len(orphans), "\n".join(orphans)))
        elif not vd:
            self.val_virt.setText("未挂载")
            self.val_virt.setStyleSheet("color:%s;font-weight:600;" % C["warning"])
            self.val_virt.setToolTip("")
        elif len(vd) == 1:
            res = s["configured_resolution"] or "跟随客户端"
            self.val_virt.setText("%s · %s" % (vd[0], res))
            self.val_virt.setStyleSheet("color:%s;font-weight:600;" % C["success"])
            self.val_virt.setToolTip("")
        else:
            # more than one virtual display means the driver's slot table is
            # polluted - say so instead of dumping a wall of device names
            res = s["configured_resolution"] or "跟随客户端"
            self.val_virt.setText("%d 个（槽位已污染，建议重置） · %s" % (len(vd), res))
            self.val_virt.setStyleSheet("color:%s;font-weight:600;" % C["danger"])
            self.val_virt.setToolTip(
                "检测到 %d 个虚拟显示器：\n%s\n\n"
                "这是驱动槽位表被反复增删污染的表现。\n"
                "点最下面「重置驱动并启动」可清空，不用重启电脑。"
                % (len(vd), "\n".join(vd)))

        auto = s["autostart_installed"]
        self.val_auto.setText("已注册" if auto else "未注册")
        self.val_auto.setStyleSheet(
            "color:%s;font-weight:600;" % (C["success"] if auto else C["faint"]))

        # header pill
        healthy = bool(vd) and s["daemon_running"]
        polluted = len(vd) > 1 or bool(orphans)
        if healthy and not polluted:
            tone, word = C["success"], "运行中"
        elif orphans and not vd:
            tone, word = C["danger"], "残留挡路"
        elif polluted:
            tone, word = C["danger"], "槽位污染"
        elif s["ok"]:
            tone, word = C["warning"], "未挂载"
        else:
            tone, word = C["danger"], "驱动不可用"
        self.dot.set_on(healthy and not polluted, tone)
        self.pill.setText(word)
        self.pill.setStyleSheet(
            "QLabel#Pill { font-size:11px; font-weight:600; padding:2px 10px;"
            "border-radius:9px; color:%s; background-color:%s; }"
            % (tone, "#1b2a27" if tone == C["success"] else
               "#2a1f1b" if tone == C["warning"] else "#2a1b1b"))

        # form state
        if s["configured_resolution"] and not self.cmb_res.signalsBlocked():
            idx = self.cmb_res.findText(s["configured_resolution"])
            if idx >= 0:
                self.cmb_res.setCurrentIndex(idx)
            else:
                self.cmb_res.setEditText(s["configured_resolution"])
        self.chk_follow.setChecked(bool(s["follow_moonlight"]))
        self.chk_auto.setChecked(bool(auto))

        self.txt_log.setPlainText(backend.log_tail(25))

    def _switch(self, btn):
        mode = [k for k, v in self.seg_btns.items() if v is btn][0]
        self._act(backend.switch, mode)

    def _follow_changed(self, state):
        """Persist follow_moonlight without touching the daemon."""
        try:
            with open(backend.SETTINGS, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:                                      # noqa: BLE001
            cfg = {}
        cfg["follow_moonlight"] = bool(state)
        try:
            with open(backend.SETTINGS, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception as exc:                              # noqa: BLE001
            self.txt_log.setPlainText("写设置失败: %s" % exc)

    def _apply_autostart(self):
        install = self.chk_auto.isChecked()
        if install and not backend.is_admin():
            if not backend.elevate_and_rerun():
                self.txt_log.setPlainText("需要管理员权限，UAC 已取消")
            return
        self._act(backend.autostart, install)

    def _reset(self):
        if not backend.is_admin():
            if not backend.elevate_and_rerun():
                self.txt_log.setPlainText("需要管理员权限，UAC 已取消")
            return
        self._show_verdict("重置中… 停保活 → 禁用适配器 → 启用 → 诊断验证", C["muted"])
        self._act(backend.reset_driver)

    def _doctor(self):
        self._show_verdict("诊断中…", C["muted"])
        self._act(backend.doctor)

    def _show_verdict(self, text, color):
        self.lbl_verdict.setText(text)
        self.lbl_verdict.setStyleSheet(
            "font-size:11px;color:%s;font-weight:500;" % color)
        self.lbl_verdict.setVisible(True)


# --------------------------------------------------------------------------- #
# selftest
# --------------------------------------------------------------------------- #

def selftest():
    import json
    print("=== VirtualDisplay panel selftest %s ===" % _now())
    print("root        :", backend.ROOT)
    for f in ("vdd-keepalive.py", "vdd-switch.py"):
        print("  exists %-20s %s" % (f, os.path.exists(os.path.join(backend.ROOT, f))))

    s = backend.status()
    print("\n-- status --")
    for k in ("ok", "driver_version", "driver_error", "daemon_running",
              "daemon_pid", "virtual_count", "virtual_displays",
              "physical", "configured_resolution", "follow_moonlight",
              "autostart_installed"):
        print("  %-22s %r" % (k, s[k]))
    if s["error"]:
        print("  ERROR:", s["error"])

    print("\n-- backend callables --")
    for name in ("start", "stop", "restart", "clean", "switch", "set_resolution",
                 "reset_driver", "autostart", "log_tail", "open_log", "is_admin"):
        print("  %-16s %s" % (name, callable(getattr(backend, name, None))))

    print("\n-- ui import --")
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        w = Main()
        print("  Main() constructed OK, size %dx%d" % (w.width(), w.height()))
        print("  combobox items:", w.cmb_res.count())
        print("  segment modes :", list(w.seg_btns.keys()))
    except Exception as exc:                                  # noqa: BLE001
        print("  UI FAIL:", exc)

    ok = (s["ok"] and s["driver_version"] is not None)
    print("\nRESULT =", "OK" if ok else "FAIL")
    return 0 if ok else 1


def _now():
    import time
    return time.strftime("%Y-%m-%d %H:%M:%S")


def main():
    import os
    if "--selftest" in sys.argv:
        return selftest()
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    w = Main()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
