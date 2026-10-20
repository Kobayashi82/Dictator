"""Componentes propios, pintados a mano y animados: botón del micrófono, selector de modo, botones con icono,
avisos flotantes y diálogos con letra grande."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from dictador.i18n import tr
from dictador.ui import style


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
        round(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


def add_shadow(widget: QWidget, blur: int = 24, dy: int = 4, alpha: int = 40) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, dy)
    effect.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(effect)


# -- botón del micrófono ----------------------------------------------------------------------------------------------


class MicButton(QAbstractButton):
    """Botón grande en forma de píldora. En reposo, azul («Empezar a hablar»); escuchando, rojo («Parar») con un halo
    que late al ritmo de la voz; cargando, un arco que gira."""

    HALO = 22  # margen alrededor de la píldora para dibujar el halo

    def __init__(self, parent: QWidget | None = None, compact: bool = False):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._compact = compact
        self._state = "idle"  # idle | listening | loading
        self._red = 0.0  # 0 azul … 1 rojo (animado)
        self._hover = 0.0
        self._level = 0.0
        self._shown_level = 0.0
        self._t0 = time.monotonic()
        self._color_anim = QVariantAnimation(self, duration=260, easingCurve=QEasingCurve.Type.OutCubic)
        self._color_anim.valueChanged.connect(self._set_red)
        self._hover_anim = QVariantAnimation(self, duration=150)
        self._hover_anim.valueChanged.connect(self._set_hover)
        self._ticker = QTimer(self, interval=16)
        self._ticker.timeout.connect(self.update)
        self.setAccessibleName(tr("Empezar a hablar"))

    def sizeHint(self) -> QSize:
        return QSize(300, 76) if self._compact else QSize(340, 84)
        # (la píldora mide 72/64 de alto; el resto es el halo)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    @property
    def state(self) -> str:
        return self._state

    def set_state(self, state: str) -> None:
        if state == self._state:
            return
        self._state = state
        self._color_anim.stop()
        self._color_anim.setStartValue(self._red)
        self._color_anim.setEndValue(1.0 if state == "listening" else 0.0)
        self._color_anim.start()
        if state == "idle":
            self._ticker.stop()
            self._level = 0.0
        else:
            self._ticker.start()
        self.setAccessibleName(tr({"idle": "Empezar a hablar", "listening": "Parar", "loading": "Preparando…"}[state]))
        self.update()

    def set_level(self, level: float) -> None:
        self._level = max(0.0, min(1.0, level))

    def _set_red(self, value) -> None:
        self._red = float(value)
        self.update()

    def _set_hover(self, value) -> None:
        self._hover = float(value)
        self.update()

    def enterEvent(self, event) -> None:
        self._hover_anim.setStartValue(self._hover)
        self._hover_anim.setEndValue(1.0)
        self._hover_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover_anim.setStartValue(self._hover)
        self._hover_anim.setEndValue(0.0)
        self._hover_anim.start()
        super().leaveEvent(event)

    def hitButton(self, pos) -> bool:
        return self._pill().contains(QPointF(pos))

    def _pill(self) -> QRectF:
        return QRectF(self.rect()).adjusted(self.HALO, self.HALO / 2 + 2, -self.HALO, -self.HALO / 2 - 2)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pill = self._pill()
        radius = pill.height() / 2
        base = _mix(style.ACCENT, style.RECORD, self._red)
        hover = _mix(style.ACCENT_HOVER, style.RECORD_HOVER, self._red)
        color = _mix(base, hover, self._hover)
        if self.isDown():
            color = color.darker(110)

        t = time.monotonic() - self._t0
        if self._state == "listening":
            # El halo: respira despacio y crece con el volumen de la voz.
            self._shown_level += (self._level - self._shown_level) * 0.25
            breath = (math.sin(t * 2.4) + 1) / 2
            grow = 4 + 6 * breath + 14 * self._shown_level
            for k, alpha in ((1.0, 40), (0.55, 70)):
                ring = QColor(style.RECORD)
                ring.setAlpha(alpha)
                g = grow * k
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(ring)
                p.drawRoundedRect(pill.adjusted(-g, -g, g, g), radius + g, radius + g)

        # Sombra suave y la píldora.
        shadow = QColor(0, 0, 0, 35)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(shadow)
        p.drawRoundedRect(pill.translated(0, 3), radius, radius)
        p.setBrush(color)
        p.drawRoundedRect(pill, radius, radius)

        # Icono (o arco girando) y texto.
        if self._state == "loading":
            label, icon = tr("Preparando…"), None
        elif self._state == "listening":
            label, icon = tr("Parar"), style.ICON_STOP
        else:
            label, icon = tr("Empezar a hablar"), style.ICON_MIC
        text_font = style.ui_font(16 if self._compact else 18, QFont.Weight.DemiBold)
        icon_size = 20 if self._compact else 22
        p.setFont(text_font)
        text_w = p.fontMetrics().horizontalAdvance(label)
        gap = 14
        icon_w = icon_size * 1.4
        total = icon_w + gap + text_w
        x = pill.center().x() - total / 2
        icon_rect = QRectF(x, pill.top(), icon_w, pill.height())
        p.setPen(QColor("white"))
        if icon == style.ICON_STOP:
            d = icon_size * 0.8
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("white"))
            p.drawRoundedRect(QRectF(icon_rect.center().x() - d / 2, icon_rect.center().y() - d / 2, d, d), 4, 4)
            p.setPen(QColor("white"))
        elif icon is None:
            pen = QPen(QColor("white"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            d = icon_size
            arc = QRectF(icon_rect.center().x() - d / 2, icon_rect.center().y() - d / 2, d, d)
            p.drawArc(arc, int(-t * 360 * 16) % (360 * 16), 270 * 16)
            p.setPen(QColor("white"))
        else:
            p.setFont(style.icon_font(icon_size))
            p.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, icon)
        p.setFont(text_font)
        p.drawText(QRectF(x + icon_w + gap, pill.top(), text_w + 4, pill.height()), Qt.AlignmentFlag.AlignVCenter, label)
        p.end()


# -- selector de modo -------------------------------------------------------------------------------------------------


class SegmentedControl(QWidget):
    """Opciones en una píldora gris; la elegida es una píldora blanca que se desliza hasta su sitio."""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str, str]], parent: QWidget | None = None):
        """options: (clave, texto, ayuda)."""
        super().__init__(parent)
        self._options = options
        self._index = 0
        self._hover = -1
        self._x = 0.0
        self._anim = QVariantAnimation(self, duration=240, easingCurve=QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._set_x)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._font = style.ui_font(13, QFont.Weight.DemiBold)
        self.setFixedHeight(48)

    def _widths(self) -> list[float]:
        from PySide6.QtGui import QFontMetricsF

        fm = QFontMetricsF(self._font)
        return [fm.horizontalAdvance(text) + 40 for _k, text, _h in self._options]

    def sizeHint(self) -> QSize:
        return QSize(int(sum(self._widths()) + 8), 48)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def _lefts(self) -> list[float]:
        lefts, x = [], 4.0
        for w in self._widths():
            lefts.append(x)
            x += w
        return lefts

    def current(self) -> str:
        return self._options[self._index][0]

    def set_current(self, key: str, animate: bool = True) -> None:
        index = next((i for i, o in enumerate(self._options) if o[0] == key), 0)
        if index == self._index and self._x:
            return
        self._index = index
        target = self._lefts()[index]
        if animate and self.isVisible():
            self._anim.stop()
            self._anim.setStartValue(self._x)
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self._x = target
            self.update()
        self.setToolTip(self._options[index][2])

    def _set_x(self, value) -> None:
        self._x = float(value)
        self.update()

    def showEvent(self, event) -> None:
        self._x = self._lefts()[self._index]
        super().showEvent(event)

    def _index_at(self, x: float) -> int:
        for i, (left, w) in enumerate(zip(self._lefts(), self._widths())):
            if left <= x < left + w:
                return i
        return -1

    def mouseMoveEvent(self, event) -> None:
        i = self._index_at(event.position().x())
        if i != self._hover:
            self._hover = i
            self.setToolTip(self._options[i][2] if i >= 0 else "")
            self.update()

    def leaveEvent(self, event) -> None:
        self._hover = -1
        self.update()

    def mousePressEvent(self, event) -> None:
        i = self._index_at(event.position().x())
        if i >= 0 and i != self._index:
            self.set_current(self._options[i][0])
            self.changed.emit(self._options[i][0])

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self.height()
        widths, lefts = self._widths(), self._lefts()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(style.TRACK)
        p.drawRoundedRect(QRectF(0, 0, lefts[-1] + widths[-1] + 4, h), h / 2, h / 2)
        if 0 <= self._hover != self._index:
            p.setBrush(style.TRACK_HOVER)
            p.drawRoundedRect(QRectF(lefts[self._hover], 4, widths[self._hover], h - 8), (h - 8) / 2, (h - 8) / 2)
        # La píldora blanca: su ancho sigue al desplazamiento entre dos opciones.
        w = widths[self._index]
        if self._anim.state() == QVariantAnimation.State.Running:
            start, end = self._anim.startValue(), self._anim.endValue()
            if end != start:
                frac = (self._x - start) / (end - start)
                prev = min(range(len(lefts)), key=lambda i: abs(lefts[i] - start))
                w = widths[prev] + (widths[self._index] - widths[prev]) * frac
        p.setBrush(QColor(0, 0, 0, 22))
        p.drawRoundedRect(QRectF(self._x, 5, w, h - 8), (h - 8) / 2, (h - 8) / 2)
        p.setBrush(style.THUMB)
        p.drawRoundedRect(QRectF(self._x, 4, w, h - 8), (h - 8) / 2, (h - 8) / 2)
        p.setFont(self._font)
        for i, ((_k, text, _h), left, width) in enumerate(zip(self._options, lefts, widths)):
            p.setPen((style.TEXT if style.DARK else style.ACCENT) if i == self._index else style.TEXT_SOFT)
            p.drawText(QRectF(left, 0, width, h), Qt.AlignmentFlag.AlignCenter, text)
        p.end()


# -- botón con icono y texto debajo -----------------------------------------------------------------------------------


class IconButton(QAbstractButton):
    def __init__(self, icon: str, text: str, tooltip: str = "", parent: QWidget | None = None,
                 glyph_font: QFont | None = None):
        super().__init__(parent)
        self._icon = icon
        self._glyph_font = glyph_font
        self.setText(text)
        self.setToolTip(tooltip or text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self._hover = 0.0
        self._anim = QVariantAnimation(self, duration=120)
        self._anim.valueChanged.connect(self._set_hover)
        self.setAccessibleName(text)

    def sizeHint(self) -> QSize:
        p = QPainter()  # noqa: F841  (solo para no crear métricas sin fuente)
        from PySide6.QtGui import QFontMetrics

        w = QFontMetrics(style.ui_font(11)).horizontalAdvance(self.text())
        return QSize(max(72, w + 24), 68)

    def _set_hover(self, value) -> None:
        self._hover = float(value)
        self.update()

    def enterEvent(self, event) -> None:
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def leaveEvent(self, event) -> None:
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(0.0)
        self._anim.start()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        bg = QColor(style.PRESSED if self.isDown() else style.HOVER)
        bg.setAlphaF(max(0.0, min(1.0, self._hover)) if self.isEnabled() else 0.0)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, 10, 10)
        color = style.TEXT if self.isEnabled() else style.DISABLED
        p.setPen(color)
        p.setFont(self._glyph_font or style.icon_font(18))
        p.drawText(QRectF(r.left(), r.top() + 6, r.width(), 32), Qt.AlignmentFlag.AlignCenter, self._icon)
        p.setFont(style.ui_font(11))
        p.drawText(QRectF(r.left(), r.top() + 38, r.width(), 22), Qt.AlignmentFlag.AlignCenter, self.text())
        p.end()


# -- aviso flotante ---------------------------------------------------------------------------------------------------


class Toast(QLabel):
    """Un aviso que aparece suavemente, se queda un momento y se va solo."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setFont(style.ui_font(13))
        self.setObjectName("toast")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)
        self._fade = QPropertyAnimation(self._effect, b"opacity", self, duration=220)
        self._timer = QTimer(self, singleShot=True)
        self._timer.timeout.connect(self._hide)
        self.hide()

    def show_message(self, text: str, ms: int = 2600) -> None:
        self.setText(text)
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()
        self._fade.stop()
        self._fade.setStartValue(self._effect.opacity())
        self._fade.setEndValue(1.0)
        self._fade.start()
        self._timer.start(ms)

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.move((parent.width() - self.width()) // 2, parent.height() - self.height() - 130)

    def _hide(self) -> None:
        self._fade.stop()
        self._fade.setStartValue(self._effect.opacity())
        self._fade.setEndValue(0.0)
        self._fade.start()


# -- barra de progreso y puntos de paso -------------------------------------------------------------------------------


class SoftProgress(QWidget):
    """Barra de progreso fina y redondeada que avanza con suavidad."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._value = 0.0
        self._shown = 0.0
        self.setFixedHeight(10)
        self._anim = QVariantAnimation(self, duration=400, easingCurve=QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._set_shown)

    def set_value(self, fraction: float) -> None:
        fraction = max(0.0, min(1.0, fraction))
        if abs(fraction - self._value) < 1e-4:
            return
        self._value = fraction
        self._anim.stop()
        self._anim.setStartValue(self._shown)
        self._anim.setEndValue(fraction)
        self._anim.start()

    def _set_shown(self, v) -> None:
        self._shown = float(v)
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(style.TRACK)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        if self._shown > 0:
            p.setBrush(style.ACCENT)
            p.drawRoundedRect(QRectF(r.left(), r.top(), max(r.height(), r.width() * self._shown), r.height()), 5, 5)
        p.end()


class StepDots(QWidget):
    def __init__(self, count: int, parent: QWidget | None = None):
        super().__init__(parent)
        self._count = count
        self._pos = 0.0
        self._anim = QVariantAnimation(self, duration=300, easingCurve=QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(lambda v: (setattr(self, "_pos", float(v)), self.update()))
        self.setFixedSize(count * 22 + 16, 16)

    def set_step(self, i: int) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(float(i))
        self._anim.start()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(self._count):
            closeness = max(0.0, 1 - abs(self._pos - i))
            w = 8 + 14 * closeness
            p.setBrush(_mix(style.SCROLL, style.ACCENT, closeness))
            x = i * 22 + 4 - (w - 8) / 2 + 4
            p.drawRoundedRect(QRectF(x, 4, w, 8), 4, 4)
        p.end()


# -- piezas pequeñas: insignia, botón píldora, interruptor, desplegable ------------------------------------------------


class Badge(QWidget):
    """Círculo de color suave con un icono dentro. `color` es el nombre de un color de `style` (sigue al tema)."""

    def __init__(self, icon: str, color: str = "ACCENT", size: int = 96, parent: QWidget | None = None):
        super().__init__(parent)
        self._icon = icon
        self._color = color
        self.setFixedSize(size, size)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = getattr(style, self._color)
        bg = QColor(color)
        bg.setAlpha(45 if style.DARK else 30)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawEllipse(QRectF(self.rect()))
        p.setPen(color)
        p.setFont(style.icon_font(self.width() * 0.3))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._icon)
        p.end()


class PillButton(QAbstractButton):
    """Botón redondeado con icono y texto, para acciones secundarias junto al botón de hablar."""

    def __init__(self, icon: str, text: str, parent: QWidget | None = None, size: float = 14):
        super().__init__(parent)
        self._icon = icon
        self._size = size
        self.setText(text)
        self.setAccessibleName(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

    def sizeHint(self) -> QSize:
        from PySide6.QtGui import QFontMetrics

        w = QFontMetrics(style.ui_font(self._size, QFont.Weight.DemiBold)).horizontalAdvance(self.text())
        return QSize(int(w + self._size * 1.6 + 58), 60)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -3.5)
        radius = r.height() / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 26))
        p.drawRoundedRect(r.translated(0, 2), radius, radius)
        bg = style.PRESSED if self.isDown() else (style.HOVER if self.underMouse() else style.SURFACE)
        p.setBrush(bg)
        p.setPen(QPen(style.BORDER, 1))
        p.drawRoundedRect(r, radius, radius)
        icon_w = self._size * 1.6
        text_font = style.ui_font(self._size, QFont.Weight.DemiBold)
        p.setFont(text_font)
        text_w = p.fontMetrics().horizontalAdvance(self.text())
        x = r.center().x() - (icon_w + 10 + text_w) / 2
        p.setPen(style.ACCENT if self.isEnabled() else style.DISABLED)
        p.setFont(style.icon_font(self._size * 1.05))
        p.drawText(QRectF(x, r.top(), icon_w, r.height()), Qt.AlignmentFlag.AlignCenter, self._icon)
        p.setPen(style.TEXT if self.isEnabled() else style.DISABLED)
        p.setFont(text_font)
        p.drawText(QRectF(x + icon_w + 10, r.top(), text_w + 4, r.height()), Qt.AlignmentFlag.AlignVCenter, self.text())
        p.end()


def _paint_switch(p: QPainter, r: QRectF, pos: float) -> None:
    """Interruptor: `pos` 0 apagado … 1 encendido."""
    p.setPen(QPen(_mix(style.TEXT_FAINT, style.ACCENT, pos), 1))
    p.setBrush(_mix(style.TRACK, style.ACCENT, pos))
    p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
    d = r.height() - 8
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_mix(style.TEXT_SOFT, QColor("white"), pos))
    p.drawEllipse(QRectF(r.left() + 4 + (r.width() - 8 - d) * pos, r.top() + 4, d, d))


class Switch(QAbstractButton):
    """Interruptor de encendido y apagado, grande y animado."""

    def __init__(self, checked: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(54, 30)
        self._pos = 1.0 if checked else 0.0
        self._anim = QVariantAnimation(self, duration=160, easingCurve=QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(lambda v: (setattr(self, "_pos", float(v)), self.update()))
        self.toggled.connect(self._animate)

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        _paint_switch(p, QRectF(self.rect()).adjusted(1, 1, -1, -1), self._pos)
        p.end()


class Combo(QComboBox):
    """Desplegable con la misma letra que el resto: la lista también sigue la hoja de estilo."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setView(QListView())
        self.setFont(style.ui_font(14))
        self.view().setFont(style.ui_font(14))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMaxVisibleItems(10)

    def wheelEvent(self, event) -> None:
        # La rueda desplaza la página en la que está, no cambia el micrófono por sorpresa al pasar por encima.
        event.ignore()


# -- panel del menú «Más» ---------------------------------------------------------------------------------------------


class MenuRow(QAbstractButton):
    """Una fila del panel: icono, texto y, a la derecha, el atajo o un interruptor."""

    def __init__(self, icon: str, text: str, hint: str = "", toggle: bool | None = None, parent=None):
        super().__init__(parent)
        self._icon = icon
        self._hint = hint
        self.setText(text)
        self.setAccessibleName(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setFixedHeight(50)
        if toggle is not None:
            self.setCheckable(True)
            self.setChecked(toggle)

    def sizeHint(self) -> QSize:
        return QSize(360, 50)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        if self.underMouse() or self.isDown():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(style.PRESSED if self.isDown() else style.HOVER)
            p.drawRoundedRect(r, 8, 8)
        p.setPen(style.ACCENT)
        p.setFont(style.icon_font(15))
        p.drawText(QRectF(10, 0, 36, r.height()), Qt.AlignmentFlag.AlignCenter, self._icon)
        right = r.width() - 14
        if self.isCheckable():
            _paint_switch(p, QRectF(right - 46, (r.height() - 26) / 2, 46, 26), 1.0 if self.isChecked() else 0.0)
            right -= 58
        elif self._hint:
            p.setPen(style.TEXT_FAINT)
            p.setFont(style.ui_font(11))
            hint_w = p.fontMetrics().horizontalAdvance(self._hint)
            p.drawText(QRectF(right - hint_w, 0, hint_w, r.height()), Qt.AlignmentFlag.AlignVCenter, self._hint)
            right -= hint_w + 12
        p.setPen(style.TEXT)
        p.setFont(style.ui_font(13.5))
        p.drawText(QRectF(56, 0, right - 56, r.height()), Qt.AlignmentFlag.AlignVCenter, self.text())
        p.end()


class MenuPanel(QWidget):
    """Menú emergente grande y claro: secciones con título, filas con icono y una fila de botones al pie."""

    def __init__(self, parent: QWidget | None = None):
        flags = Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint
        super().__init__(parent, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 10, 16, 22)
        self.frame = QFrame(self)
        self.frame.setObjectName("panel")
        add_shadow(self.frame, blur=30, dy=6, alpha=60)
        outer.addWidget(self.frame)
        self.body = QVBoxLayout(self.frame)
        self.body.setContentsMargins(8, 10, 8, 10)
        self.body.setSpacing(0)
        self.rows: list[MenuRow] = []

    def add_section(self, title: str) -> None:
        if self.body.count():
            self.add_separator()
        label = QLabel(title.upper())
        label.setProperty("heading", True)
        label.setFont(style.ui_font(10, QFont.Weight.DemiBold))
        label.setContentsMargins(14, 4, 0, 4)
        self.body.addWidget(label)

    def add_separator(self) -> None:
        line = QFrame()
        line.setObjectName("separator")
        self.body.addSpacing(6)
        self.body.addWidget(line)
        self.body.addSpacing(6)

    def add_row(self, icon: str, text: str, slot, hint: str = "", toggle: bool | None = None) -> MenuRow:
        row = MenuRow(icon, text, hint, toggle)
        if toggle is None:
            row.clicked.connect(lambda: self._run(slot))
        else:
            row.toggled.connect(slot)  # el interruptor no cierra el panel: así se ve el cambio
        self.body.addWidget(row)
        self.rows.append(row)
        return row

    def add_tiles(self, tiles: list[tuple[str, str, object]]) -> None:
        self.add_separator()
        line = QHBoxLayout()
        line.setSpacing(4)
        for icon, text, slot in tiles:
            b = IconButton(icon, text)
            b.clicked.connect(lambda _c=False, slot=slot: self._run(slot))
            line.addWidget(b, 1)
            self.rows.append(b)
        self.body.addLayout(line)

    def add_note(self, text: str) -> None:
        label = QLabel(text)
        label.setProperty("soft", True)
        label.setFont(style.ui_font(11))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        label.setContentsMargins(10, 8, 10, 0)
        self.body.addWidget(label)

    def texts(self) -> list[str]:
        return [r.text() for r in self.rows]

    def _run(self, slot) -> None:
        self.close()
        QTimer.singleShot(0, slot)  # los diálogos se abren con el panel ya cerrado

    def popup_under(self, widget: QWidget) -> None:
        """Se abre debajo del botón, alineado con su borde derecho y sin salirse de la pantalla."""
        self.setFixedWidth(420)
        self.adjustSize()
        anchor = widget.mapToGlobal(widget.rect().bottomRight())
        screen = widget.screen().availableGeometry()
        x = max(screen.left(), min(anchor.x() - self.width() + 16, screen.right() - self.width()))
        y = max(screen.top(), min(anchor.y() - 4, screen.bottom() - self.height()))
        self.move(x, y)
        self.show()


# -- diálogo con letra grande -----------------------------------------------------------------------------------------


class FriendlyDialog(QDialog):
    """Pregunta o aviso con letra grande y botones claros. `exec()` devuelve el índice del botón pulsado."""

    def __init__(self, parent: QWidget | None, title: str, text: str, buttons: list[str], primary: int = 0,
                 icon: str = style.ICON_HELP, icon_color: str = "ACCENT"):
        super().__init__(parent)
        self.setWindowTitle("Dictador")
        self.setModal(True)
        self.setProperty("surface", True)
        self._choice = -1
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 30, 36, 26)
        layout.setSpacing(14)
        head = QHBoxLayout()
        head.addWidget(Badge(icon, icon_color, 52))
        head.addSpacing(10)
        heading = QLabel(title)
        heading.setFont(style.display_font(19))
        heading.setWordWrap(True)
        head.addWidget(heading, 1)
        layout.addLayout(head)
        body = QLabel(text)
        body.setFont(style.ui_font(14))
        body.setWordWrap(True)
        body.setProperty("soft", True)
        body.setMinimumWidth(460)
        layout.addWidget(body)
        layout.addSpacing(10)
        row = QHBoxLayout()
        row.addStretch()
        for i, label in enumerate(buttons):
            b = QPushButton(label)
            if i == primary:
                b.setProperty("primary", True)
                b.setDefault(True)
            b.clicked.connect(lambda _c=False, i=i: self._pick(i))
            row.addWidget(b)
        layout.addLayout(row)

    def _pick(self, i: int) -> None:
        self._choice = i
        self.accept()

    def exec(self) -> int:  # type: ignore[override]
        super().exec()
        return self._choice


def ask(parent, title: str, text: str, buttons: list[str], primary: int = 0, **kw) -> int:
    return FriendlyDialog(parent, title, text, buttons, primary, **kw).exec()


def tell(parent, title: str, text: str, warning: bool = False) -> None:
    kw = {"icon": style.ICON_WARNING, "icon_color": "WARNING"} if warning else {"icon": style.ICON_IDEA}
    FriendlyDialog(parent, title, text, [tr("Entendido")], **kw).exec()
