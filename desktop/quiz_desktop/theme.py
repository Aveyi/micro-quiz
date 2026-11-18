"""Оформление приложения: светлая и тёмная темы.

Стиль сдержанный, «журнальный»: тёплая бумажная основа, чёрные чернила для текста
и главных кнопок и один акцентный цвет (киноварь) для важных деталей. Без градиентов,
теней и декоративных значков: порядок строят отступы, тонкие линии и размер шрифта.

Весь вид собран здесь в одной таблице стилей (QSS, это CSS для Qt), а экраны только
называют роль виджета: кнопка «основная», подпись «ошибка»:

    set_variant(button, "primary")   # чёрная кнопка
    set_role(label, "error")         # красная подпись
"""

from dataclasses import dataclass
from string import Template

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QWidget

# Варианты выбора темы в меню. «auto» — как в системе.
THEME_MODES = ("auto", "light", "dark")

# Шрифты по приоритету: Segoe UI есть в Windows, SF Pro — в macOS.
FONT_FAMILIES = ["Segoe UI", "SF Pro Text", "Helvetica Neue", "Arial"]


@dataclass(frozen=True)
class Palette:
    name: str
    bg: str  # фон окна
    surface: str  # карточки, поля ввода, таблицы
    surface_alt: str  # вторичные заливки, дорожка индикатора
    hover: str
    border: str
    text: str  # «чернила»
    muted: str  # второстепенный текст
    accent: str  # единственный яркий цвет: фокус, ссылки, срочное
    selection: str  # заливка выбранной строки в таблицах и списках
    primary: str  # заливка главных кнопок
    primary_hover: str
    primary_pressed: str
    primary_disabled: str
    primary_text: str  # текст на главных кнопках
    danger: str
    danger_soft: str
    success: str
    warning: str


LIGHT = Palette(
    name="light",
    bg="#F4F1EA",
    surface="#FCFBF8",
    surface_alt="#ECE8DE",
    hover="#E3DED1",
    border="#D8D3C6",
    text="#1B1B1F",
    muted="#6F6A5F",
    accent="#D9482B",
    selection="#E8E2D3",
    primary="#1B1B1F",
    primary_hover="#33333A",
    primary_pressed="#000000",
    primary_disabled="#A9A59B",
    primary_text="#FCFBF8",
    danger="#B3261E",
    danger_soft="#F7E1DE",
    success="#1F7A4D",
    warning="#946300",
)

DARK = Palette(
    name="dark",
    bg="#121214",
    surface="#1B1B1F",
    surface_alt="#26262B",
    hover="#303036",
    border="#34343B",
    text="#ECE9E2",
    muted="#9C978B",
    accent="#FF6B4A",
    selection="#2C2C33",
    primary="#ECE9E2",
    primary_hover="#FFFFFF",
    primary_pressed="#CFCBC2",
    primary_disabled="#55524B",
    primary_text="#121214",
    danger="#FF7A72",
    danger_soft="#3C1F1D",
    success="#4FD08A",
    warning="#E7B04A",
)

# Цвета вариантов ответа: по цвету и букве вариант легко найти и у себя, и на экране
# ведущего. Приглушённые, но различимые; одинаковы в обеих темах, на них всегда белый текст.
OPTION_COLORS = ["#D9482B", "#2F5DA8", "#B7800F", "#2E7D5B"]
OPTION_LETTERS = "ABCD"
OPTION_MUTED = "#8C897F"  # невыбранные варианты после ответа

# Медали первой тройки в таблице лидеров: золото, серебро, бронза.
MEDAL_COLORS = {1: "#C9A227", 2: "#9AA0A6", 3: "#A8703E"}

