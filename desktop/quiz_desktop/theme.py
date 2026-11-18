"""Оформление приложения: светлая и тёмная темы.

Вся внешность собрана здесь в одной таблице стилей (QSS, это CSS для Qt),
а экраны только называют роль виджета: кнопка «основная», подпись «ошибка».
Так оформление меняется в одном месте, а тема переключается на лету.

    set_variant(button, "primary")   # кнопка с акцентной заливкой
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
    surface_alt: str  # вторичные кнопки, дорожка индикатора
    hover: str
    border: str
    text: str
    muted: str  # второстепенный текст
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_text: str  # текст на акцентной заливке
    accent_soft: str  # мягкая подсветка: выбранная строка, бейдж
    accent_disabled: str
    danger: str
    danger_soft: str
    success: str
    warning: str
    hero_from: str  # градиент шапки
    hero_to: str
    shadow: str  # цвет тени карточек, «r,g,b,a»


LIGHT = Palette(
    name="light",
    bg="#F3F4FB",
    surface="#FFFFFF",
    surface_alt="#ECEEF8",
    hover="#E2E5F4",
    border="#DADDEE",
    text="#1D2040",
    muted="#666B8F",
    accent="#5B4CF0",
    accent_hover="#4C3DDC",
    accent_pressed="#4030C0",
    accent_text="#FFFFFF",
    accent_soft="#E7E5FF",
    accent_disabled="#B9B3F6",
    danger="#D92D3A",
    danger_soft="#FDECEE",
    success="#128A4A",
    warning="#B26A00",
    hero_from="#5B4CF0",
    hero_to="#B24CE6",
    shadow="30,30,90,38",
)

DARK = Palette(
    name="dark",
    bg="#0F101B",
    surface="#191B2D",
    surface_alt="#23263C",
    hover="#2C3050",
    border="#2F3354",
    text="#ECEEFF",
    muted="#9A9FC8",
    accent="#7364FF",
    accent_hover="#8678FF",
    accent_pressed="#6355EE",
    accent_text="#FFFFFF",
    accent_soft="#2A2766",
    accent_disabled="#4B4687",
    danger="#FF6B73",
    danger_soft="#3B1D27",
    success="#3DD68C",
    warning="#F5B544",
    hero_from="#4338CA",
    hero_to="#9333EA",
    shadow="0,0,0,110",
)

# Цвета вариантов ответа, как в Kahoot: по цвету вариант легко найти и у себя,
# и на экране ведущего. Одинаковы в обеих темах: на них всегда белый текст.
OPTION_COLORS = ["#EE4258", "#2F7BEA", "#D98A00", "#1F9D55"]
OPTION_MUTED = "#8E93B3"  # невыбранные варианты после ответа

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

/* ---------- карточки и шапка ---------- */
QFrame#card {
    background: $surface; border: 1px solid $border; border-radius: 18px;
}
QFrame#hero {
    border: none; border-radius: 24px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 $hero_from, stop:1 $hero_to);
}

/* ---------- подписи ---------- */
QLabel[role="title"] { font-size: 30px; font-weight: 700; }
QLabel[role="h1"] { font-size: 24px; font-weight: 700; }
QLabel[role="h2"] { font-size: 17px; font-weight: 600; }
QLabel[role="muted"] { color: $muted; }
QLabel[role="section"] { color: $muted; font-size: 12px; font-weight: 700; }
QLabel[role="error"] { color: $danger; }
QLabel[role="success"] { color: $success; }
QLabel[role="title-success"] { font-size: 34px; font-weight: 800; color: $success; }
QLabel[role="title-error"] { font-size: 34px; font-weight: 800; color: $danger; }
QLabel[role="hero-title"] { color: white; font-size: 36px; font-weight: 800; }
QLabel[role="hero-text"] { color: rgba(255,255,255,222); font-size: 16px; }
QLabel[role="badge"] {
    background: $accent_soft; color: $accent; border-radius: 9px;
    padding: 3px 12px; font-weight: 600;
}
QLabel[role="code"] {
    color: $accent; font-size: 72px; font-weight: 800;
    background: $accent_soft; border-radius: 22px; padding: 6px 28px;
}
QLabel[role="icon"] {
    background: $accent_soft; border-radius: 18px; font-size: 28px;
    min-width: 60px; max-width: 60px; min-height: 60px; max-height: 60px;
}
QLabel[role="pill"] {
    background: rgba(255,255,255,48); color: white; border-radius: 12px;
    padding: 4px 14px; font-weight: 600;
}
QLabel[role="timer"] { font-size: 44px; font-weight: 800; color: $accent; }
QLabel[role="timer"][low="true"] { color: $danger; }

/* ---------- кнопки ---------- */
QPushButton {
    background: $surface; color: $text; border: 1px solid $border;
    border-radius: 11px; padding: 9px 18px; font-weight: 600;
}
QPushButton:hover { background: $hover; }
QPushButton:pressed { background: $border; }
QPushButton:disabled { color: $muted; background: $surface_alt; border-color: $surface_alt; }
QPushButton[variant="primary"] {
    background: $accent; color: $accent_text; border: 1px solid $accent;
}
QPushButton[variant="primary"]:hover { background: $accent_hover; border-color: $accent_hover; }
QPushButton[variant="primary"]:pressed { background: $accent_pressed; border-color: $accent_pressed; }
QPushButton[variant="primary"]:disabled {
    background: $accent_disabled; color: $accent_text; border-color: $accent_disabled;
}
QPushButton[variant="danger"] { color: $danger; border: 1px solid $danger; background: transparent; }
QPushButton[variant="danger"]:hover { background: $danger_soft; }
QPushButton[variant="danger"]:disabled { color: $muted; border-color: $border; background: transparent; }
QPushButton[variant="ghost"] { background: transparent; border: none; color: $muted; }
QPushButton[variant="ghost"]:hover { background: $hover; color: $text; }
QPushButton[variant="link"] { background: transparent; border: none; color: $accent; padding: 6px 8px; }
QPushButton[variant="link"]:hover { background: $accent_soft; }
QPushButton:focus { outline: none; }

QToolButton {
    background: $surface_alt; color: $text; border: 1px solid $border;
    border-radius: 9px; padding: 6px 11px; font-weight: 700;
}
QToolButton:hover { background: $hover; }
QToolButton:disabled { color: $muted; background: transparent; border-color: transparent; }

/* ---------- поля ввода ---------- */
QLineEdit, QPlainTextEdit {
    background: $surface; color: $text; border: 1px solid $border; border-radius: 11px;
    padding: 9px 12px; selection-background-color: $accent; selection-color: $accent_text;
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
QRadioButton::indicator:hover { border-color: $accent; }
QRadioButton::indicator:checked {
    border: 2px solid $accent;
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
        stop:0 $accent, stop:0.5 $accent, stop:0.6 $surface, stop:1 $surface);
}

/* ---------- таблицы и списки ---------- */
QTableWidget, QListWidget {
    background: $surface; border: 1px solid $border; border-radius: 14px;
    outline: 0; selection-background-color: $accent_soft; selection-color: $text;
}
QListWidget { padding: 6px; }
QListWidget::item { padding: 10px 12px; border-radius: 9px; margin: 1px 0; }
QListWidget::item:selected { background: $accent_soft; color: $text; }
QListWidget::item:hover:!selected { background: $surface_alt; }
QTableWidget { gridline-color: transparent; }
QTableWidget::item { padding: 10px 12px; border-bottom: 1px solid $border; }
QTableWidget::item:selected { background: $accent_soft; color: $text; }
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

QProgressBar { background: $surface_alt; border: none; border-radius: 6px; min-height: 14px; max-height: 14px; }
QProgressBar::chunk { background: $accent; border-radius: 6px; }
QProgressBar[low="true"]::chunk { background: $danger; }

QSplitter::handle { background: transparent; }

/* ---------- меню и строка состояния ---------- */
QMenuBar { background: $surface; border-bottom: 1px solid $border; padding: 3px 6px; }
QMenuBar::item { background: transparent; padding: 6px 12px; border-radius: 8px; }
QMenuBar::item:selected { background: $accent_soft; }
QMenu { background: $surface; border: 1px solid $border; border-radius: 12px; padding: 6px; }
QMenu::item { padding: 8px 26px 8px 14px; border-radius: 8px; }
QMenu::item:selected { background: $accent_soft; }
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
    (например, текст в стандартных диалогах)."""
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
        (QPalette.ColorRole.Highlight, p.accent),
        (QPalette.ColorRole.HighlightedText, p.accent_text),
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
    """Роль подписи: title, h1, h2, muted, section, error, success, badge, code, timer."""
    widget.setProperty("role", role)
    repolish(widget)
    return widget


def set_variant(button: QWidget, variant: str) -> QWidget:
    """Вид кнопки: primary, danger, ghost, link (без вида — обычная)."""
    button.setProperty("variant", variant)
    repolish(button)
    return button
