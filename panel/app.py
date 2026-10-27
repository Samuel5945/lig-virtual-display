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
from PySide6.QtGui import QColor, QPainter, QBrush, QPen, QFont, QFontMetrics
from PySide6.QtCore import QRectF, QPointF
from PySide6.QtWidgets import QAbstractButton
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QComboBox, QSpinBox, QScrollArea, QSizeGrip,
    QMessageBox,
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
QPushButton:focus   { border-color: %(accent)s; }
QPushButton:disabled{ color: %(faint)s; border-color: #22262f; background-color: #191d24; }

QPushButton#Primary { background-color: %(accent)s; border: 1px solid %(accent)s;
                      color: #06231f; font-weight: 600; }
QPushButton#Primary:hover   { background-color: #65ded3; border-color: #65ded3; }
QPushButton#Primary:disabled{ background-color: #23343a; border-color: #23343a; color: #4a5a60; }

/* the accent-filled twin of #Compact, for a row's primary action */
QPushButton#PrimaryCompact { background-color: %(accent)s; border: 1px solid %(accent)s;
                             color: #06231f; font-weight: 600; padding: 6px 12px;
                             min-width: 0; font-size: 11.5px; }
QPushButton#PrimaryCompact:hover { background-color: #65ded3; border-color: #65ded3; }
QPushButton#PrimaryCompact:disabled { background-color: #23343a; border-color: #23343a; color: #4a5a60; }

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

/* a button that sits inside a settings row: as wide as its word, not 64px */
QPushButton#Compact { padding: 6px 12px; min-width: 0; font-size: 11.5px; }

