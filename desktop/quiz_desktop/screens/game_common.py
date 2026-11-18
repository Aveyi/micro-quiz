"""Общие виджеты экранов игры (игрок и ведущий): таймер, варианты, таблица."""

from PySide6.QtCore import QElapsedTimer, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from quiz_desktop.theme import OPTION_COLORS, OPTION_MUTED, repolish, set_role

# Цвета вариантов, как в Kahoot (OPTION_COLORS в theme.py): по цвету вариант
# легко найти и на экране ведущего, и у себя.

# Медали первой тройки в таблице лидеров: золото, серебро, бронза.
MEDAL_COLORS = {1: "#F5B301", 2: "#A7AEC8", 3: "#C9824B"}

# Сообщения room_closed (раздел 4.4).
ROOM_CLOSED_REASONS = {
    "host_left": "Ведущий вышел, игра прервана",
    "lobby_timeout": "Игра так и не началась: лобби закрыто через 30 минут",
    "server_shutdown": "Сервер перезапускается, игра прервана",
}


def big_label(text: str = "", size: int = 18, bold: bool = True, role: str | None = None) -> QLabel:
    """Подпись по центру. role (theme.py) задаёт оформление темой, а не размером шрифта."""
    label = QLabel(text)
    font = QFont()
    font.setPointSize(size)
    font.setBold(bold)
    label.setFont(font)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)
    if role:
        set_role(label, role)
    return label


LOW_TIME_MS = 5000


class Countdown(QWidget):
    """Обратный отсчёт вопроса. Решающий таймер — на сервере (раздел 4.4),
    этот только показывает, сколько осталось. Считаем от момента получения
    вопроса по QElapsedTimer — монотонным часам, как и на сервере."""

    expired = Signal()

    def __init__(self):
        super().__init__()
        self._label = big_label(size=28, role="timer")
        self._bar = QProgressBar()
        self._bar.setTextVisible(False)
        self._clock = QElapsedTimer()
        self._limit_ms = 0
        self._tick = QTimer(self)
        self._tick.setInterval(100)
        self._tick.timeout.connect(self._update)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)
        layout.addWidget(self._bar)

    def start(self, seconds: int) -> None:
        self._limit_ms = seconds * 1000
        self._set_low(False)
        self._bar.setRange(0, self._limit_ms)
        self._clock.start()
        self._tick.start()
        self._update()

    def stop(self) -> None:
        self._tick.stop()

    def remaining_ms(self) -> int:
        return max(0, self._limit_ms - self._clock.elapsed())

    def _set_low(self, low: bool) -> None:
        if (self._label.property("low") == "true") == low:
            return
        for widget in (self._label, self._bar):
            widget.setProperty("low", "true" if low else "false")
            repolish(widget)

    def _update(self) -> None:
        left = self.remaining_ms()
        self._bar.setValue(left)
        # Последние 5 секунд полоса и цифры краснеют.
        self._set_low(left <= LOW_TIME_MS)
        # Округляем вверх: «1» на экране до самого конца последней секунды.
        self._label.setText(str((left + 999) // 1000))
        if left == 0:
            self._tick.stop()
            self.expired.emit()


class OptionButtons(QWidget):
    """Цветные кнопки вариантов, сеткой 2×2."""

    chosen = Signal(int)  # option_id

    def __init__(self):
        super().__init__()
        self._grid = QGridLayout(self)
        self.buttons: dict[int, QPushButton] = {}

    def set_options(self, options: list[dict]) -> None:
        for button in self.buttons.values():
            button.deleteLater()
        self.buttons = {}
        for i, option in enumerate(options):
            button = QPushButton(option["text"])
            button.setMinimumHeight(84)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            font = button.font()
            font.setPointSize(16)
            button.setFont(font)
            self._paint(button, OPTION_COLORS[i % len(OPTION_COLORS)])
            option_id = option["option_id"]
            button.clicked.connect(lambda _=False, oid=option_id: self.chosen.emit(oid))
            self._grid.addWidget(button, i // 2, i % 2)
            self.buttons[option_id] = button

    def lock(self, chosen: int | None = None) -> None:
        """Ответ дан или время вышло: варианты больше не нажимаются.
        Выбранный остаётся ярким, остальные бледнеют."""
        for option_id, button in self.buttons.items():
            button.setEnabled(False)
            if chosen is not None and option_id != chosen:
                self._paint(button, OPTION_MUTED)

    @staticmethod
    def _paint(button: QPushButton, color: str) -> None:
        base = QColor(color)
        button.setStyleSheet(
            f"QPushButton {{ background: {color}; color: white; border: none; border-radius: 16px;"
            f" padding: 12px 18px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: {base.lighter(112).name()}; }}"
            f"QPushButton:pressed {{ background: {base.darker(115).name()}; }}"
            f"QPushButton:disabled {{ background: {color}; color: white; }}"
        )


def _medal_icon(rank: int) -> QIcon:
    """Цветной кружок для первой тройки; у остальных пустое место того же размера,
    чтобы все строки таблицы были выровнены."""
    pixmap = QPixmap(18, 18)
    pixmap.fill(Qt.GlobalColor.transparent)
    color = MEDAL_COLORS.get(rank)
    if color:
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawEllipse(1, 1, 16, 16)
        painter.end()
    return QIcon(pixmap)


class Leaderboard(QListWidget):
    """Таблица лидеров: «1. Вася — 1840». Свою строку выделяем жирным,
    первую тройку — цветной медалью."""

    def __init__(self):
        super().__init__()
        self.setIconSize(QSize(18, 18))

    def show_entries(self, entries: list[dict], me: int | None = None) -> None:
        self.clear()
        for e in entries:
            text = f"{e['rank']}. {e['nickname']} — {e['score']}"
            if e.get("left"):
                text += " (выбыл)"
            item = QListWidgetItem(_medal_icon(e["rank"]), text)
            if e["player_id"] == me:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            self.addItem(item)


class AnswerStats(QWidget):
    """Распределение ответов для ведущего: полоса на каждый вариант,
    правильный отмечен галочкой."""

    def __init__(self):
        super().__init__()
        self._layout = QVBoxLayout(self)
        self.rows: dict[int, tuple[QLabel, QProgressBar]] = {}

    def show_counts(self, options: list[dict], counts: dict[str, int], correct_id: int) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.layout():
                while item.layout().count():
                    item.layout().takeAt(0).widget().deleteLater()
        self.rows = {}
        total = max(1, sum(counts.values()))
        for i, option in enumerate(options):
            oid = option["option_id"]
            count = counts.get(str(oid), 0)  # ключи в JSON — строки (раздел 4.4)
            mark = "  ✓" if oid == correct_id else ""
            label = QLabel(f"{option['text']}{mark} — {count}")
            label.setMinimumWidth(220)
            if oid == correct_id:
                font = label.font()
                font.setBold(True)
                label.setFont(font)
            bar = QProgressBar()
            bar.setRange(0, total)
            bar.setValue(count)
            bar.setTextVisible(False)
            color = OPTION_COLORS[i % len(OPTION_COLORS)]
            bar.setStyleSheet(f"QProgressBar::chunk {{ background: {color}; }}")
            row = QHBoxLayout()
            row.addWidget(label)
            row.addWidget(bar, stretch=1)
            self._layout.addLayout(row)
            self.rows[oid] = (label, bar)
