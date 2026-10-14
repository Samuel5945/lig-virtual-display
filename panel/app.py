"""
VirtualDisplay panel - modern Qt6 UI for the MttVDD virtual display.

Dark, card-based. Every action goes through backend.py, which imports
vdd_core.py from the project root - the panel holds no logic of its own.

    VirtualDisplayPanel.exe              open the panel
    VirtualDisplayPanel.exe --selftest   headless check, prints a report
"""

import sys

from PySide6.QtCore import (QThread, QTimer, QPropertyAnimation, QEasingCurve,
                            Qt, Signal, QObject)
from PySide6.QtGui import QColor, QPainter, QBrush
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QComboBox, QSpinBox, QScrollArea, QSizeGrip,
)

import backend

APP_NAME = "VirtualDisplay"


# --------------------------------------------------------------------------- #
# palette
# --------------------------------------------------------------------------- #

C = {
    "bg":         "#0f1115",
    "card":       "#171a21",
    "border":     "#262b35",
    "text":       "#e8ebf0",
    "muted":      "#8b93a1",
    "faint":      "#5c6472",
    "accent":     "#4fd1c5",
    "accent_dim": "#2b6f68",
    "success":    "#4ade80",
    "warning":    "#fbbf24",
    "danger":     "#f87171",
    "danger_dim": "#7a3030",
}

