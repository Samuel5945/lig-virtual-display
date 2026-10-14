"""
VirtualDisplay panel - modern Qt6 UI for the MttVDD virtual display.

Dark, card-based. Every action goes through backend.py, which imports
vdd_core.py from the project root - the panel holds no logic of its own.

    VirtualDisplayPanel.exe              open the panel
    VirtualDisplayPanel.exe --selftest   headless check, prints a report
"""

import os
import sys

from PySide6.QtCore import (QThread, QTimer, QEvent, QPropertyAnimation,
                            QEasingCurve, Qt, Signal, QObject)
from PySide6.QtGui import QColor, QPainter, QBrush, QPen
from PySide6.QtCore import QRectF, QPointF
from PySide6.QtWidgets import QAbstractButton
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QComboBox, QSpinBox, QScrollArea, QSizeGrip, QMessageBox,
)

import backend

APP_NAME = "VirtualDisplay"


def _resource(name):
    """Locate a bundled asset.

    In a PyInstaller onefile build the payload is unpacked to sys._MEIPASS;
    running from source it sits next to this file (or in ../gui for the ico).
    """
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name).replace("\\", "/")


_APP_ICON = None


def app_icon():
    """The application icon, for the taskbar / Alt-Tab.

    Without an explicit window icon a Qt window falls back to whatever the
    loader provides, and a frameless window frequently ends up with none at
    all - which is how the panel lost its taskbar icon.
    """
    global _APP_ICON
    if _APP_ICON is None:
        from PySide6.QtGui import QIcon
        for cand in (_resource("app.ico"),
                     os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "gui", "app.ico")):
            if os.path.exists(cand):
                _APP_ICON = QIcon(cand)
                break
        if _APP_ICON is None:
            _APP_ICON = QIcon()
    return _APP_ICON


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
QDialog, QMessageBox { background-color: %(bg)s; }
QMessageBox QLabel, QDialog QLabel { color: %(text)s; background: transparent; }
QMessageBox QPushButton, QDialog QPushButton { color: %(text)s; }

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
QPushButton#Seg {
    padding: 5px 12px; min-width: 0; font-size: 11.5px;
    background-color: #1c212a; border: 1px solid %(border)s; color: %(muted)s;
}
QPushButton#Seg:hover { background-color: #232935; color: %(text)s; }
QPushButton#Seg[active="true"] {
    background-color: %(accent_dim)s; border-color: %(accent)s;
    color: #eafffb; font-weight: 600;
}
QPushButton#SegDanger[active="true"] {
    background-color: #5a2424; border-color: %(danger)s; color: #ffe4e4; font-weight: 600;
}
QLabel#Warn { font-size: 11px; color: %(warning)s; }

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
/* Native drop-down paints its own block behind the arrow, which looks like a
   stray button on our flat dark field. Styling ::drop-down suppresses that
   block AND the native arrow, so the arrow is drawn by the Chevron overlay
   instead (see Chevron). */
QComboBox::drop-down {
    background: transparent;
    border: none;
    width: 26px;
}
QComboBox::down-arrow { image: none; }
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


