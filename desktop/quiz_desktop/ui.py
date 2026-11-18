"""Общие кирпичики интерфейса: карточка и логотип."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QWidget

from quiz_desktop import theme


def card(parent: QWidget | None = None, shadow: bool = True) -> QFrame:
    """Белая карточка со скруглением и мягкой тенью (стиль — theme.py, QFrame#card)."""
    frame = QFrame(parent)
    frame.setObjectName("card")
    if shadow:
        effect = QGraphicsDropShadowEffect(frame)
        effect.setBlurRadius(36)
        effect.setOffset(0, 8)
        r, g, b, a = (int(x) for x in theme.palette().shadow.split(","))
        effect.setColor(QColor(r, g, b, a))
        frame.setGraphicsEffect(effect)
    return frame


class LogoMark(QWidget):
    """Логотип: скруглённый квадрат с градиентом и знаком вопроса.
    inverted — белый квадрат: для цветной шапки, где градиент слился бы с фоном."""

    def __init__(self, size: int = 56, inverted: bool = False):
        super().__init__()
        self._inverted = inverted
        self.setFixedSize(size, size)

    def paintEvent(self, event) -> None:
        p = theme.palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(rect, rect.width() * 0.3, rect.height() * 0.3)
        if self._inverted:
            painter.fillPath(path, QColor("white"))
            glyph = QColor(p.hero_from)
        else:
            gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
            gradient.setColorAt(0, QColor(p.hero_from))
            gradient.setColorAt(1, QColor(p.hero_to))
            painter.fillPath(path, gradient)
            glyph = QColor("white")

        font = QFont()
        font.setFamilies(theme.FONT_FAMILIES)
        font.setBold(True)
        font.setPixelSize(int(rect.height() * 0.62))
        painter.setFont(font)
        painter.setPen(glyph)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "?")