STYLE = """
QWidget#Root {
    background-color: %(bg)s;
    border: 1px solid %(border)s;
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    font-size: 12px;
    color: %(text)s;
}

QWidget#TitleBar { background-color: %(card)s; border: none;
                   border-bottom: 1px solid %(border)s; }
QLabel#TitleText { font-size: 12px; font-weight: 600; color: %(text)s; }
QPushButton#WinBtn, QPushButton#WinClose {
    background-color: transparent; border: none; border-radius: 6px;
    color: %(muted)s; font-size: 12px; padding: 0; min-width: 0;
}
QPushButton#WinBtn:hover   { background-color: #262c38; color: %(text)s; }
QPushButton#WinClose:hover { background-color: #c0392b; color: #ffffff; }
QLabel#Sub   { font-size: 11px; color: %(faint)s; }
QLabel#SectionTitle { font-size: 12.5px; font-weight: 600; color: %(text)s; }
QLabel#Hint  { font-size: 11px; color: %(muted)s; }
QLabel#Key   { font-size: 11.5px; color: %(muted)s; }
QLabel#Value { font-size: 11.5px; color: %(text)s; font-weight: 500; }
QLabel#Pill  { font-size: 11px; font-weight: 600; padding: 2px 10px;
               border-radius: 9px; background-color: #1e232c; }
QLabel#Badge { font-size: 10px; font-weight: 600; color: %(accent)s;
               background-color: %(accent_dim)s; border-radius: 7px;
               padding: 1px 7px; }

QFrame#Card     { background-color: %(card)s; border: 1px solid %(border)s; border-radius: 12px; }
QFrame#CardWarn { background-color: %(card)s; border: 1px solid %(danger_dim)s; border-radius: 12px; }
QFrame#Banner   { background-color: #2a1b1b; border: 1px solid %(danger_dim)s; border-radius: 10px; }
QLabel#BannerText { color: #ffd9d9; font-size: 11.5px; }

QPushButton {
    background-color: #1f242e; border: 1px solid %(border)s; border-radius: 8px;
    color: %(text)s; padding: 7px 14px; font-size: 12px; min-width: 64px;
}
QPushButton:hover   { background-color: #262c38; border-color: #333a47; }
QPushButton:pressed { background-color: #1a1f28; }
QPushButton:disabled{ color: %(faint)s; border-color: #22262f; background-color: #191d24; }

QPushButton#Primary { background-color: %(accent)s; border: 1px solid %(accent)s;
                      color: #06231f; font-weight: 600; }
QPushButton#Primary:hover   { background-color: #65ded3; border-color: #65ded3; }
QPushButton#Primary:disabled{ background-color: #23343a; border-color: #23343a; color: #4a5a60; }

QPushButton#Danger  { background-color: #2a1c1c; border: 1px solid %(danger_dim)s; color: %(danger)s; }
QPushButton#Danger:hover { background-color: #3a2222; border-color: #a04a4a; }
QPushButton#BannerBtn { background-color: %(danger)s; border: 1px solid %(danger)s;
                        color: #2a0d0d; font-weight: 600; padding: 6px 14px; min-width: 0; }
QPushButton#BannerBtn:hover { background-color: #ff9a9a; border-color: #ff9a9a; }
QPushButton#MiniDanger { padding: 3px 9px; min-width: 0; font-size: 11px; border-radius: 6px;
                         background-color: #2a1c1c; border: 1px solid %(danger_dim)s; color: %(danger)s; }
QPushButton#MiniDanger:hover { background-color: #3a2222; }

QComboBox {
    background-color: #1f242e; border: 1px solid %(border)s; border-radius: 8px;
    color: %(text)s; padding: 6px 10px; min-width: 150px; font-size: 12px;
}
QComboBox:hover { border-color: #333a47; }
/* an explicit :focus rule is required: without it the style draws a focus
   rect in the widget's text colour, which shows up as a bright line along
   the top edge of the control */
QComboBox:focus, QComboBox:on { border: 1px solid %(accent)s; }
/* Do NOT style QComboBox::drop-down or ::down-arrow. Qt stops drawing the
   native subcontrol as soon as either is styled, and every workaround we
   tried produced artifacts: the border-triangle trick is browser-only and
   does nothing in Qt; a custom paintEvent on a subclass corrupted the styled
   frame (a bright full-width line along the top edge); an image on
   ::down-arrow rendered a second chevron in the middle. Leaving both rules
   out gives one clean native arrow. */
QComboBox QAbstractItemView {
    background-color: #1f242e; border: 1px solid %(border)s; border-radius: 8px;
    color: %(text)s; selection-background-color: %(accent_dim)s; padding: 4px;
}

QSpinBox {
    background-color: #1f242e; border: 1px solid %(border)s; border-radius: 8px;
    color: %(text)s; padding: 5px 8px; font-size: 12px;
    min-width: 52px; max-width: 86px;
}
QSpinBox:focus { border-color: %(accent)s; }
QSpinBox::up-button, QSpinBox::down-button { width: 0; border: none; }

QScrollArea { border: none; background: transparent; }
QScrollArea#Scroll, QScrollArea#Scroll > QWidget { background: transparent; }
QWidget#Body { background: transparent; }
QWidget#Row  { background: transparent; }
QScrollBar:vertical   { background: transparent; width: 10px; margin: 3px; }
QScrollBar::handle:vertical { background: #2f3641; border-radius: 5px; min-height: 32px; }
QScrollBar::handle:vertical:hover { background: #414b59; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; border: none; background: none; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
""" % C


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