class GlyphButton(QAbstractButton):
    """A window control that paints its own fill and glyph.

    The QSS version had two problems. The stylesheet's min-width/padding shrank
    the button to 12px wide while it stayed 26px tall, so once the hover fill
    appeared it read as a stray vertical red pill instead of a window control;
    and the fill switched on/off instantly, which looked like a glitch rather
    than a hover. This draws a properly sized rounded square and fades the fill
    in over ~130ms, and the glyphs are vector lines rather than text characters
    so the stroke weight is even.
    """

    W, H, RADIUS = 34, 26, 6

    def __init__(self, kind, parent=None, danger=False):
        super().__init__(parent)
        self._kind = kind            # "min" | "close" | "max"
        self._danger = danger
        self._t = 0.0                # 0 = idle, 1 = fully hovered
        self.setFixedSize(self.W, self.H)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip({"min": "最小化", "close": "关闭", "max": "最大化"}.get(kind, ""))
        # paint everything ourselves; keep QSS out of the way
        self.setStyleSheet("background: transparent; border: none; padding: 0;")
        self._anim = QPropertyAnimation(self, b"hoverT", self)
        self._anim.setDuration(130)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def get_hoverT(self):
        return self._t

    def set_hoverT(self, v):
        self._t = float(v)
        self.update()

    hoverT = property(get_hoverT, set_hoverT)

    def _to(self, target):
        self._anim.stop()
        self._anim.setStartValue(self._t)
        self._anim.setEndValue(float(target))
        self._anim.start()

    def enterEvent(self, ev):
        self._to(1.0)
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self._to(0.0)
        super().leaveEvent(ev)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        if self._t > 0.01:
            fill = QColor("#c0392b") if self._danger else QColor("#2c3340")
            fill.setAlphaF(self._t * (0.90 if self._danger else 0.85))
            p.setPen(Qt.NoPen)
            p.setBrush(fill)
            p.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2),
                              self.RADIUS, self.RADIUS)

        # glyph: muted -> text colour, or white on a red hover
        if self._danger and self._t > 0.45:
            col = QColor("#ffffff")
        else:
            a, b = QColor(C["muted"]), QColor(C["text"])
            k = self._t
            col = QColor(int(a.red() + (b.red() - a.red()) * k),
                         int(a.green() + (b.green() - a.green()) * k),
                         int(a.blue() + (b.blue() - a.blue()) * k))
        pen = QPen(col, 1.6)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)

        cx, cy = self.width() / 2.0, self.height() / 2.0
        if self._kind == "min":
            p.drawLine(QPointF(cx - 5, cy), QPointF(cx + 5, cy))
        elif self._kind == "close":
            p.drawLine(QPointF(cx - 4.5, cy - 4.5), QPointF(cx + 4.5, cy + 4.5))
            p.drawLine(QPointF(cx + 4.5, cy - 4.5), QPointF(cx - 4.5, cy + 4.5))
        elif self._kind == "max":
            p.drawRect(QRectF(cx - 4.5, cy - 4.5, 9, 9))
        p.end()


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

        for kind, slot in (("min", self._on_min), ("close", self._on_close)):
            b = GlyphButton(kind, self, danger=(kind == "close"))
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


class Chevron(QLabel):
    """Chevron drawn as a transparent overlay on a QComboBox.

    Qt cannot give us both "no block behind the arrow" and "a native arrow
    that looks right". Styling ::drop-down removes the block but also
    suppresses the native arrow, and putting an image on ::down-arrow
    produced a second chevron. So the native arrow is disabled and this label
    paints the chevron on top. It ignores mouse events so clicks still open
    the popup.
    """

    W, H, RIGHT = 22, 18, 7

    def __init__(self, combo, colour=None):
        super().__init__(combo)
        self._combo = combo
        self.setText("\u25be")          # small solid down triangle
        self.setAlignment(Qt.AlignCenter)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setStyleSheet(
            "color: %s; background: transparent; font-size: 11px;"
            % (colour or C["muted"]))
        combo.installEventFilter(self)
        self._place()

    def _place(self):
        self.setGeometry(self._combo.width() - self.W - self.RIGHT,
                         (self._combo.height() - self.H) // 2,
                         self.W, self.H)

    def eventFilter(self, obj, ev):
        if obj is self._combo and ev.type() == QEvent.Resize:
            self._place()
        return False


def apply_dark_palette(app):
    """Give Qt a dark palette.

    QSS alone is not enough. Widgets that render through their palette keep the
    system colours, and this machine's are the light defaults: Text/WindowText
    #000000 and Highlight #779c48 (the Windows accent). That is why the
    QSpinBox numbers showed up black despite `QSpinBox { color: ... }` in the
    stylesheet, and why the combo drop-down highlighted items in green.
    """
    from PySide6.QtGui import QPalette
    p = QPalette()
    p.setColor(QPalette.Window, QColor(C["bg"]))
    p.setColor(QPalette.WindowText, QColor(C["text"]))
    p.setColor(QPalette.Base, QColor("#1f242e"))
    p.setColor(QPalette.AlternateBase, QColor(C["card"]))
    p.setColor(QPalette.Text, QColor(C["text"]))
    p.setColor(QPalette.Button, QColor("#1f242e"))
    p.setColor(QPalette.ButtonText, QColor(C["text"]))
    p.setColor(QPalette.BrightText, QColor("#ffffff"))
    p.setColor(QPalette.ToolTipBase, QColor("#1f242e"))
    p.setColor(QPalette.ToolTipText, QColor(C["text"]))
    p.setColor(QPalette.Highlight, QColor(C["accent_dim"]))
    p.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.Link, QColor(C["accent"]))
    for role in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText):
        p.setColor(QPalette.Disabled, role, QColor(C["faint"]))
    app.setPalette(p)