QComboBox {
    background-color: #1f242e; border: 1px solid %(border)s; border-radius: 8px;
    color: %(text)s; padding: 6px 10px; min-width: 0; font-size: 12px;
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
/* width is per-use, not global: a stretching combo box was both ugly and why
   the 应用 button fell off the right edge at the default 620px window */
QComboBox#Mode  { min-width: 168px; max-width: 170px; }
QComboBox#Res   { min-width: 130px; max-width: 130px; }
QComboBox#Scale { min-width: 56px;  max-width: 56px; }
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


class WheelNeedsFocus(QObject):
    """Make the mouse wheel change a value only after you click the control.

    Qt 6 gives QComboBox and QSpinBox a wheel handler with no focus check, so
    a wheel that merely passes over one of them while you scroll the page
    re-picks the resolution behind your back (measured on this machine: one
    notch over an unfocused combo moved it 3 -> 6).

    Two parts, and both are load-bearing:

    * `Qt::WheelFocus` is what hands the control focus *before* the event
      filters run, so a filter that only checks `hasFocus()` would always see
      it armed. Dropping the bit to StrongFocus stops that. On its own the
      policy change is not enough - measured, the value still moved.
    * the filter then blocks the wheel until the control really has keyboard
      focus, i.e. until it has been clicked. Ignoring rather than eating the
      event lets it reach the scroll area, so the page still scrolls under the
      cursor while the control stays put.

    Qt does not own event filters, so the wrapper is parked on the widget too:
    a filter whose Python side is collected stops running, silently.
    """

    def __init__(self, widget):
        super().__init__(widget)
        widget.setFocusPolicy(Qt.StrongFocus)
        widget._wheel_guard = self
        widget.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Wheel and not obj.hasFocus():
            ev.ignore()                                   # let the page scroll
            return True                                   # but not this control
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
    """Make the taskbar button behave for a frameless window.

    Two separate things have to be forced, because Qt's
    ``Qt.Window | Qt.FramelessWindowHint`` drops both:

    * ``WS_EX_APPWINDOW`` - without it Windows can drop the window from the
      taskbar entirely once the frame goes away.
    * ``WS_MINIMIZEBOX`` (+ ``WS_SYSMENU``) - this is what makes **clicking the
      taskbar button collapse the window**. The shell only minimises the
      foreground window on a taskbar click when that window *can* be minimised,
      and it decides by looking at these style bits; measured on this box the
      frameless window had neither, so the click did nothing. They do not bring
      back a title bar - that is ``WS_CAPTION``, which stays off.

    ``WS_THICKFRAME`` is set on purpose and not a leftover: the old version of
    this function wrote its ex-style into ``GWL_STYLE`` (``-16`` is the style,
    ``-20`` the ex-style), and the value it OR-ed in - 0x00040000 - happens to
    *be* WS_THICKFRAME. So every window this app ever shipped with had it, and
    edge-drag resize plus the QSizeGrip quietly relied on that. Fixing the index
    without adding the bit back would have taken resizing away.
    """
    try:
        import ctypes
        GWL_STYLE, GWL_EXSTYLE = -16, -20
        WS_MINIMIZEBOX = 0x00020000
        WS_SYSMENU = 0x00080000
        WS_THICKFRAME = 0x00040000
        WS_EX_APPWINDOW = 0x00040000
        WS_EX_TOOLWINDOW = 0x00000080
        user32 = ctypes.windll.user32
        hwnd = int(widget.winId())
        ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                              (ex | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW)
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        user32.SetWindowLongW(hwnd, GWL_STYLE, style | WS_MINIMIZEBOX
                              | WS_SYSMENU | WS_THICKFRAME)
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
# display schematic
# --------------------------------------------------------------------------- #

RES_TAGS = {(3840, 2160): "4K", (2560, 1440): "2.5K", (1920, 1080): "FHD",
            (2560, 1600): "2.5K宽", (2160, 1440): "3:2", (1080, 2400): "竖屏"}


def res_tag(w, h):
    """Short resolution tag, only ever shown when the full one cannot fit."""
    return RES_TAGS.get((w, h), "%dx%d" % (w, h))


class DisplayMap(QWidget):
    """What is plugged in, drawn from Windows' own coordinates.

    Why this exists: 「虚拟屏位置」 was four identical buttons. The refresh code
    only ever called setEnabled() on them and never mark(), so nothing lit up to
    say which side the virtual screen was actually on, and the card could not
    answer "手机看到的是物理屏还是虚拟屏". A layout is a fact about the desktop,
    so draw the fact: position and size of every rect come straight from
    EnumDisplaySettings. A click on one side of the reference screen moves the
    virtual display there through the same handler the buttons use.

    The big number in each box is the number Windows' own 「标识」 paints on
    that screen (vdd_core.list_displays numbers them the same way), so the two
    pictures can be read side by side. Virtual boxes can also be dragged: the
    drag preview snaps to the neighbours' edges and centres, and on release the
    new position is written back with ChangeDisplaySettingsEx. Physical boxes
    are read-only - their real position is where the desk is, and a stray drag
    must not shove the monitor the user is looking at.
    """

    sideClicked = Signal(str)
    moveRequested = Signal(str, int, int)        # device, x, y in desktop px
    selectedChanged = Signal(str)                # which screen the card edits
    # 190: three stacked screens spend the widget's height on 5040 desktop px.
    # At 170 the virtual and third boxes fell below the height where the caption
    # line fits (number only); 190 keeps the caption and still leaves the
    # resolution/scaling row on the first screen at the default window height.
    MIN_H, PAD, GUT = 190, 12, 18
    SNAP_PX = 8.0
    SIDE_CN = {"left": "在左侧", "right": "在右侧",
               "above": "在上方", "below": "在下方"}
    # tooltip phrasing: "放到%s" reads right with a bare direction, while
    # SIDE_CN's "在…" form belongs to the legend's 偏向… sentence
    SIDE_GO = {"left": "左侧", "right": "右侧",
               "above": "上方", "below": "下方"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._displays, self._ref, self._virtual = [], None, None
        self._side, self._exact = None, True
        self._interactive = False
        self._hover = None
        self._sig = None
        self._selected = None
        self._press_device = None
        self._drag = None           # {"device", "press", "rect", "moved"}
        self._drag_rect = None
        self.setMinimumHeight(self.MIN_H)
        self.setMouseTracking(True)

    def set_state(self, displays, ref, virtual, side, exact, interactive,
                  selected=None):
        """Feed it the live readings. Repaints only when something moved."""
        sig = (tuple(sorted((d["device"], d.get("number"), d["x"], d["y"],
                             d["width"], d["height"],
                             bool(d["virtual"]), bool(d["primary"]))
                            for d in displays)), side, exact, interactive,
               selected)
        if sig == self._sig:
            return
        self._sig = sig
        self._displays = list(displays)
        self._ref = ref
        self._virtual = virtual
        self._side = side
        self._exact = exact
        self._interactive = interactive
        self._selected = selected
        if not interactive:
            self._hover = None
        # A poll that saw the geometry change while a drag was in flight means
        # Windows moved a screen under our feet; the drag preview no longer
        # refers to anything real, so drop it rather than write a stale spot.
        self._drag = None
        self._drag_rect = None
        self.update()

    def set_selected(self, device):
        """Selection moved without any geometry moving."""
        if device != self._selected:
            self._selected = device
            self.update()

    # ------------------------------------------------------------- geometry
    def _layout(self):
        """(scale, origin, {device: QRectF}): desktop px -> widget px, centred."""
        ds = self._displays
        if not ds:
            return None
        x0 = min(d["x"] for d in ds)
        y0 = min(d["y"] for d in ds)
        bw = max(d["x"] + d["width"] for d in ds) - x0
        bh = max(d["y"] + d["height"] for d in ds) - y0
        # Scale to the inner box so a GUT-wide band is left free on all four
        # sides: without it the tallest screen fills the widget and the 上方 /
        # 下方 click zones simply do not exist (measured on the first run).
        inset = self.PAD + self.GUT
        aw, ah = self.width() - 2 * inset, self.height() - 2 * inset
        fw, fh = self.width() - 2 * self.PAD, self.height() - 2 * self.PAD
        if bw <= 0 or bh <= 0 or aw <= 8 or ah <= 8:
            return None
        k = min(aw / float(bw), ah / float(bh))
        ox = self.PAD + (fw - bw * k) / 2.0 - x0 * k
        oy = self.PAD + (fh - bh * k) / 2.0 - y0 * k
        rects = {d["device"]: QRectF(ox + d["x"] * k, oy + d["y"] * k,
                                     d["width"] * k, d["height"] * k)
                 for d in ds}
        return k, (ox, oy), rects

    def _side_at(self, x, y):
        """Which side of the reference screen a widget point falls on."""
        lay = self._layout()
        if not lay or self._ref is None:
            return None
        rb = lay[2].get(self._ref["device"])
        if rb is None:
            return None
        if rb.contains(float(x), float(y)):
            return None
        gaps = {"left": rb.left() - x, "right": x - rb.right(),
                "above": rb.top() - y, "below": y - rb.bottom()}
        cand = [(g, s) for s, g in gaps.items() if g > 0]
        return min(cand)[1] if cand else None

    def _movable_at(self, x, y):
        """Any attached, non-primary box under a point - virtual or physical.

        Windows pins the primary at (0,0); every other screen can be dragged,
        which is what the layout card's picture promises.
        """
        lay = self._layout()
        if not lay:
            return None
        for d in self._displays:
            if not d.get("attached") or d.get("primary"):
                continue
            r = lay[2].get(d["device"])
            if r is not None and r.contains(float(x), float(y)):
                return d["device"]
        return None

    def _display_at(self, x, y):
        """Device of any attached box under a widget point."""
        lay = self._layout()
        if not lay:
            return None
        for d in self._displays:
            if not d.get("attached"):
                continue
            r = lay[2].get(d["device"])
            if r is not None and r.contains(float(x), float(y)):
                return d["device"]
        return None

    def _clamp_rect(self, rect):
        """Keep the dragged box inside the picture.

        Windows accepts a screen at any coordinate; the widget is a finite
        box, so a box dragged past the edge would simply vanish.
        """
        x = min(max(rect.left(), self.PAD),
                max(self.PAD, self.width() - self.PAD - rect.width()))
        y = min(max(rect.top(), self.PAD),
                max(self.PAD, self.height() - self.PAD - rect.height()))
        out = QRectF(rect)
        out.moveLeft(x)
        out.moveTop(y)
        return out

    def _snap_rect(self, rect, device):
        """Pull a dragged box onto a neighbour's edges or centre lines.

        Candidates include true alignment (left/right/centre) and edge-to-edge
        abutment, which is what Windows' own settings do when two boxes touch.
        The threshold is in widget pixels, so it feels the same however far the
        desktop is zoomed down.
        """
        lay = self._layout()
        if not lay:
            return rect
        others = [r for dev, r in lay[2].items() if dev != device]
        if not others:
            return rect
        xs, ys = [rect.left()], [rect.top()]
        for o in others:
            for c in (o.left(), o.right() - rect.width(),
                      o.center().x() - rect.width() / 2.0,
                      o.right(), o.left() - rect.width()):
                if abs(c - rect.left()) <= self.SNAP_PX:
                    xs.append(c)
            for c in (o.top(), o.bottom() - rect.height(),
                      o.center().y() - rect.height() / 2.0,
                      o.bottom(), o.top() - rect.height()):
                if abs(c - rect.top()) <= self.SNAP_PX:
                    ys.append(c)
        out = QRectF(rect)
        out.moveLeft(min(xs, key=lambda c: abs(c - rect.left())))
        out.moveTop(min(ys, key=lambda c: abs(c - rect.top())))
        return self._clamp_rect(out)

    def _avoid_overlap(self, rect, device):
        """Windows will not let two extended sources overlap.

        Measured on this box: asking ChangeDisplaySettingsEx for a virtual
        screen that overlaps the physical one returns success but silently
        clamps the axis (y stayed at -1440 when -1360 was requested). A drag
        preview that ignored that would land where it never pointed. Push the
        box to the nearest free edge instead, like Windows' own arrangement.
        """
        lay = self._layout()
        if not lay:
            return rect
        out = QRectF(rect)
        others = [r for dev, r in lay[2].items() if dev != device]
        for _ in range(3):                 # a push can hit the next neighbour
            moved = False
            for o in others:
                if not out.intersects(o):
                    continue
                cands = [
                    QPointF(o.left() - out.width(), out.top()),
                    QPointF(o.right(), out.top()),
                    QPointF(out.left(), o.top() - out.height()),
                    QPointF(out.left(), o.bottom()),
                ]
                pick = min(cands, key=lambda p: abs(p.x() - out.left()) +
                                                abs(p.y() - out.top()))
                out.moveTo(pick)
                moved = True
            if not moved:
                break
        return out

    def _tidy_rect(self, rect, device):
        """Overlap first, then snapping, then overlap again.

        Snapping to a centre line can put the box back on top of a neighbour;
        the second push keeps the release point legal.
        """
        return self._avoid_overlap(self._snap_rect(
            self._avoid_overlap(rect, device), device), device)

    def _to_desktop(self, rect):
        """Widget px -> desktop px, the coordinate space Windows stores."""
        lay = self._layout()
        if not lay:
            return None
        k, (ox, oy), _rects = lay
        return (int(round((rect.left() - ox) / k)),
                int(round((rect.top() - oy) / k)))

    def _hover_edge(self, lay):
        """(reference rect, side) for the placement band under the cursor.

        Deliberately not a ghost rectangle of the whole virtual screen: the
        placement would need a full screen-height of free band around the
        arrangement to fit, and clipping it looked worse than not drawing it.
        The cue is a single quiet line centred in the gap (see paintEvent);
        the cursor and the tooltip carry the rest.
        """
        if not lay or not (self._interactive and self._hover and self._ref):
            return None
        if self._hover == self._side:
            return None
        rb = lay[2].get(self._ref["device"])
        if rb is None:
            return None
        return rb, self._hover

    def _free_reach(self, rb, side, rects):
        """How many widget px the gap on `side` of `rb` stays clear of other
        boxes, capped at GUT.

        Boxes sit at scaled real positions, so the band next to the reference
        edge can be nearly zero when a screen is adjacent (or staircase-offset,
        with its bottom edge just above the reference top). The marker is
        placed inside the measured free gap so it can never lie on top of a
        neighbour - the earlier fixed-length arrow did exactly that.
        """
        lim = float(self.GUT)
        for dev, r in rects.items():
            if dev == self._ref["device"]:
                continue
            if side in ("left", "right"):
                if r.bottom() < rb.top() + 1 or r.top() > rb.bottom() - 1:
                    continue          # not alongside this vertical stretch
                d = (rb.left() - r.right()) if side == "left" \
                    else (r.left() - rb.right())
            else:
                if r.right() < rb.left() + 1 or r.left() > rb.right() - 1:
                    continue
                d = (rb.top() - r.bottom()) if side == "above" \
                    else (r.top() - rb.bottom())
            if d >= -0.5:
                lim = min(lim, max(0.0, d))
        return lim

    # --------------------------------------------------------------- paint
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self._displays:
            p.setPen(QColor(C["faint"]))
            p.drawText(self.rect(), Qt.AlignCenter, "没有接好的显示器")
            p.end()
            return
        lay = self._layout()
        if not lay:
            p.end()
            return
        k, _org, rects = lay
        for d in self._displays:
            if self._drag and d["device"] == self._drag["device"]:
                continue                     # drawn on top, under the cursor
            self._paint_box(p, d, rects[d["device"]])
        if self._drag and self._drag_rect:
            d = next((x for x in self._displays
                      if x["device"] == self._drag["device"]), None)
            if d is not None:
                self._paint_box(p, d, self._drag_rect, dragging=True)
        edge = self._hover_edge(lay)
        if edge is not None:
            rb, side = edge
            reach = self._free_reach(rb, side, rects)
            if reach >= 4.0:
                pen = QPen(QColor(C["accent"]), 2.0)
                pen.setCapStyle(Qt.RoundCap)
                p.setPen(pen)
                # centred in the free gap so the line touches neither the
                # reference box nor a neighbour
                off = min(self.GUT, reach) / 2.0
                if side == "left":
                    x = rb.left() - off
                    p.drawLine(QPointF(x, rb.top()), QPointF(x, rb.bottom()))
                elif side == "right":
                    x = rb.right() + off
                    p.drawLine(QPointF(x, rb.top()), QPointF(x, rb.bottom()))
                elif side == "above":
                    y = rb.top() - off
                    p.drawLine(QPointF(rb.left(), y), QPointF(rb.right(), y))
                else:
                    y = rb.bottom() + off
                    p.drawLine(QPointF(rb.left(), y), QPointF(rb.right(), y))
        p.end()

    def _paint_box(self, p, d, r, dragging=False):
        virt = bool(d["virtual"])
        sel = self._selected == d["device"]
        edge = C["accent"] if (virt or sel) else C["border"]
        pen = QPen(QColor(edge), 2.6 if sel else (2.4 if dragging else
                                                  (1.8 if virt else 1.2)))
        if dragging:
            pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        fill = "#22363a" if dragging else ("#1f3032" if sel else
                                           ("#1b2a2b" if virt else "#141821"))
        p.setBrush(QBrush(QColor(fill)))
        p.drawRoundedRect(r, 6, 6)
        self._paint_label(p, d, r)

    def _paint_label(self, p, d, r):
        """The Identify number first, then what the box is.

        Windows' display settings identify a screen by a number and nothing
        else. That number is the only handle a person has when the screens are
        not where the picture says, so it gets the large type; the words shrink
        to one small line and fall back to abbreviations only when the box is
        too narrow to carry them.
        """
        virt = bool(d["virtual"])
        # a screen that is switched off has no Windows number either
        num = str(d.get("number") or "–")
        nfont = QFont(self.font())
        nfont.setBold(True)
        nfont.setPixelSize(int(round(max(11.0, min(24.0, r.height() * 0.40)))))
        nmet = QFontMetrics(nfont)
        full = ("虚拟屏" if virt else "物理屏")
        full += ("·主屏" if d.get("primary") else "")
        full += " · %dx%d" % (d["width"], d["height"])
        small = ("虚" if virt else "物") + ("·主" if d.get("primary") else "")
        small += " · " + res_tag(d["width"], d["height"])
        sfont = QFont(self.font())
        sfont.setPixelSize(11)
        smet = QFontMetrics(sfont)
        avail = max(0.0, r.width() - 10.0)
        sub = small if smet.horizontalAdvance(full) > avail else full

        nh, sh = nmet.height(), smet.height()
        hot = virt or self._selected == d["device"]
        if r.height() < nh + sh + 2:
            # box too short for two lines: the number is what matters
            p.setFont(nfont)
            p.setPen(QColor(C["accent"] if hot else C["text"]))
            p.drawText(r, Qt.AlignCenter, num)
            return
        top = r.center().y() - (nh + sh) / 2.0
        p.setFont(nfont)
        p.setPen(QColor(C["accent"] if hot else C["text"]))
        p.drawText(QRectF(r.left(), top, r.width(), nh), Qt.AlignCenter, num)
        p.setFont(sfont)
        p.setPen(QColor(C["muted"]))
        p.drawText(QRectF(r.left(), top + nh, r.width(), sh),
                   Qt.AlignCenter, sub)

    # ---------------------------------------------------------------- input
    def mousePressEvent(self, ev):
        """Pressing a virtual box picks it up; any box becomes the selection."""
        if self._interactive and ev.button() == Qt.LeftButton:
            dev = self._display_at(ev.pos().x(), ev.pos().y())
            if dev:
                self._press_device = dev
                if dev != self._selected:
                    self._selected = dev
                    self.selectedChanged.emit(dev)
                    self.update()
                if self._movable_at(ev.pos().x(), ev.pos().y()) == dev:
                    lay = self._layout()
                    if lay and dev in lay[2]:
                        self._drag = {"device": dev,
                                      "press": QPointF(ev.pos()),
                                      "rect": QRectF(lay[2][dev]),
                                      "moved": False}
                        self._drag_rect = QRectF(lay[2][dev])
                        self._hover = None
                        self.setCursor(Qt.ClosedHandCursor)
                        self.setToolTip("松手就按这个位置写回 Windows")
                        self.update()
                return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._drag:
            delta = QPointF(ev.pos()) - self._drag["press"]
            if abs(delta.x()) > 3 or abs(delta.y()) > 3:
                self._drag["moved"] = True
            r = QRectF(self._drag["rect"])
            r.translate(delta.x(), delta.y())
            r = self._clamp_rect(r)
            if self._drag["moved"]:
                r = self._tidy_rect(r, self._drag["device"])
            self._drag_rect = r
            self.update()
            return
        if not self._interactive:
            super().mouseMoveEvent(ev)
            return
        if self._movable_at(ev.pos().x(), ev.pos().y()):
            # over a draggable box: say so instead of drawing a placement edge
            changed = self._hover is not None or self.cursor().shape() != Qt.SizeAllCursor
            self._hover = None
            self.setCursor(Qt.SizeAllCursor)
            self.setToolTip("拖动这块屏，松手就按这个位置写回 Windows")
            if changed:
                self.update()
            super().mouseMoveEvent(ev)
            return
        if self._display_at(ev.pos().x(), ev.pos().y()):
            # the primary: selectable for its resolution row, pinned in place
            changed = self._hover is not None
            self._hover = None
            self.setCursor(Qt.PointingHandCursor)
            self.setToolTip("主屏固定在 (0,0)，不能拖；点一下选中它改分辨率/缩放")
            if changed:
                self.update()
            super().mouseMoveEvent(ev)
            return
        side = self._side_at(ev.pos().x(), ev.pos().y())
        if side != self._hover:
            self._hover = side
            self.setCursor(Qt.PointingHandCursor if side else Qt.ArrowCursor)
            self.setToolTip(("点击空隙：把虚拟屏放到主屏%s"
                             % self.SIDE_GO[side]) if side else "")
            self.update()
        super().mouseMoveEvent(ev)

    def leaveEvent(self, ev):
        if self._drag:
            return
        if self._hover:
            self._hover = None
            self.setCursor(Qt.ArrowCursor)
            self.setToolTip("")
            self.update()
        super().leaveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if self._drag and ev.button() == Qt.LeftButton:
            drag, rect = self._drag, self._drag_rect
            self._drag, self._drag_rect = None, None
            self._press_device = None
            self.setCursor(Qt.ArrowCursor)
            self.setToolTip("")
            self.update()
            if drag["moved"] and rect is not None:
                pos = self._to_desktop(rect)
                if pos:
                    self.moveRequested.emit(drag["device"], pos[0], pos[1])
            # a press that did not move is not a placement click either
            return
        if self._press_device:
            # a click on a box only selects it; placement lives outside the boxes
            self._press_device = None
            return
        if self._interactive and ev.button() == Qt.LeftButton:
            side = self._side_at(ev.pos().x(), ev.pos().y())
            if side:
                self.sideClicked.emit(side)
        super().mouseReleaseEvent(ev)


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
        # Start big enough that the layout card's resolution/scaling row (and
        # its 应用) is on screen without scrolling; clamped for small screens.
        scr = QApplication.primaryScreen()
        avail = scr.availableGeometry() if scr else None
        w, h = 660, 860
        if avail is not None:
            w = min(w, max(self.minimumWidth(), avail.width() - 60))
            h = min(h, max(self.minimumHeight(), avail.height() - 60))
        self.resize(w, h)
        if avail is not None:
            self.move(avail.center().x() - w // 2,
                      avail.center().y() - h // 2)
        # size to restore when moving between screens; resizeEvent updates it
        # only for sizes the user chose on the current screen
        self._base_size = self.size()
        self._base_screen = None
        self._adjusting = False
        self._threads = []
        self._st = {}
        # A pick in the resolution combo (or a typed count) is a request, not a
        # fact until 应用 runs. The poll rebuilds both from whatever the driver
        # reports, so without these a pending value reverts under the cursor.
        self._count_dirty = None
        self._sel_device = None
        self._res_sig = None
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
        wh = self.windowHandle()
        if wh is not None and not getattr(self, "_screen_wired", False):
            self._screen_wired = True
            wh.screenChanged.connect(self._screen_changed)

    def _screen_changed(self, scr):
        """Keep the panel inside whatever screen it was dragged to.

        Qt keeps the *logical* size across per-monitor DPI changes, so the
        660x860 window that fit the 200% main screen became 1155x1505 physical
        px on the 175% second screen - 65px taller than that screen. Cap to
        the new screen's available area, keep the title bar on-screen, and
        restore the size the user chose when the next screen has room for it.
        """
        if scr is None:
            return
        QTimer.singleShot(0, lambda: self._fit_to_screen(scr))

    def _fit_to_screen(self, scr):
        if scr is None:
            return
        avail = scr.availableGeometry()
        base = getattr(self, "_base_size", self.size())
        max_w = max(self.minimumWidth(), avail.width() - 40)
        max_h = max(self.minimumHeight(), avail.height() - 40)
        w = max(self.minimumWidth(), min(base.width(), max_w))
        h = max(self.minimumHeight(), min(base.height(), max_h))
        self._adjusting = True
        try:
            if (w, h) != (self.width(), self.height()):
                # resize from the top-left corner: the window stays where the
                # user dropped it, it only gets shorter/wider to fit
                self.resize(w, h)
        finally:
            self._adjusting = False

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        # Remember the size the user chose, but not the size Qt imposes while
        # crossing a DPI boundary: that one belongs to the new screen, not to
        # the user, and restoring it would defeat the cap above.
        if getattr(self, "_adjusting", False):
            return
        scr = self.screen()
        if scr is getattr(self, "_base_screen", None):
            self._base_size = self.size()
        else:
            self._base_screen = scr

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
        # the schematic first, the buttons second: the picture says where things
        # are, the buttons only move them
        self.map = DisplayMap()
        self.map.sideClicked.connect(self._place)
        self.map.moveRequested.connect(self._move_display)
        self.map.selectedChanged.connect(self._screen_selected)
        l5.addWidget(self.map)
        self.lbl_map_legend = QLabel("")
        self.lbl_map_legend.setObjectName("Key")
        self.lbl_map_legend.setWordWrap(True)
        l5.addWidget(self.lbl_map_legend)

        # the screen picked in the schematic owns the two settings Windows puts
        # under its own arrangement picture: resolution and scaling
        self.lbl_screen = QLabel("—")
        self.lbl_screen.setObjectName("Key")
        self.lbl_screen.setWordWrap(True)
        l5.addWidget(self.lbl_screen)

        # One screen's two fields share a row. The hierarchy is carried by
        # spacing, not by a fixed label column: each label hugs its own box,
        # the two groups get a wider gap, and 应用 lives at the row's end so it
        # reads as the action for both. Four equal gaps (and 74px-wide labels)
        # made it look like four unrelated controls.
        row = QHBoxLayout()
        row.setSpacing(6)
        rlab = QLabel("分辨率")
        rlab.setObjectName("Key")
        row.addWidget(rlab)
        self.cmb_res = QComboBox()
        self.cmb_res.setObjectName("Res")
        self.cmb_res.setMaxVisibleItems(16)
        Chevron(self.cmb_res)
        WheelNeedsFocus(self.cmb_res)
        row.addWidget(self.cmb_res)
        row.addSpacing(14)                 # group gap = 20px with the spacing
        zlab = QLabel("缩放")
        zlab.setObjectName("Key")
        row.addWidget(zlab)
        self.cmb_scale = QComboBox()
        self.cmb_scale.setObjectName("Scale")
        self.cmb_scale.setMaxVisibleItems(12)
        Chevron(self.cmb_scale)
        WheelNeedsFocus(self.cmb_scale)
        row.addWidget(self.cmb_scale)
        row.addStretch(1)
        # No 应用 button: a bare button at the row's end was the most
        # conspicuous thing on the card. Windows' own display page applies a
        # pick as soon as it is made, and so does this - the hint says so
        # instead of leaving a button to explain it.
        self.lbl_instant = QLabel("选中即生效")
        self.lbl_instant.setObjectName("Hint")
        row.addWidget(self.lbl_instant)
        l5.addLayout(row)

        def seg_row(title, items, handler, target=None):
            target = l5 if target is None else target
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
            target.addWidget(wrap)
            return btns

        self.topo_btns = seg_row(
            "显示模式",
            [("extend", "扩展", False),
             ("virtual", "仅虚拟屏", True),
             ("physical", "仅物理屏", False),
             ("clone", "复制", False)],
            self._set_topo)
        # mode -> primary -> placement is the order the facts depend on:
        # placement only means something in extend mode, and it is measured
        # from whichever screen is primary
        self.prim_btns = seg_row(
            "主显示器",
            [("physical", "物理屏", False), ("virtual", "虚拟屏", False)],
            self._make_primary)
        self.pos_btns = seg_row(
            "虚拟屏位置",
            [("left", "在左侧", False), ("right", "在右侧", False),
             ("above", "在上方", False), ("below", "在下方", False)],
            self._place)
        bl2.addWidget(c5)

        # ---- streaming (Sunshine) ----
        c6, l6 = card("串流（Sunshine）")
        # One conclusion first, then the two choices, then the technical
        # detail. The old order mixed a success sentence, a caveat and the
        # raw conf, so the card never read top-to-bottom.
        self.lbl_ss_state = QLabel("—")
        self.lbl_ss_state.setObjectName("Value")
        self.lbl_ss_state.setWordWrap(True)
        l6.addWidget(self.lbl_ss_state)
        self.lbl_ss_note = QLabel("")
        self.lbl_ss_note.setObjectName("Hint")
        self.lbl_ss_note.setStyleSheet(
            "font-size:11px;color:%s;" % C["warning"])
        self.lbl_ss_note.setWordWrap(True)
        self.lbl_ss_note.setVisible(False)
        l6.addWidget(self.lbl_ss_note)

        # The target row is rebuilt from Sunshine's own enumeration: only a
        # screen it listed at startup can be pinned through output_name. Fixed
        # 「物理屏 / 虚拟屏」 buttons lied whenever there were two physical
        # screens, and greyed the virtual screen out when its log entry simply
        # had no GDI name.
        self.ss_row = QWidget()
        self.ss_row.setObjectName("Row")
        self.ss_lay = QHBoxLayout(self.ss_row)
        self.ss_lay.setContentsMargins(0, 0, 0, 0)
        self.ss_lay.setSpacing(6)
        sslab = QLabel("手机看哪块")
        sslab.setObjectName("Key")
        sslab.setMinimumWidth(74)
        self.ss_lay.addWidget(sslab)
        self.ss_btns = {}
        l6.addWidget(self.ss_row)

        self.others_btns = seg_row(
            "其他屏",
            [("keep", "保持扩展", False), ("blank", "串流时关掉", False)],
            self._pick_others, l6)
        # the one line that settles arguments: which screen the phone is not
        # looking at, by name
        self.lbl_ss_where = QLabel("—")
        self.lbl_ss_where.setObjectName("Key")
        self.lbl_ss_where.setWordWrap(True)
        l6.addWidget(self.lbl_ss_where)
        self.lbl_ss_cfg = QLabel("—")
        self.lbl_ss_cfg.setObjectName("Key")
        self.lbl_ss_cfg.setStyleSheet(
            "font-size:10.5px;color:%s;" % C["faint"])
        self.lbl_ss_cfg.setWordWrap(True)
        l6.addWidget(self.lbl_ss_cfg)
        self.others_btns["keep"].setToolTip(
            "其他屏照常可用，只是手机看不到它们")
        self.others_btns["blank"].setToolTip(
            "串流期间只保留手机看的那块，其余屏（包括物理屏）会熄灭；断开后恢复")
        bl2.addWidget(c6)

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
        self.btn_count.setObjectName("Compact")
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
        self.btn_add_res.setObjectName("Compact")
        ra.addWidget(self.btn_add_res)
        ra.addStretch(1)
        l3.addLayout(ra)

        # Same misfire as the resolution combo: one stray notch over 数量/宽/高
        # silently rewrites the driver config numbers.
        for spin in (self.spn_count, self.spn_w, self.spn_h, self.spn_hz):
            WheelNeedsFocus(spin)

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
        self.btn_count.clicked.connect(self._apply_count)
        self.cmb_res.activated.connect(self._resolution_picked)
        self.cmb_scale.activated.connect(self._scaling_picked)
        self.spn_count.valueChanged.connect(self._count_edited)
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
        text = str(text)
        self.pill.setText(text[:40])
        # the pill is one line; keep the full message reachable on hover
        self.pill.setToolTip(text if len(text) > 40 else "")
        self.pill.setStyleSheet(
            "QLabel#Pill { font-size:11px; font-weight:600; padding:2px 10px;"
            "border-radius:9px; color:%s; background-color:#1e232c; }" % color)

    def _count_edited(self, value):
        self._count_dirty = value

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

    def _stream_axes(self):
        """Read the two stream axes back out of Sunshine's own config.

        The conf is the only source of truth - nothing is remembered from the
        last click, so an edit made in Sunshine's web UI shows up here on the
        next poll just like a display change does.
        """
        ss = backend.sunshine_status()
        st = ss.get("settings") or {}
        out = (st.get("output_name") or "").strip()
        dd = (st.get("dd_configuration_option") or "disabled").strip()
        targets = ss.get("targets") or []
        keys = {t["key"] for t in targets}
        if not out:
            target = "system"
        elif out in keys:
            target = out
        else:
            target = "stale"          # pinned to a screen Sunshine no longer lists
        return {"target": target, "keep": dd != "ensure_only_display",
                "ids": ss.get("display_ids") or {}, "targets": targets,
                "settings": st}

    def _add_ss_btn(self, key, text, tip=""):
        b = QPushButton(text)
        b.setObjectName("Seg")
        b.setMinimumWidth(0)
        if tip:
            b.setToolTip(tip)
        b.clicked.connect(lambda _=False, k=key: self._pick_stream_target(k))
        self.ss_lay.addWidget(b)
        self.ss_btns[key] = b

    def _rebuild_stream_targets(self, targets):
        """Rebuild the target row only when Sunshine's list actually changes.

        Rebuilding every poll would flicker and steal focus; the keys, numbers
        and names are enough of a signature.
        """
        sig = tuple((t.get("key"), t.get("number"), t.get("kind"),
                     t.get("name")) for t in targets)
        if sig == getattr(self, "_ss_sig", None):
            return
        self._ss_sig = sig
        while self.ss_lay.count() > 1:        # keep the row label at index 0
            item = self.ss_lay.takeAt(1)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self.ss_btns = {}
        # "follow the primary" is always available: it is the config with no
        # output_name at all
        self._add_ss_btn("system", "跟随主屏",
                         "不钉屏：Sunshine 抓主显示器那一块")
        for t in targets:
            num = t.get("number") or "?"
            kind = "虚拟" if t.get("kind") == "virtual" else "物理"
            tip = "%s（%s）" % (t.get("name") or "未命名", t.get("gdi") or "")
            self._add_ss_btn(t["key"], "%s 号屏 · %s" % (num, kind), tip)
        self.ss_lay.addStretch(1)

    def _pick_stream_target(self, key):
        """Which screen the phone sees. Keeps the other axis as it stands."""
        cur = self._stream_axes()
        self._need_admin(backend.set_stream_target, key, cur["keep"])

    def _pick_others(self, key):
        """Whether the other screens go dark during a stream.

        Meaningless while the target is '跟随主屏' (that option is what stops
        Sunshine touching the topology), so the row is greyed out there; a
        click that still arrives is ignored rather than silently switching
        the target.
        """
        cur = self._stream_axes()
        if cur["target"] in ("system", "stale"):
            return
        self._need_admin(backend.set_stream_target, cur["target"],
                         key == "keep")

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

    def _move_display(self, device, x, y):
        """A drag in the schematic landed: write the spot into Windows."""
        self._act(backend.move_display, device, x, y)

    def _screen_selected(self, device):
        """The schematic says which box was clicked; edit that screen."""
        self._sel_device = device
        self.map.set_selected(device)
        d = next((x for x in (self._st.get("displays") or [])
                  if x["device"] == device), None)
        self._fill_screen_card(d, self._st.get("scaling") or {})

    def _resolution_picked(self, _index):
        """A resolution was picked from the dropdown - apply it right away.

        'activated' only fires on user interaction, so the poll's own
        setCurrentIndex never calls this. The current refresh rate is kept
        when the picked size supports it, otherwise the fastest one is used.
        """
        dev = getattr(self, "_sel_device", None)
        data = self.cmb_res.currentData()
        if not dev or not data:
            return
        d = next((x for x in (self._st.get("displays") or [])
                  if x["device"] == dev), None)
        if d is None:
            return
        w, h = data
        if (w, h) == (d["width"], d["height"]):
            return
        hzs = [hz for (mw, mh, hz) in self._cached_modes(d)
               if (mw, mh) == (w, h)]
        if not hzs:
            return
        hz = d["hz"] if d["hz"] in hzs else max(hzs)
        self._act(backend.set_display_mode, dev, w, h, hz)

    def _scaling_picked(self, _index):
        """A scaling was picked - apply it right away, like Windows' page."""
        dev = getattr(self, "_sel_device", None)
        pct = self.cmb_scale.currentData()
        if not dev or not pct:
            return
        now = (self._st.get("scaling") or {}).get(dev)
        if int(pct) == now:
            return
        self._act(backend.set_display_scaling, dev, int(pct))

    def _make_primary(self, which):
        self._act(backend.make_primary, which)

    def _reload(self):
        self._need_admin(backend.reload_driver)

    def _banner_action(self):
        mode = self._st.get("_banner_mode")
        if mode == "install":
            if backend.HAS_PROJECT:
                self._act(backend.start_install)
            else:
                # a shared exe has no project folder: install from the driver
                # files bundled inside it instead
                self._need_admin(backend.install_driver_bundled)
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
               # where each screen sits is the whole point of the schematic and
               # of the 位置 selection state, so a move must re-paint even if no
               # size changed
               (s["virtual"] or {}).get("x"), (s["virtual"] or {}).get("y"),
               (s["physical"] or {}).get("x"), (s["physical"] or {}).get("y"),
               s.get("virtual_side"), s.get("virtual_side_exact"),
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
        self._modes_cache = None          # driver work may change the list
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

        if cfg:
            if self._count_dirty in (None, cfg["count"]):
                self.spn_count.blockSignals(True)
                self.spn_count.setValue(cfg["count"])
                self.spn_count.blockSignals(False)
                self._count_dirty = None
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
        self._apply_streaming(s, vd)

    def _mark(self, btn, active):
        """Flip a segment button's [active] style property in place."""
        if btn.property("active") != active:
            btn.setProperty("active", active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _apply_layout(self, s, vd, phys):
        """Reflect the live multi-monitor state on the layout card."""
        topo = s.get("topology")
        labels = s.get("topology_labels") or {}
        valid = s.get("topology_valid") or {}
        mark = self._mark

        for key, b in self.topo_btns.items():
            mark(b, key == topo)
            b.setEnabled(bool(valid.get(key, True)))

        vd_primary = bool(vd and vd.get("primary"))
        for key, b in self.prim_btns.items():
            mark(b, (key == "virtual" and vd_primary) or
                    (key == "physical" and not vd_primary))
            b.setEnabled(bool(vd) and bool(phys))
            # number the two candidates like the picture does: with two
            # physical screens "物理屏" alone never said which one
            d = (phys[0] if phys else None) if key == "physical" else vd
            if d is not None:
                b.setText("%s 号屏 · %s" % (d.get("number") or "?",
                                            "物理" if key == "physical" else "虚拟"))
        # Switching the primary to the virtual screen is not cosmetic: the
        # taskbar and the mouse follow it onto a screen nobody can see. Say so
        # where the click happens rather than in a doc nobody opens.
        self.prim_btns["virtual"].setToolTip(
            "主显示器会跳到虚拟屏 —— 任务栏和鼠标都跟过去，而那块屏你看不见。\n"
            "要回来：再点左边的物理屏")
        self.prim_btns["physical"].setToolTip("把主显示器切回物理屏（当前那块能看见的）")

        # position only means something while both screens are on. The side is
        # read back out of Windows' coordinates (vdd_core.virtual_side), never
        # remembered from the last click - Windows' own settings can move it.
        side = s.get("virtual_side")
        exact = s.get("virtual_side_exact")
        movable = topo == "extend" and bool(vd) and bool(phys)
        for key, b in self.pos_btns.items():
            mark(b, key == side)
            b.setEnabled(movable)
        # which screen the resolution/scaling row edits: whatever was clicked
        # in the picture, defaulting to the virtual one so the card is useful
        # on first open
        attached = [d for d in (s.get("displays") or []) if d.get("attached")]
        sel = getattr(self, "_sel_device", None)
        if sel not in [d["device"] for d in attached]:
            pick = vd or phys or (attached[0] if attached else None)
            sel = pick["device"] if pick else None
            self._sel_device = sel
        self.map.set_state(s.get("displays") or [], s.get("reference"),
                           vd, side, exact, movable, selected=sel)
        self._fill_screen_card(
            next((d for d in attached if d["device"] == sel), None),
            s.get("scaling") or {})
        self.map.setToolTip(
            "拖动虚拟屏或物理副屏可放到任意位置（主屏固定在 0,0）；"
            "点主屏的某一侧则把虚拟屏贴到那一侧"
            if movable else "切回「扩展」才能挪虚拟屏的位置")

        # the schematic abbreviates when a box gets small, so the exact readings
        # live here instead
        scaling = s.get("scaling") or {}
        rows = []
        for d in s.get("displays") or []:
            if not d.get("attached"):
                continue
            rows.append("%s @(%d,%d)　缩放 %s" % (
                backend.describe_display(d), d["x"], d["y"],
                ("%d%%" % scaling[d["device"]]) if scaling.get(d["device"]) else "未知"))
        if side and not exact:
            rows.append("虚拟屏不在标准摆位（偏向%s，可能是手动拖过一半）"
                        % DisplayMap.SIDE_CN[side])
        elif not side and movable:
            rows.append("虚拟屏和主屏叠在同一个位置，说不清在哪一侧")
        self.lbl_map_legend.setText("\n".join(rows))

        cur = labels.get(topo, "未知")
        if topo == "virtual":
            hint = ("当前：%s —— 物理屏已关闭。按 Win+P 或点上面的「扩展」可以恢复。"
                    % cur)
        else:
            hint = ("当前：%s。这里改的就是 Windows 自己的显示模式，"
                    "跟系统设置里的「多显示器」是同一处，两边会同步。"
                    "图中数字与系统设置里「标识」的编号一致；除主屏外都能直接拖。"
                    % cur)
        if topo == "clone":
            hint += "复制模式下两块屏必须用同一分辨率。"
        self.lbl_layout_hint.setText(hint)
        self.lbl_layout_hint.setStyleSheet(
            "font-size:11px;color:%s;font-weight:600;"
            % (C["warning"] if topo == "virtual" else C["muted"]))

    def _fill_screen_card(self, d, scaling):
        """Resolution + scaling of the screen picked in the picture.

        Both values are read back from Windows on every poll, so a change made
        in the system settings shows up here without the panel claiming a
        stale value. The resolution list is Windows' own EnumDisplaySettings
        list, collapsed to one line per size with the fastest refresh behind
        it; a pick keeps the current refresh rate when that size supports it.
        """
        if d is None:
            self.lbl_screen.setText("没有可选的屏")
            self.cmb_res.clear()
            self.cmb_scale.clear()
            self.cmb_res.setEnabled(False)
            self.cmb_scale.setEnabled(False)
            self.lbl_instant.setVisible(False)
            return

        virt = bool(d["virtual"])
        self.lbl_screen.setText(
            "选中的是 %s 号 %s（%s）—— 点图中另一块可切换。"
            % (d.get("number"), "虚拟屏" if virt else "物理屏",
               friendly_device(d["device"])))
        self.cmb_res.setEnabled(True)
        self.cmb_scale.setEnabled(True)
        self.lbl_instant.setVisible(True)

        modes = self._cached_modes(d)
        best = {}
        for (w, h, hz) in modes:
            key = (w, h)
            if key not in best or hz > best[key]:
                best[key] = hz
        opts = sorted(best.items(), key=lambda kv: (-kv[0][0] * kv[0][1],
                                                    -kv[0][1]))
        sig = (d["device"], tuple(opts), d["width"], d["height"])
        if sig != getattr(self, "_res_sig", None):
            self._res_sig = sig
            self.cmb_res.blockSignals(True)
            self.cmb_res.clear()
            for (w, h), _hz in opts:
                self.cmb_res.addItem("%d × %d" % (w, h), (w, h))
            for i in range(self.cmb_res.count()):
                w, h = self.cmb_res.itemData(i)
                if (w, h) == (d["width"], d["height"]):
                    self.cmb_res.setCurrentIndex(i)
                    break
            self.cmb_res.blockSignals(False)

        sc = scaling.get(d["device"])
        opts = backend.scale_options()
        if sc and sc not in opts:
            opts = sorted(opts + [sc])
        ssig = (d["device"], tuple(opts), sc)
        if ssig != getattr(self, "_scale_sig", None):
            self._scale_sig = ssig
            self.cmb_scale.blockSignals(True)
            self.cmb_scale.clear()
            for pct in opts:
                self.cmb_scale.addItem("%d%%" % pct, pct)
            if sc:
                for i in range(self.cmb_scale.count()):
                    if self.cmb_scale.itemData(i) == sc:
                        self.cmb_scale.setCurrentIndex(i)
                        break
            self.cmb_scale.blockSignals(False)
        self.lbl_instant.setToolTip(
            "下拉里选一个就立即生效，和 Windows 设置一样。\n"
            "已经打开的应用大多会跟着变，少数旧程序要重开才跟随。\n"
            "缩放档位有上限，超出会被夹住，结果以回读为准。")

    def _cached_modes(self, d):
        """EnumDisplaySettings over a 200-mode 4K panel costs ~68ms.

        The 3-second poll runs this on the UI thread, so keep the list until
        the screen's own mode (or the selection) changes. A full reload clears
        it, which is what happens after driver work.
        """
        key = (d["device"], d["width"], d["height"], d["hz"])
        cache = getattr(self, "_modes_cache", None)
        if cache and cache[0] == key:
            return cache[1]
        modes = tuple(backend.display_modes(d["device"]))
        self._modes_cache = (key, modes)
        return modes

    def _apply_streaming(self, s, vd):
        """One conclusion, two choices, then the raw conf."""
        ss = backend.sunshine_status()
        if not ss.get("installed"):
            self._rebuild_stream_targets([])
            self.lbl_ss_state.setText("未安装 Sunshine（串流功能不可用）")
            self.lbl_ss_state.setStyleSheet(
                "font-size:11.5px;color:%s;" % C["muted"])
            self.lbl_ss_note.setVisible(False)
            self.lbl_ss_where.setText("")
            self.lbl_ss_cfg.setText("")
            for b in self.ss_btns.values():
                b.setEnabled(False)
            for b in self.others_btns.values():
                b.setEnabled(False)
            return

        st = ss.get("settings") or {}
        out = (st.get("output_name") or "").strip()
        mode = (st.get("dd_configuration_option") or "disabled").strip()
        targets = ss.get("targets") or []
        axes = self._stream_axes()
        target, keep = axes["target"], axes["keep"]

        self._rebuild_stream_targets(targets)
        for key, b in self.ss_btns.items():
            self._mark(b, key == target)
            b.setEnabled(True)
        for key, b in self.others_btns.items():
            self._mark(b, (key == "keep") == keep)
            b.setEnabled(target not in ("system", "stale"))

        tgt = backend.capture_target(st, s.get("displays") or [])
        kind = tgt.get("kind")
        if kind in ("primary", "named"):
            d = tgt.get("display") or {}
            if d.get("number"):
                label = "%s 号屏 · %s（%s %dx%d%s）" % (
                    d.get("number"), "虚拟" if d.get("virtual") else "物理",
                    friendly_device(d.get("device")),
                    d.get("width"), d.get("height"),
                    "·主屏" if d.get("primary") else "")
            else:
                label = tgt.get("label", "?")
            self.lbl_ss_state.setText("手机看到 = %s" % label)
            self.lbl_ss_state.setStyleSheet(
                "font-size:11.5px;font-weight:600;color:%s;" % C["success"])
        elif kind == "stale":
            self.lbl_ss_state.setText(
                "手机看到 = 不确定：钉的屏不在 Sunshine 枚举里")
            self.lbl_ss_state.setStyleSheet(
                "font-size:11.5px;font-weight:600;color:%s;" % C["danger"])
        else:
            self.lbl_ss_state.setText("手机看到 = 未知")
            self.lbl_ss_state.setStyleSheet(
                "font-size:11.5px;font-weight:600;color:%s;" % C["warning"])

        notes = []
        if kind == "stale":
            notes.append("output_name 指向的 device_id 不在 Sunshine 这次的屏列表里；"
                         "重启 Sunshine，或点「跟随主屏」重新选。")
        if not any(t.get("kind") == "virtual" for t in targets):
            notes.append("Sunshine 还没枚举到虚拟屏；重启一次 Sunshine 后，"
                         "这里会出现「3 号屏 · 虚拟」。")
        self.lbl_ss_note.setText("\n".join(notes))
        self.lbl_ss_note.setVisible(bool(notes))

        # what the phone is *not* looking at, in the same numbered language
        # the buttons above use
        td = tgt.get("display") or {}
        others = []
        for d in (s.get("displays") or []):
            if not d.get("attached") or d["device"] == td.get("device"):
                continue
            others.append("%s 号屏 · %s（%s %dx%d）" % (
                d.get("number") or "?", "虚拟" if d.get("virtual") else "物理",
                friendly_device(d.get("device")), d.get("width"),
                d.get("height")))
        if kind in ("primary", "named") and others:
            self.lbl_ss_where.setText("手机看不到：%s" % "、".join(others))
            self.lbl_ss_where.setStyleSheet(
                "font-size:11px;color:%s;" % C["muted"])
        else:
            self.lbl_ss_where.setText("")

        self.lbl_ss_cfg.setText(
            "output_name = %s\ndd_configuration_option = %s"
            % (out or "（未设，抓主屏）", mode))

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
                 "open_project_dir", "start_install", "is_admin",
                 "sunshine_status", "capture_target", "side_position",
                 "describe_display", "display_modes", "set_display_mode",
                 "move_display", "set_display_scaling", "scale_options"):
        print("  %-18s %s" % (name, callable(getattr(backend, name, None))))

    print("\n-- ui import --")
    ui_ok = False
    checks = []
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        apply_dark_palette(app)
        app.setStyleSheet(STYLE)
        w = Main()
        print("  Main() constructed OK, %dx%d" % (w.width(), w.height()))
        print("  banner present  :", hasattr(w, "banner"))
        ui_ok = True

        # -- selection state and the schematic: the two things this card got
        #    wrong before (nothing ever marked the 位置 buttons as a group)
        w.reload()
        app.processEvents()
        s2 = w._st if w._st.get("topology") else s
        topo = s2.get("topology")
        vd2 = s2.get("virtual")
        phys2 = s2.get("physical")
        on = [k for k, b in w.pos_btns.items() if bool(b.property("active"))]
        lit = [k for k, b in w.topo_btns.items() if bool(b.property("active"))]
        print("  位置按钮亮着    :", on or "(无)")
        print("  显示模式亮着    :", lit or "(无)")
        print("  示意图屏数      :", len(w.map._displays),
              "side=%s exact=%s" % (w.map._side, w.map._exact))
        print("  图下读数        :", (w.lbl_map_legend.text() or "").replace("\n", " / "))
        print("  串流去向        :", (w.lbl_ss_where.text() or "").replace("\n", " / "))
        checks.append(("显示模式恰好亮一个", len(lit) == 1, lit))
        want_lit = 1 if (topo == "extend" and vd2 and phys2
                         and s2.get("virtual_side")) else 0
        checks.append(("位置按钮按真实几何亮%d个" % want_lit, len(on) == want_lit, on))
        checks.append(("位置亮的这一侧等于反推结果",
                       (not on) or on[0] == s2.get("virtual_side"), (on, s2.get("virtual_side"))))
        checks.append(("示意图拿到两块以上在位的屏", len(w.map._displays) >= 2,
                       len(w.map._displays)))
        checks.append(("图下读数非空（完整读数不被缩写吞掉）",
                       bool(w.lbl_map_legend.text()), w.lbl_map_legend.text()))
        checks.append(("串流去向说得出是哪块屏",
                       "手机看到 =" in (w.lbl_ss_state.text() or ""),
                       w.lbl_ss_state.text()))
        checks.append(("主显示器两个按钮都可点且带跳转提示",
                       all(b.isEnabled() for b in w.prim_btns.values()) and
                       "看不见" in (w.prim_btns["virtual"].toolTip() or ""),
                       [b.isEnabled() for b in w.prim_btns.values()]))
        # 串流：目标只能是 Sunshine 自己枚举到的屏；另一轴是其他屏黑不黑
        axes = w._stream_axes()
        lit_t = [k for k, b in w.ss_btns.items() if bool(b.property("active"))]
        lit_o = [k for k, b in w.others_btns.items() if bool(b.property("active"))]
        tnames = {t["key"]: "%s号屏" % t["number"] for t in axes["targets"]}
        tshow = tnames.get(axes["target"], axes["target"])
        print("  串流目标          : %s keep=%s 亮=%s / %s"
              % (tshow, axes["keep"], [tnames.get(k, k) for k in lit_t], lit_o))
        want_keys = {"system"} | {t["key"] for t in axes["targets"]}
        checks.append(("串流目标 = 跟随主屏 + Sunshine 枚举到的屏",
                       set(w.ss_btns) == want_keys,
                       (sorted(w.ss_btns), sorted(want_keys))))
        checks.append(("Sunshine 枚举到虚拟屏（EDID 兜底）",
                       any(t["kind"] == "virtual" for t in axes["targets"]),
                       [t["kind"] for t in axes["targets"]]))
        checks.append(("其他屏两态齐全",
                       set(w.others_btns) == {"keep", "blank"},
                       sorted(w.others_btns)))
        checks.append(("串流目标恰好亮一个且等于 conf 回读",
                       lit_t == [axes["target"]], (lit_t, axes["target"])))
        checks.append(("其他屏恰好亮一个且等于 conf 回读",
                       lit_o == [("keep" if axes["keep"] else "blank")],
                       (lit_o, axes["keep"])))
        checks.append(("跟随主屏时其他屏置灰",
                       (axes["target"] != "system") or
                       all(not b.isEnabled() for b in w.others_btns.values()),
                       (axes["target"],
                        [b.isEnabled() for b in w.others_btns.values()])))
        # 任务栏图标点一下要能收回：shell 只看样式位，所以直接量样式位
        w.show()
        for _ in range(8):
            app.processEvents()
            time.sleep(0.05)
        try:
            import ctypes
            h = int(w.winId())
            st = ctypes.windll.user32.GetWindowLongW(h, -16)
            ex = ctypes.windll.user32.GetWindowLongW(h, -20)
            checks.append(("样式带 WS_MINIMIZEBOX（任务栏点击可收回）",
                           bool(st & 0x00020000), hex(st & 0xFFFFFFFF)))
            checks.append(("样式带 WS_SYSMENU", bool(st & 0x00080000), hex(st)))
            checks.append(("没带 WS_CAPTION（不会长出系统标题栏）",
                           not (st & 0x00C00000), hex(st & 0xFFFFFFFF)))
            checks.append(("仍带 WS_THICKFRAME（边缘拖拽缩放不丢）",
                           bool(st & 0x00040000), hex(st & 0xFFFFFFFF)))
            checks.append(("扩展样式带 WS_EX_APPWINDOW（任务栏有按钮）",
                           bool(ex & 0x00040000), hex(ex & 0xFFFFFFFF)))
        except Exception as exc:                               # noqa: BLE001
            checks.append(("读窗口样式", False, str(exc)))
        # clicking a side must resolve through the same geometry the buttons use
        lay = w.map._layout()
        if lay:
            k, (ox, oy), rects = lay
            rb = rects[s2["physical"]["device"]]
            probes = {
                "left": (rb.left() - 30.0, rb.center().y()),
                "right": (rb.right() + 30.0, rb.center().y()),
                "above": (rb.center().x(), rb.top() - 30.0),
                "below": (rb.center().x(), rb.bottom() + 30.0),
            }
            for side, (px, py) in probes.items():
                got = w.map._side_at(px, py)
                checks.append(("点%s侧命中" % side, got == side, got))
            checks.append(("点主屏正中不动屏",
                           w.map._side_at(rb.center().x(), rb.center().y()) is None,
                           "None"))
            sub = next((d for d in (s2.get("displays") or [])
                        if d.get("attached") and not d.get("virtual")
                        and not d.get("primary")), None)
            if sub is not None:
                subc = rects[sub["device"]].center()
                checks.append(("物理副屏可拖（非主屏）",
                               w.map._movable_at(subc.x(), subc.y()) == sub["device"],
                               (sub["device"], w.map._movable_at(subc.x(), subc.y()))))
            checks.append(("主屏不能拖（固定在 0,0）",
                           w.map._movable_at(rb.center().x(),
                                             rb.center().y()) is None,
                           None))

        # -- system numbers, selection, per-screen settings, drag math -------
        nums = [(d.get("number"), d["device"])
                for d in (s2.get("displays") or []) if d.get("attached")]
        checks.append(("每块屏都有系统编号且连续",
                       [n for n, _ in nums] == list(range(1, len(nums) + 1)),
                       nums))
        checks.append(("选中态默认落在虚拟屏",
                       w._sel_device == (vd2 or {}).get("device"),
                       w._sel_device))
        checks.append(("选中屏的分辨率下拉等于当前模式",
                       bool(w.cmb_res.currentData()) and
                       tuple(w.cmb_res.currentData()) ==
                       ((vd2["width"], vd2["height"]) if vd2 else ()),
                       (w.cmb_res.count(), w.cmb_res.currentText())))
        sc = (s2.get("scaling") or {}).get((vd2 or {}).get("device"))
        checks.append(("缩放下拉选中的是系统回读值",
                       (("%d%%" % sc) == w.cmb_scale.currentText())
                       if sc else w.cmb_scale.count() == 0,
                       (w.cmb_scale.currentText(), sc)))
        checks.append(("没有应用按钮（选中即生效）",
                       not hasattr(w, "btn_screen_apply") and
                       not hasattr(w, "btn_res_apply") and
                       not hasattr(w, "btn_scale_apply"),
                       True))
        # regressions this card had: a stretching 465px combo box ran past the
        # right edge, and the whole settings row sat below the fold at the
        # default window size
        scr = w.findChild(QScrollArea)
        if scr is not None:
            panel = scr.widget()
            br = w.cmb_scale.mapTo(panel, w.cmb_scale.rect().topRight())
            checks.append(("缩放下拉不超出卡片内容宽",
                           br.x() <= panel.width() - 1,
                           (br.x(), panel.width())))
            bb = w.cmb_scale.mapTo(panel, w.cmb_scale.rect().bottomLeft())
            checks.append(("分辨率/缩放行在首屏内（不用滚动）",
                           bb.y() <= scr.viewport().height(),
                           (bb.y(), scr.viewport().height())))
        checks.append(("分辨率与缩放在同一行",
                       abs(w.cmb_res.mapTo(w, w.cmb_res.rect().topLeft()).y() -
                           w.cmb_scale.mapTo(w, w.cmb_scale.rect().topLeft()).y()) <= 2,
                       (w.cmb_res.y(), w.cmb_scale.y())))

        probe = DisplayMap()
        probe.resize(1062, 263)
        probe.set_state(s2.get("displays") or [], s2.get("reference"), vd2,
                        s2.get("virtual_side"), s2.get("virtual_side_exact"),
                        True, selected=(vd2 or {}).get("device"))
        play = probe._layout()
        if play and vd2 and phys2:
            _pk, _porg, prects = play
            prv = prects[vd2["device"]]
            prb = prects[phys2["device"]]
            checks.append(("拖动坐标往返",
                           probe._to_desktop(prv) == (vd2["x"], vd2["y"]),
                           (probe._to_desktop(prv), (vd2["x"], vd2["y"]))))
            near = QRectF(prb.left() - prv.width() + 4, prb.top() + 20,
                          prv.width(), prv.height())
            snapped = probe._tidy_rect(near, vd2["device"])
            checks.append(("拖到主屏边上会吸过去",
                           abs(snapped.right() - prb.left()) < 0.01,
                           (snapped.right(), prb.left())))
            on_top = QRectF(prb.center().x() - prv.width() / 2,
                            prb.center().y() - prv.height() / 2,
                            prv.width(), prv.height())
            pushed = probe._avoid_overlap(on_top, vd2["device"])
            checks.append(("重叠位置会被推开（Windows 不接受重叠）",
                           not pushed.intersects(prb), pushed))

            from PySide6.QtGui import QMouseEvent
            got = []
            probe.moveRequested.connect(
                lambda dev, x, y: got.append((dev, x, y)))

            def _mev(t, p, btn, btns):
                return QMouseEvent(t, p, p, btn, btns, Qt.NoModifier)

            press = QPointF(prv.center())
            move = press + QPointF(prb.left() - prv.width() + 4 - prv.left(),
                                   prb.top() + 20 - prv.top())
            probe.mousePressEvent(_mev(QEvent.MouseButtonPress, press,
                                       Qt.LeftButton, Qt.LeftButton))
            probe.mouseMoveEvent(_mev(QEvent.MouseMove, move,
                                      Qt.NoButton, Qt.LeftButton))
            probe.mouseReleaseEvent(_mev(QEvent.MouseButtonRelease, move,
                                         Qt.LeftButton, Qt.NoButton))
            checks.append(("松手写回的是被拖的那块屏",
                           bool(got) and got[0][0] == vd2["device"] and
                           got[0][2] >= 0, got))

        shot = w.map.grab()
        import tempfile
        png = os.path.join(tempfile.gettempdir(), "vdd_map_probe.png")
        shot.save(png)
        print("  示意图已渲染    :", shot.width(), "x", shot.height(), "->", png)
    except Exception as exc:                                   # noqa: BLE001
        print("  UI FAIL:", exc)

    print("\n-- selfcheck --")
    bad = 0
    for name, ok, detail in checks:
        print("  %s %-40s %s" % ("PASS" if ok else "FAIL", name, detail if not ok else ""))
        bad += 0 if ok else 1
    ui_ok = ui_ok and bad == 0 and bool(checks)
    print("RESULT =", "OK" if ui_ok else "FAIL", "（%d 项检查，%d 项不符）"
          % (len(checks), bad))

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