class Dot(QWidget):
    """Status dot with a soft pulse when healthy."""

    def __init__(self, color=None, size=9, parent=None):
        super().__init__(parent)
        self._on = False
        self._color = QColor(color or C["success"])
        self._size = size
        self._opacity = 1.0
        self.setFixedSize(size + 8, size + 8)
        self._anim = None

    def set_state(self, on, color=None):
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
        self._on = on
        self.update()

    def get_opacity(self):
        return self._opacity

    def set_opacity(self, v):
        self._opacity = v
        self.update()

    opacity = property(get_opacity, set_opacity)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        col = QColor(self._color)
        col.setAlphaF(self._opacity if self._on else 0.4)
        d = self._size
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(col))
        p.drawEllipse((self.width() - d) // 2, (self.height() - d) // 2, d, d)


class TitleBar(QWidget):
    """Custom title bar, so the frame colour is ours instead of the OS accent.

    Why not just ask Windows for a dark frame: on this build it is impossible.
    Measured on Windows 10 19045 with the title bar sampled via GDI BitBlt:

        baseline                    #779c48   (the OS accent colour)
        DwmSetWindowAttribute(20)   returns S_OK, colour unchanged
        DwmSetWindowAttribute(19)   E_INVALIDARG
        SetWindowTheme(DarkMode_Explorer)  returns S_OK, colour unchanged

    Attribute 20 is a Windows 11 feature - on Windows 10 it reports success and
    does nothing. So the window is frameless and we draw the bar ourselves.
    """

    def __init__(self, parent, title):
        super().__init__(parent)
        self._win = parent
        self._drag_origin = None
        self.setObjectName("TitleBar")
        # a QWidget subclass does NOT honour a stylesheet background unless
        # this attribute is set - without it the bar stays transparent and
        # the QSS rule silently does nothing
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(40)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 8, 0)
        lay.setSpacing(8)

        self.dot_brand = Dot(C["accent"], 8)
        lay.addWidget(self.dot_brand, 0, Qt.AlignVCenter)

        name = QLabel(title)
        name.setObjectName("TitleText")
        lay.addWidget(name)
        lay.addStretch(1)

        for glyph, slot, obj in (("\u2500", self._on_min, "WinBtn"),
                                 ("\u2715", self._on_close, "WinClose")):
            b = QPushButton(glyph)
            b.setObjectName(obj)
            b.setFixedSize(36, 28)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(slot)
            lay.addWidget(b)

    def _on_min(self):
        self._win.showMinimized()

    def _on_close(self):
        self._win.close()

    # dragging the bar moves the window, as a native one would
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag_origin = (ev.globalPosition().toPoint()
                                 - self._win.frameGeometry().topLeft())
            ev.accept()

    def mouseMoveEvent(self, ev):
        if self._drag_origin is not None and ev.buttons() & Qt.LeftButton:
            self._win.move(ev.globalPosition().toPoint() - self._drag_origin)
            ev.accept()

    def mouseReleaseEvent(self, ev):
        self._drag_origin = None

    def mouseDoubleClickEvent(self, ev):
        if self._win.isMaximized():
            self._win.showNormal()
        else:
            self._win.showMaximized()


def dark_chrome(widget):
    """Kept only for the Win11 rounded-corner preference.

    On Windows 10 this cannot darken the title bar - see TitleBar's docstring
    for the measurements. The frameless window is what actually solves it.
    """
    try:
        import ctypes
        from ctypes import wintypes
        dwm = ctypes.windll.dwmapi
        dwm.DwmSetWindowAttribute.argtypes = [
            wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        dwm.DwmSetWindowAttribute.restype = ctypes.c_long
        hwnd = wintypes.HWND(int(widget.winId()))
        rnd = ctypes.c_int(2)
        dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(rnd), ctypes.sizeof(rnd))
    except Exception:                                          # noqa: BLE001
        pass