_STYLESHEET = Template(
    """
/* ---------- общее ---------- */
QMainWindow, QDialog, QMessageBox { background: $bg; }
QStackedWidget#root { background: $bg; }
QWidget { color: $text; }
QLabel { background: transparent; }
QToolTip {
    background: $surface; color: $text; border: 1px solid $border;
    border-radius: 6px; padding: 6px 8px;
}

/* ---------- карточки ---------- */
QFrame#card {
    background: $surface; border: 1px solid $border; border-radius: 14px;
}

/* ---------- подписи ---------- */
QLabel[role="display"] { font-size: 40px; font-weight: 800; }
QLabel[role="title"] { font-size: 30px; font-weight: 800; }
QLabel[role="h1"] { font-size: 24px; font-weight: 700; }
QLabel[role="h2"] { font-size: 17px; font-weight: 600; }
QLabel[role="lead"] { color: $muted; font-size: 16px; }
QLabel[role="muted"] { color: $muted; }
QLabel[role="section"] { color: $muted; font-size: 12px; font-weight: 700; }
QLabel[role="brand"] { font-size: 16px; font-weight: 700; }
QLabel[role="index"] { color: $accent; font-size: 13px; font-weight: 700; }
QLabel[role="error"] { color: $danger; }
QLabel[role="success"] { color: $success; }
QLabel[role="title-success"] { font-size: 34px; font-weight: 800; color: $success; }
QLabel[role="title-error"] { font-size: 34px; font-weight: 800; color: $danger; }
QLabel[role="code"] {
    color: $text; font-size: 72px; font-weight: 800;
    background: $surface; border: 2px solid $text; border-radius: 16px; padding: 4px 30px;
}
QLabel[role="timer"] { font-size: 44px; font-weight: 800; }
QLabel[role="timer"][low="true"] { color: $accent; }

/* ---------- кнопки ---------- */
QPushButton {
    background: $surface; color: $text; border: 1px solid $border;
    border-radius: 9px; padding: 9px 18px; font-weight: 600;
}
QPushButton:hover { background: $surface_alt; }
QPushButton:pressed { background: $hover; }
QPushButton:disabled { color: $muted; background: $surface_alt; border-color: $surface_alt; }
QPushButton[variant="primary"] {
    background: $primary; color: $primary_text; border: 1px solid $primary;
}
QPushButton[variant="primary"]:hover { background: $primary_hover; border-color: $primary_hover; }
QPushButton[variant="primary"]:pressed { background: $primary_pressed; border-color: $primary_pressed; }
QPushButton[variant="primary"]:disabled {
    background: $primary_disabled; color: $primary_text; border-color: $primary_disabled;
}
QPushButton[variant="danger"] { color: $danger; border: 1px solid $danger; background: transparent; }
QPushButton[variant="danger"]:hover { background: $danger_soft; }
QPushButton[variant="danger"]:disabled { color: $muted; border-color: $border; background: transparent; }
QPushButton[variant="ghost"] { background: transparent; border: none; color: $muted; }
QPushButton[variant="ghost"]:hover { background: $surface_alt; color: $text; }
QPushButton[variant="link"] { background: transparent; border: none; color: $accent; padding: 6px 8px; }
QPushButton[variant="link"]:hover { background: $selection; }
QPushButton:focus { outline: none; }

QToolButton {
    background: $surface; color: $text; border: 1px solid $border;
    border-radius: 9px; padding: 6px 11px; font-weight: 700;
}
QToolButton:hover { background: $surface_alt; }
QToolButton:disabled { color: $muted; background: transparent; border-color: transparent; }

/* ---------- поля ввода ---------- */
QLineEdit, QPlainTextEdit {
    background: $surface; color: $text; border: 1px solid $border; border-radius: 9px;
    padding: 9px 12px; selection-background-color: $text; selection-color: $surface;
}
QLineEdit:focus, QPlainTextEdit:focus { border: 2px solid $accent; padding: 8px 11px; }
QLineEdit:disabled { background: $surface_alt; color: $muted; }
/* QSpinBox намеренно без своих правил: Qt вычисляет для него область ввода по родной теме,
   и с отступами из таблицы стилей поле ввода схлопывается. Он рисуется палитрой (Fusion). */

QRadioButton { spacing: 8px; background: transparent; }
QRadioButton::indicator {
    width: 18px; height: 18px; border-radius: 10px;
    border: 2px solid $border; background: $surface;
}
QRadioButton::indicator:hover { border-color: $text; }
QRadioButton::indicator:checked {
    border: 2px solid $accent;
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
        stop:0 $accent, stop:0.5 $accent, stop:0.6 $surface, stop:1 $surface);
}

/* ---------- таблицы и списки ---------- */
QTableWidget, QListWidget {
    background: $surface; border: 1px solid $border; border-radius: 12px;
    outline: 0; selection-background-color: $selection; selection-color: $text;
}
QListWidget { padding: 6px; }
QListWidget::item { padding: 10px 12px; border-radius: 8px; margin: 1px 0; }
QListWidget::item:selected { background: $selection; color: $text; }
QListWidget::item:hover:!selected { background: $surface_alt; }
QTableWidget { gridline-color: transparent; }
QTableWidget::item { padding: 10px 12px; border-bottom: 1px solid $border; }
QTableWidget::item:selected { background: $selection; color: $text; }
QHeaderView { background: transparent; }
QHeaderView::section {
    background: transparent; color: $muted; border: none; border-bottom: 1px solid $border;
    padding: 10px 12px; font-weight: 700;
}
QTableCornerButton::section { background: transparent; border: none; }

QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical { background: $border; border-radius: 4px; min-height: 36px; }
QScrollBar::handle:vertical:hover { background: $muted; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px; }
QScrollBar::handle:horizontal { background: $border; border-radius: 4px; min-width: 36px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QProgressBar { background: $surface_alt; border: none; border-radius: 3px; min-height: 8px; max-height: 8px; }
QProgressBar::chunk { background: $text; border-radius: 3px; }
QProgressBar[low="true"]::chunk { background: $accent; }

QSplitter::handle { background: transparent; }

/* ---------- меню и строка состояния ---------- */
QMenuBar { background: $surface; border-bottom: 1px solid $border; padding: 3px 6px; }
QMenuBar::item { background: transparent; padding: 6px 12px; border-radius: 7px; }
QMenuBar::item:selected { background: $surface_alt; }
QMenu { background: $surface; border: 1px solid $border; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 8px 26px 8px 14px; border-radius: 7px; }
QMenu::item:selected { background: $surface_alt; }
QMenu::item:disabled { color: $muted; }
QMenu::separator { height: 1px; background: $border; margin: 6px 8px; }
QStatusBar { background: $surface; border-top: 1px solid $border; color: $muted; }
QStatusBar::item { border: none; }
QStatusBar QLabel { color: $muted; }
"""
)