def force_taskbar_button(widget):
    """Make sure a frameless window keeps its taskbar button.

    Qt.Window | Qt.FramelessWindowHint usually keeps it, but Windows can drop
    the window from the taskbar anyway unless WS_EX_APPWINDOW is set on the
    native style. Cheap and idempotent.
    """
    try:
        import ctypes
        GWL_EXSTYLE = -16
        WS_EX_APPWINDOW = 0x00040000
        WS_EX_TOOLWINDOW = 0x00000080
        user32 = ctypes.windll.user32
        hwnd = int(widget.winId())
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                              (style | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW)
    except Exception:                                          # noqa: BLE001
        pass


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


class ConfirmDialog(QWidget):
    """Frameless dark confirm dialog with an Ok/Cancel pair.

    QMessageBox was not usable here. Measured on this machine: its body renders
    #ffffff / #f0f0f0 while the app palette's Window is #0f1115 - the native
    style paints the dialog background itself and ignores the palette - and it
    keeps the OS accent-coloured title bar, which is the exact green frame the
    rest of the UI went frameless to avoid. It also labels its buttons "Yes"/"No"
    in English. Drawing our own keeps everything consistent.
    """

    def __init__(self, parent, title, message, ok_text="确定",
                 cancel_text="取消", on_ok=None, danger=True):
        super().__init__(parent)
        self._on_ok = on_ok
        self.setObjectName("Root")
        self.setWindowTitle(title)
        self.setWindowIcon(app_icon())
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setWindowModality(Qt.ApplicationModal)
        self.setMinimumWidth(430)
        self._drag = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(1, 1, 1, 1)
        lay.setSpacing(0)

        # header: same look as the main title bar, but no minimise button
        head = QWidget()
        head.setObjectName("TitleBar")
        head.setAttribute(Qt.WA_StyledBackground, True)
        head.setFixedHeight(38)
        h = QHBoxLayout(head)
        h.setContentsMargins(14, 0, 8, 0)
        h.setSpacing(8)
        name = QLabel(title)
        name.setObjectName("TitleText")
        h.addWidget(name)
        h.addStretch(1)
        close = GlyphButton("close", head, danger=True)
        close.clicked.connect(self.reject)
        h.addWidget(close)
        head.mousePressEvent = self._head_press
        head.mouseMoveEvent = self._head_move
        head.mouseReleaseEvent = self._head_release
        lay.addWidget(head)

        body = QWidget()
        body.setObjectName("Body")
        b = QHBoxLayout(body)
        b.setContentsMargins(22, 20, 22, 16)
        b.setSpacing(14)
        mark = QLabel("\u26a0")            # warning triangle
        mark.setStyleSheet(
            "font-size:26px; color:%s; background:transparent;"
            % (C["warning"] if danger else C["accent"]))
        b.addWidget(mark, 0, Qt.AlignTop)
        msg = QLabel(message)
        msg.setWordWrap(True)
        msg.setObjectName("DialogText")
        msg.setStyleSheet(
            "font-size:12px; color:%s; background:transparent; line-height:150%%;"
            % C["text"])
        b.addWidget(msg, 1)
        lay.addWidget(body)

        foot = QWidget()
        foot.setObjectName("Body")
        f = QHBoxLayout(foot)
        f.setContentsMargins(22, 6, 22, 18)
        f.setSpacing(10)
        f.addStretch(1)
        cancel = QPushButton(cancel_text)
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        f.addWidget(cancel)
        ok = QPushButton(ok_text)
        ok.setObjectName("Danger" if danger else "Primary")
        ok.setCursor(Qt.PointingHandCursor)
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        f.addWidget(ok)
        lay.addWidget(foot)

        self.adjustSize()

    def _accept(self):
        self.close()
        if self._on_ok:
            self._on_ok()

    def reject(self):
        self.close()

    # dragging, mirroring the main window's title bar
    def _head_press(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag = (ev.globalPosition().toPoint()
                          - self.frameGeometry().topLeft())

    def _head_move(self, ev):
        if self._drag is not None and ev.buttons() & Qt.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._drag)

    def _head_release(self, ev):
        self._drag = None

    def showEvent(self, ev):
        super().showEvent(ev)
        # centre on the parent window
        par = self.parent()
        if par is not None:
            g = par.frameGeometry()
            self.move(g.center().x() - self.width() // 2,
                      g.center().y() - self.height() // 2)
        dark_chrome(self)


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
        self.setWindowIcon(app_icon())
        # frameless: the native frame cannot be darkened on Windows 10, so we
        # draw our own title bar (see TitleBar)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setMinimumWidth(620)
        self.setMinimumHeight(720)
        self._threads = []
        self._st = {}
        self._build()
        self.reload()

        # Windows' own display settings can be changed at any time; without a
        # poll the panel silently shows stale values (that is exactly how the
        # first round of this bug was reported).
        self._poll = QTimer(self)
        self._poll.setInterval(3000)
        self._poll.timeout.connect(self._refresh_quiet)
        self._poll.start()

    def showEvent(self, ev):
        super().showEvent(ev)
        # rounded corners where the OS supports it (Win11); harmless elsewhere
        dark_chrome(self)
        # a frameless window must opt in explicitly, or the taskbar entry
        # disappears along with the frame
        force_taskbar_button(self)

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
        sub = QLabel("虚拟显示器 · MttVDD" +
                             (" · " + backend.ROOT if backend.HAS_PROJECT else "（共享副本）"))
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

        # ---- display layout (multi-monitor) ----
        c5, l5 = card("显示器布局（多显示器）")
        self.lbl_layout_hint = QLabel("")
        self.lbl_layout_hint.setObjectName("Hint")
        self.lbl_layout_hint.setWordWrap(True)
        l5.addWidget(self.lbl_layout_hint)

        def seg_row(title, items, handler):
            wrap = QWidget(); wrap.setObjectName("Row")
            h = QHBoxLayout(wrap)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(6)
            lab = QLabel(title); lab.setObjectName("Key")
            lab.setMinimumWidth(74)
            h.addWidget(lab)
            btns = {}
            for key, text, danger in items:
                b = QPushButton(text)
                b.setObjectName("SegDanger" if danger else "Seg")
                b.setMinimumWidth(0)
                b.clicked.connect(lambda _=False, k=key: handler(k))
                h.addWidget(b)
                btns[key] = b
            h.addStretch(1)
            l5.addWidget(wrap)
            return btns

        self.topo_btns = seg_row(
            "显示模式",
            [("extend", "扩展", False),
             ("virtual", "仅虚拟屏", True),
             ("physical", "仅物理屏", False),
             ("clone", "复制", False)],
            self._set_topo)
        self.pos_btns = seg_row(
            "虚拟屏位置",
            [("left", "在左侧", False), ("right", "在右侧", False),
             ("above", "在上方", False), ("below", "在下方", False)],
            self._place)
        self.prim_btns = seg_row(
            "主显示器",
            [("physical", "物理屏", False), ("virtual", "虚拟屏", False)],
            self._make_primary)
        bl2.addWidget(c5)

        # ---- active mode ----
        c2, l2 = card("虚拟屏分辨率（现在用哪个）")
        self.lbl_mode_hint = QLabel(
            "从驱动提供的模式里选一个，虚拟屏立即切过去，不需要重载驱动。\n"
            "只影响虚拟屏，物理显示器不受影响。")
        self.lbl_mode_hint.setObjectName("Hint")
        self.lbl_mode_hint.setWordWrap(True)
        l2.addWidget(self.lbl_mode_hint)
        r = QHBoxLayout()
        r.setSpacing(8)
        self.cmb_mode = QComboBox()
        self.cmb_mode.setMinimumWidth(180)
        Chevron(self.cmb_mode)
        r.addWidget(self.cmb_mode, 1)
        self.btn_apply = QPushButton("应用")
        self.btn_apply.setObjectName("Primary")
        r.addWidget(self.btn_apply)
        l2.addLayout(r)
        bl2.addWidget(c2)

        # ---- config ----
        c3, l3 = card("驱动配置（驱动提供什么）")
        self.lbl_cfg_hint = QLabel("")
        self.lbl_cfg_hint.setObjectName("Hint")
        self.lbl_cfg_hint.setWordWrap(True)
        l3.addWidget(self.lbl_cfg_hint)

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
        self.btn_reload = QPushButton("重载驱动，让上面的改动生效")
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

    def _set_topo(self, key):
        # "only the virtual display" switches the physical monitor off - if the
        # user is reading this panel on that monitor their screen goes black,
        # so make them confirm rather than surprising them.
        if key == "virtual":
            ConfirmDialog(
                self,
                "确认关闭物理显示器",
                "「仅虚拟屏」会把物理显示器关掉。\n\n"
                "如果你的屏幕现在显示着这个面板，它会立刻变黑。\n"
                "恢复方法：按 Win+P 循环切换显示模式。",
                ok_text="仍然切换", cancel_text="取消",
                on_ok=lambda: self._act(backend.set_topology, key),
            ).show()
            return
        self._act(backend.set_topology, key)

    def _place(self, side):
        self._act(backend.place_beside, side)

    def _make_primary(self, which):
        self._act(backend.make_primary, which)

    def _reload(self):
        self._need_admin(backend.reload_driver)

    def _banner_action(self):
        mode = self._st.get("_banner_mode")
        if mode == "install":
            self._act(backend.start_install)
        elif mode == "reload":
            self._need_admin(backend.reload_driver)
        elif mode == "config":
            # writing into the driver's config dir needs admin; run the panel
            # elevated rather than failing with a permission error
            self._need_admin(backend.create_default_config)

    # ---------------- refresh ----------------

    def _refresh_quiet(self):
        """Poll in the background and only touch the UI if something moved."""
        try:
            s = backend.status(light=True)
        except Exception:                                      # noqa: BLE001
            return
        if not s.get("available"):
            return
        sig = (s.get("topology"),
               (s["virtual"] or {}).get("device"),
               (s["virtual"] or {}).get("width"),
               (s["virtual"] or {}).get("height"),
               (s["virtual"] or {}).get("hz"),
               (s["physical"] or {}).get("width"),
               (s["physical"] or {}).get("height"),
               (s["physical"] or {}).get("hz"),
               tuple(sorted((s.get("scaling") or {}).items())),
               len(s.get("modes") or []),
               (s.get("config") or {}).get("count"),
               bool((s["virtual"] or {}).get("primary") if s.get("virtual") else None))
        if sig == getattr(self, "_last_sig", None):
            return
        self._last_sig = sig
        self._apply_status(s)

    def reload(self):
        s = backend.status()
        self._st = s
        self._apply_status(s)

    def _apply_status(self, s):
        self._st = s

        if not s.get("available"):
            self.dot.set_state(False, C["danger"])
            self._flash("核心模块不可用", C["danger"])
            self._show_banner("load_error",
                              "无法载入 vdd_core.py：%s" % s.get("error", ""), None)
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

        scaling = s.get("scaling") or {}

        if vd:
            txt = "%s · %dx%d @ %dHz" % (friendly_device(vd["device"]),
                                         vd["width"], vd["height"], vd["hz"])
            if scaling.get(vd["device"]):
                txt += " · 缩放 %d%%" % scaling[vd["device"]]
            self.val_virt.setText(txt)
            self.val_virt.setStyleSheet("font-size:11.5px;font-weight:600;color:%s;"
                                        % C["success"])
        else:
            self.val_virt.setText("无")
            self.val_virt.setStyleSheet("font-size:11.5px;font-weight:600;color:%s;"
                                        % C["warning"])

        phys = [d for d in s.get("displays", []) if not d["virtual"] and d["attached"]]
        if phys:
            p = phys[0]
            ptxt = "%dx%d @ %dHz" % (p["width"], p["height"], p["hz"])
            if scaling.get(p["device"]):
                ptxt += " · 缩放 %d%%" % scaling[p["device"]]
            self.val_phys.setText(ptxt)
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
        elif s.get("config_error"):
            self.dot.set_state(False, C["warning"])
            self._flash("配置缺失", C["warning"])
            self._show_banner("config",
                              "驱动的配置文件不存在（%s）。\n"
                              "点右侧按钮写入一份默认配置（1 块屏、2560x1440/1080p/4K、60/120/144Hz），"
                              "然后重载驱动。"
                              % (s.get("config_error") or ""), "创建默认配置")
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

        # keep both hints honest about the live state, so the two cards are
        # self-explanatory instead of leaving the user to work out which one
        # needs a driver reload and which takes effect immediately
        if s.get("modes"):
            self.lbl_mode_hint.setText(
                "\u3000\u3000从下面 %d 个模式里挑一个，虚拟屏立即切过去，"
                "不需要重载驱动，也不影响物理显示器。" % len(s["modes"]))
        else:
            self.lbl_mode_hint.setText(
                "\u3000\u3000驱动已安装但没检测到虚拟屏，暂时没有可选模式。"
                "先到下面的「驱动配置」确认设置，再重载驱动。")

        if cfg:
            self.spn_count.blockSignals(True)
            self.spn_count.setValue(cfg["count"])
            self.spn_count.blockSignals(False)
            self._rebuild_res_rows(cfg["resolutions"])

            actual = s.get("virtual_count", 0)
            if cfg["count"] != actual:
                self.lbl_cfg_hint.setText(
                    "\u3000\u3000改动还没生效：配置里是 %d 块虚拟屏，实际有 %d 块。"
                    "点下面对应的按钮重载驱动。" % (cfg["count"], actual))
                self.lbl_cfg_hint.setStyleSheet(
                    "font-size:11px;color:%s;font-weight:600;" % C["warning"])
            else:
                self.lbl_cfg_hint.setText(
                    "\u3000\u3000决定驱动提供几块虚拟屏、以及可选哪些分辨率。"
                    "这里的改动不会立即生效，改完必须重载驱动。")
                self.lbl_cfg_hint.setStyleSheet(
                    "font-size:11px;color:%s;" % C["muted"])
        else:
            self.lbl_cfg_hint.setText(
                "\u3000\u3000读不到配置文件：%s" % (s.get("config_error") or "未知原因"))
            self.lbl_cfg_hint.setStyleSheet(
                "font-size:11px;color:%s;" % C["danger"])

        self._apply_layout(s, vd, phys)

    def _apply_layout(self, s, vd, phys):
        """Reflect the live multi-monitor state on the layout card."""
        topo = s.get("topology")
        labels = s.get("topology_labels") or {}
        valid = s.get("topology_valid") or {}

        def mark(btn, active):
            if btn.property("active") != active:
                btn.setProperty("active", active)
                btn.style().unpolish(btn)
                btn.style().polish(btn)

        for key, b in self.topo_btns.items():
            mark(b, key == topo)
            b.setEnabled(bool(valid.get(key, True)))

        vd_primary = bool(vd and vd.get("primary"))
        for key, b in self.prim_btns.items():
            mark(b, (key == "virtual" and vd_primary) or
                    (key == "physical" and not vd_primary))
            b.setEnabled(bool(vd) and bool(phys))

        # position only means something while both screens are on
        for b in self.pos_btns.values():
            b.setEnabled(topo == "extend" and bool(vd) and bool(phys))

        cur = labels.get(topo, "未知")
        if topo == "virtual":
            hint = ("当前：%s —— 物理屏已关闭。按 Win+P 或点上面的「扩展」可以恢复。"
                    % cur)
        else:
            hint = ("当前：%s。这里改的就是 Windows 自己的显示模式，"
                    "跟系统设置里的「多显示器」是同一处，两边会同步。" % cur)
        if topo == "clone":
            hint += "复制模式下两块屏必须用同一分辨率。"
        self.lbl_layout_hint.setText(hint)
        self.lbl_layout_hint.setStyleSheet(
            "font-size:11px;color:%s;font-weight:600;"
            % (C["warning"] if topo == "virtual" else C["muted"]))

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
        apply_dark_palette(app)
        app.setStyleSheet(STYLE)
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
    apply_dark_palette(app)
    app.setStyleSheet(STYLE)
    w = Main()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