def card(title=None, warn=False):
    f = QFrame()
    f.setObjectName("CardWarn" if warn else "Card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(10)
    if title:
        t = QLabel(title)
        t.setObjectName("SectionTitle")
        lay.addWidget(t)
    return f, lay


def kv_row(key):
    w = QWidget()
    w.setObjectName("Row")
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(8)
    k = QLabel(key)
    k.setObjectName("Key")
    v = QLabel("—")
    v.setObjectName("Value")
    v.setTextInteractionFlags(Qt.TextSelectableByMouse)
    h.addWidget(k)
    h.addStretch(1)
    h.addWidget(v)
    return w, v


def friendly_device(name):
    """'\\\\.\\DISPLAY91' -> 'DISPLAY91'. The escaped form is what the Win32
    API returns but it reads like a typo in the UI."""
    return (name or "").replace("\\\\.\\", "").replace("\\\\?\\", "")


class Worker(QObject):
    done = Signal(object)

    def __init__(self, fn, *args):
        super().__init__()
        self._fn, self._args = fn, args

    def run(self):
        try:
            res = self._fn(*self._args)
        except Exception as exc:                               # noqa: BLE001
            res = {"ok": False, "error": str(exc)}
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
        self.setObjectName("Root")          # required by the QWidget#Root rule
        self.setWindowTitle(APP_NAME)
        # frameless: the native frame cannot be darkened on Windows 10, so we
        # draw our own title bar (see TitleBar)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setMinimumWidth(620)
        self.setMinimumHeight(720)
        self._threads = []
        self._st = {}
        self._build()
        self.reload()

    def showEvent(self, ev):
        super().showEvent(ev)
        # rounded corners where the OS supports it (Win11); harmless elsewhere
        dark_chrome(self)

    # ---------------- construction ----------------

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)   # room for the border
        outer.setSpacing(0)

        self.title_bar = TitleBar(self, APP_NAME)
        outer.addWidget(self.title_bar)

        root = QVBoxLayout()
        root.setContentsMargins(20, 14, 20, 14)
        root.setSpacing(12)
        outer.addLayout(root, 1)

        head = QHBoxLayout()
        head.setSpacing(10)
        sub = QLabel("虚拟显示器 · MttVDD · C:\\VirtualDisplay")
        sub.setObjectName("Sub")
        head.addWidget(sub)
        head.addStretch(1)
        self.dot = Dot(C["faint"], 9)
        head.addWidget(self.dot, 0, Qt.AlignVCenter)
        self.pill = QLabel("检测中")
        self.pill.setObjectName("Pill")
        head.addWidget(self.pill, 0, Qt.AlignVCenter)
        root.addLayout(head)

        # alert banner - shown only when something needs doing, and always
        # with its own fix button so the remedy is never off-screen
        self.banner = QFrame()
        self.banner.setObjectName("Banner")
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(14, 10, 12, 10)
        bl.setSpacing(10)
        self.banner_dot = Dot(C["danger"], 8)
        bl.addWidget(self.banner_dot, 0, Qt.AlignVCenter)
        self.banner_text = QLabel("")
        self.banner_text.setObjectName("BannerText")
        self.banner_text.setWordWrap(True)
        bl.addWidget(self.banner_text, 1)
        self.banner_btn = QPushButton("安装驱动")
        self.banner_btn.setObjectName("BannerBtn")
        bl.addWidget(self.banner_btn, 0, Qt.AlignVCenter)
        self.banner.setVisible(False)
        root.addWidget(self.banner)

        scroll = QScrollArea()
        scroll.setObjectName("Scroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        body.setObjectName("Body")
        bl2 = QVBoxLayout(body)
        bl2.setContentsMargins(0, 0, 0, 0)
        bl2.setSpacing(12)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # a frameless window has no resize border, so give it a size grip
        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 0, 0)
        grip_row.addStretch(1)
        grip = QSizeGrip(self)
        grip.setFixedSize(16, 16)
        grip.setObjectName("Grip")
        grip_row.addWidget(grip, 0, Qt.AlignBottom | Qt.AlignRight)
        root.addLayout(grip_row)

        # ---- status ----
        c1, l1 = card("状态")
        self.row_dev, self.val_dev = kv_row("驱动设备")
        self.row_virt, self.val_virt = kv_row("虚拟显示器")
        self.row_phys, self.val_phys = kv_row("物理显示器")
        self.row_cfg, self.val_cfg = kv_row("配置文件")
        for w in (self.row_dev, self.row_virt, self.row_phys, self.row_cfg):
            l1.addWidget(w)
        bl2.addWidget(c1)

        # ---- active mode ----
        c2, l2 = card("当前模式")
        h = QLabel("改变虚拟屏实际使用哪一个模式。只影响虚拟屏，物理屏不受影响。")
        h.setObjectName("Hint")
        h.setWordWrap(True)
        l2.addWidget(h)
        r = QHBoxLayout()
        r.setSpacing(8)
        self.cmb_mode = QComboBox()
        r.addWidget(self.cmb_mode, 1)
        self.btn_apply = QPushButton("应用")
        self.btn_apply.setObjectName("Primary")
        r.addWidget(self.btn_apply)
        l2.addLayout(r)
        bl2.addWidget(c2)

        # ---- config ----
        c3, l3 = card("配置")
        h3 = QLabel("决定驱动提供几块虚拟屏、对外提供哪些分辨率。"
                    "改动需要重载驱动才生效。")
        h3.setObjectName("Hint")
        h3.setWordWrap(True)
        l3.addWidget(h3)

        rc = QHBoxLayout()
        rc.setSpacing(8)
        rc.addWidget(QLabel("虚拟屏数量"))
        self.spn_count = QSpinBox()
        self.spn_count.setRange(1, 8)
        rc.addWidget(self.spn_count)
        self.btn_count = QPushButton("应用")
        rc.addWidget(self.btn_count)
        rc.addStretch(1)
        l3.addLayout(rc)

        self.res_box = QVBoxLayout()
        self.res_box.setSpacing(6)
        l3.addLayout(self.res_box)

        ra = QHBoxLayout()
        ra.setSpacing(6)
        self.spn_w = QSpinBox(); self.spn_w.setRange(320, 7680); self.spn_w.setValue(2560)
        self.spn_h = QSpinBox(); self.spn_h.setRange(200, 4320); self.spn_h.setValue(1440)
        self.spn_hz = QSpinBox(); self.spn_hz.setRange(24, 480); self.spn_hz.setValue(60)
        ra.addWidget(QLabel("宽"))
        ra.addWidget(self.spn_w)
        ra.addWidget(QLabel("高"))
        ra.addWidget(self.spn_h)
        ra.addWidget(QLabel("刷新"))
        ra.addWidget(self.spn_hz)
        self.btn_add_res = QPushButton("添加")
        ra.addWidget(self.btn_add_res)
        ra.addStretch(1)
        l3.addLayout(ra)

        rr = QHBoxLayout()
        self.btn_reload = QPushButton("重载驱动（需管理员）")
        self.btn_reload.setObjectName("Danger")
        rr.addWidget(self.btn_reload)
        rr.addStretch(1)
        l3.addLayout(rr)
        bl2.addWidget(c3)

        # ---- misc ----
        c4, l4 = card("其他")
        r4 = QHBoxLayout()
        r4.setSpacing(8)
        self.btn_cfgdir = QPushButton("打开配置目录")
        self.btn_projdir = QPushButton("打开项目目录")
        r4.addWidget(self.btn_cfgdir)
        r4.addWidget(self.btn_projdir)
        r4.addStretch(1)
        l4.addLayout(r4)
        bl2.addWidget(c4)

        bl2.addStretch(1)

        # ---- signals ----
        self.btn_apply.clicked.connect(self._apply_mode)
        self.btn_count.clicked.connect(self._apply_count)
        self.btn_add_res.clicked.connect(self._add_res)
        self.btn_reload.clicked.connect(self._reload)
        self.btn_cfgdir.clicked.connect(lambda: self._act(backend.open_config_dir))
        self.btn_projdir.clicked.connect(lambda: self._act(backend.open_project_dir))
        self.banner_btn.clicked.connect(self._banner_action)

    # ---------------- actions ----------------

    def _act(self, fn, *args):
        t = ActionThread(fn, *args)
        t.worker.done.connect(self._after)
        self._threads.append(t)
        t.start()

    def _after(self, res):
        if isinstance(res, dict) and res.get("error"):
            self._flash(res["error"], C["danger"])
        elif isinstance(res, dict) and res.get("out"):
            self._flash(res["out"], C["success"])
        self.reload()

    def _flash(self, text, color):
        self.pill.setText(str(text)[:40])
        self.pill.setStyleSheet(
            "QLabel#Pill { font-size:11px; font-weight:600; padding:2px 10px;"
            "border-radius:9px; color:%s; background-color:#1e232c; }" % color)

    def _apply_mode(self):
        data = self.cmb_mode.currentData()
        if data:
            self._act(backend.set_mode, data[0], data[1], data[2])

    def _apply_count(self):
        self._act(backend.set_count, self.spn_count.value())

    def _add_res(self):
        self._act(backend.add_resolution, self.spn_w.value(),
                  self.spn_h.value(), self.spn_hz.value())

    def _remove_res(self, m):
        self._act(backend.remove_resolution, m[0], m[1], m[2])

    def _need_admin(self, fn, *args):
        """Run an admin action, elevating the whole panel if needed."""
        if not backend.is_admin():
            if not backend.elevate_and_rerun():
                self._flash("已取消管理员授权", C["warning"])
            return
        self._act(fn, *args)

    def _reload(self):
        self._need_admin(backend.reload_driver)

    def _banner_action(self):
        mode = self._st.get("_banner_mode")
        if mode == "install":
            self._act(backend.start_install)
        elif mode == "reload":
            self._need_admin(backend.reload_driver)

    # ---------------- refresh ----------------

    def reload(self):
        s = backend.status()
        self._st = s

        if not s.get("available"):
            self.dot.set_state(False, C["danger"])
            self._flash("核心模块不可用", C["danger"])
            self._show_banner("load_error",
                              "无法载入 vdd_core.py：%s\n"
                              "检查 C:\\VirtualDisplay\\vdd_core.py 是否存在。"
                              % s.get("error", ""), None)
            for v in (self.val_dev, self.val_virt, self.val_phys, self.val_cfg):
                v.setText("—")
            self.cmb_mode.clear()
            return

        installed = s.get("device_installed")
        vd = s.get("virtual")
        cfg = s.get("config")

        self.val_dev.setText("已安装" if installed else "未安装")
        self.val_dev.setStyleSheet("font-size:11.5px;font-weight:600;color:%s;"
                                   % (C["success"] if installed else C["danger"]))

        if vd:
            self.val_virt.setText("%s · %dx%d @ %dHz"
                                  % (friendly_device(vd["device"]),
                                     vd["width"], vd["height"], vd["hz"]))
            self.val_virt.setStyleSheet("font-size:11.5px;font-weight:600;color:%s;"
                                        % C["success"])
        else:
            self.val_virt.setText("无")
            self.val_virt.setStyleSheet("font-size:11.5px;font-weight:600;color:%s;"
                                        % C["warning"])

        phys = [d for d in s.get("displays", []) if not d["virtual"] and d["attached"]]
        if phys:
            p = phys[0]
            self.val_phys.setText("%dx%d @ %dHz" % (p["width"], p["height"], p["hz"]))
            self.val_phys.setStyleSheet("font-size:11.5px;color:%s;" % C["text"])
        else:
            self.val_phys.setText("—")

        if cfg:
            self.val_cfg.setText("count=%d · %d 个分辨率"
                                 % (cfg["count"], len(cfg["resolutions"])))
            self.val_cfg.setStyleSheet("font-size:11.5px;color:%s;" % C["text"])
        else:
            self.val_cfg.setText(s.get("config_error") or "—")
            self.val_cfg.setStyleSheet("font-size:11.5px;color:%s;" % C["danger"])

        # pill + banner
        if not installed:
            self.dot.set_state(False, C["danger"])
            self._flash("驱动未安装", C["danger"])
            self._show_banner("install",
                              "没有检测到 MttVDD 虚拟显示驱动。点右侧按钮运行安装脚本"
                              "（会弹 UAC，需要管理员）。", "安装驱动")
        elif not vd:
            self.dot.set_state(False, C["warning"])
            self._flash("未挂载", C["warning"])
            self._show_banner("reload",
                              "驱动已安装但没有检测到虚拟显示器。"
                              "若刚改过配置，点右侧按钮重载驱动。", "重载驱动")
        elif cfg and cfg["count"] != s.get("virtual_count", 0):
            self.dot.set_state(True, C["warning"])
            self._flash("配置待生效", C["warning"])
            self._show_banner("reload",
                              "配置要求 %d 块虚拟屏，实际 %d 块 —— 点右侧按钮重载驱动。"
                              % (cfg["count"], s.get("virtual_count", 0)), "重载驱动")
        else:
            self.dot.set_state(True, C["success"])
            self._flash("运行中", C["success"])
            self.banner.setVisible(False)
            self._st["_banner_mode"] = None

        # mode combo
        self.cmb_mode.blockSignals(True)
        self.cmb_mode.clear()
        cur = (vd["width"], vd["height"], vd["hz"]) if vd else None
        for m in s.get("modes", []):
            self.cmb_mode.addItem("%dx%d @ %dHz" % m, m)
        if cur:
            for i in range(self.cmb_mode.count()):
                if self.cmb_mode.itemData(i) == cur:
                    self.cmb_mode.setCurrentIndex(i)
                    break
        self.cmb_mode.setEnabled(bool(s.get("modes")))
        self.cmb_mode.blockSignals(False)
        self.btn_apply.setEnabled(bool(s.get("modes")))

        if cfg:
            self.spn_count.blockSignals(True)
            self.spn_count.setValue(cfg["count"])
            self.spn_count.blockSignals(False)
            self._rebuild_res_rows(cfg["resolutions"])

    def _show_banner(self, mode, text, btn_label):
        self._st["_banner_mode"] = mode
        self.banner_text.setText(text)
        self.banner_btn.setText(btn_label or "")
        self.banner_btn.setVisible(bool(btn_label))
        self.banner.setVisible(True)

    def _rebuild_res_rows(self, resolutions):
        while self.res_box.count():
            item = self.res_box.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        vd = self._st.get("virtual") or {}
        current = (vd.get("width"), vd.get("height"), vd.get("hz"))

        for m in resolutions:
            row = QWidget()
            row.setObjectName("Row")
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(8)
            lab = QLabel("%dx%d @ %dHz" % m)
            lab.setObjectName("Value")
            h.addWidget(lab)
            if m == current:
                badge = QLabel("使用中")
                badge.setObjectName("Badge")
                h.addWidget(badge)
            h.addStretch(1)
            btn = QPushButton("移除")
            btn.setObjectName("MiniDanger")
            btn.setEnabled(len(resolutions) > 1)
            btn.clicked.connect(lambda _=False, mm=m: self._remove_res(mm))
            h.addWidget(btn)
            self.res_box.addWidget(row)