_current: Palette = LIGHT


def palette() -> Palette:
    """Палитра применённой сейчас темы (нужна коду, который красит элементы сам)."""
    return _current


def stylesheet(p: Palette) -> str:
    return _STYLESHEET.substitute(vars(p))


def resolve_mode(mode: str, app: QApplication | None = None) -> Palette:
    """Какую палитру показывать: «auto» следует за темой системы."""
    if mode == "dark":
        return DARK
    if mode == "light":
        return LIGHT
    app = app or QApplication.instance()
    scheme = app.styleHints().colorScheme() if app else Qt.ColorScheme.Light
    return DARK if scheme == Qt.ColorScheme.Dark else LIGHT


def _qpalette(p: Palette) -> QPalette:
    """Палитра Qt для частей интерфейса, которые таблица стилей не красит
    (например, текст в стандартных диалогах и поле времени на ответ)."""
    qp = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, p.bg),
        (QPalette.ColorRole.WindowText, p.text),
        (QPalette.ColorRole.Base, p.surface),
        (QPalette.ColorRole.AlternateBase, p.surface_alt),
        (QPalette.ColorRole.Text, p.text),
        (QPalette.ColorRole.Button, p.surface),
        (QPalette.ColorRole.ButtonText, p.text),
        (QPalette.ColorRole.ToolTipBase, p.surface),
        (QPalette.ColorRole.ToolTipText, p.text),
        (QPalette.ColorRole.PlaceholderText, p.muted),
        (QPalette.ColorRole.Highlight, p.text),
        (QPalette.ColorRole.HighlightedText, p.surface),
    ):
        qp.setColor(role, QColor(color))
    return qp


def apply_theme(app: QApplication, mode: str = "auto") -> Palette:
    """Применяет тему ко всему приложению; можно вызывать повторно."""
    global _current
    p = resolve_mode(mode, app)
    _current = p
    # Fusion одинаково выглядит на всех системах, и таблица стилей
    # ложится на него предсказуемо.
    app.setStyle("Fusion")
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPointSize(10)
    app.setFont(font)
    app.setPalette(_qpalette(p))
    app.setStyleSheet(stylesheet(p))
    return p


# ---------- помощники для экранов ----------


def repolish(widget: QWidget) -> None:
    """Заставляет Qt заново применить стили после смены свойства виджета."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def set_role(widget: QWidget, role: str) -> QWidget:
    """Роль подписи: display, title, h1, h2, lead, muted, section, brand, index,
    error, success, code, timer, title-success, title-error."""
    widget.setProperty("role", role)
    repolish(widget)
    return widget


def set_variant(button: QWidget, variant: str) -> QWidget:
    """Вид кнопки: primary, danger, ghost, link (без вида — обычная)."""
    button.setProperty("variant", variant)
    repolish(button)
    return button
