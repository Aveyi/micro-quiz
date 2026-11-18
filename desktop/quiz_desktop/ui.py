"""Общие кирпичики интерфейса: карточка и логотип."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QWidget

from quiz_desktop import theme


def card(parent: QWidget | None = None) -> QFrame:
    """Карточка: светлая поверхность с тонкой рамкой и скруглением (стиль — theme.py, QFrame#card)."""
    frame = QFrame(parent)
    frame.setObjectName("card")
    return frame


class LogoMark(QWidget):
    """Логотип: квадрат цвета «чернил» с буквой Q — белое кольцо и киноварный хвостик."""

    def __init__(self, size: int = 40):
        super().__init__()
        self.setFixedSize(size, size)

    def paintEvent(self, event) -> None:
        p = theme.palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        side = rect.width()

        # В тёмной теме квадрат светлый, как и главные кнопки: логотип всегда контрастен фону.
        path = QPainterPath()
        path.addRoundedRect(rect, side * 0.24, side * 0.24)
        painter.fillPath(path, QColor(p.primary))

        center = QPointF(rect.center().x() - side * 0.03, rect.center().y() - side * 0.03)
        radius = side * 0.23
        painter.setPen(QPen(QColor(p.primary_text), side * 0.1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(center, radius, radius)

        tail = QPen(QColor(p.accent), side * 0.1)
        tail.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(tail)
        painter.drawLine(
            QPointF(center.x() + radius * 0.5, center.y() + radius * 0.5),
            QPointF(center.x() + radius * 1.3, center.y() + radius * 1.3),
        )