# --------------------------------------------------------------------------- #
# selftest
# --------------------------------------------------------------------------- #

def selftest():
    import time
    print("=== VirtualDisplay panel selftest %s ===" % time.strftime("%Y-%m-%d %H:%M:%S"))
    print("core available :", backend.core_available())
    if not backend.core_available():
        print("  ERROR:", backend.CORE_ERROR)

    s = backend.status()
    if s.get("available"):
        print("device installed:", s["device_installed"])
        print("virtual count   :", s["virtual_count"])
        vd = s.get("virtual")
        print("virtual display :",
              "%s %dx%d@%d" % (vd["device"], vd["width"], vd["height"], vd["hz"])
              if vd else None)
        print("modes offered   :", len(s.get("modes", [])))
        cfg = s.get("config")
        print("config count    :", cfg["count"] if cfg else None)
        print("config error    :", s.get("config_error") or "(none)")
    else:
        print("status error    :", s.get("error"))

    print("\n-- backend callables --")
    for name in ("status", "modes", "set_mode", "set_count", "add_resolution",
                 "remove_resolution", "reload_driver", "open_config_dir",
                 "open_project_dir", "start_install", "is_admin"):
        print("  %-18s %s" % (name, callable(getattr(backend, name, None))))

    print("\n-- ui import --")
    ui_ok = False
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        w = Main()
        print("  Main() constructed OK, %dx%d" % (w.width(), w.height()))
        print("  mode combo items:", w.cmb_mode.count())
        print("  banner present  :", hasattr(w, "banner"))
        ui_ok = True
    except Exception as exc:                                   # noqa: BLE001
        print("  UI FAIL:", exc)

    print("\nRESULT =", "OK" if ui_ok else "FAIL")
    print("DRIVER =",
          "installed, %d virtual display(s)" % s.get("virtual_count", 0)
          if s.get("available") and s.get("device_installed")
          else "not installed / not reachable")
    return 0 if ui_ok else 1


def main():
    if "--selftest" in sys.argv:
        return selftest()
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    w = Main()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
