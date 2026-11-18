"""Оформление: таблица стилей, тёмная и светлая темы, переключение в меню."""

import pytest
from PySide6.QtCore import QSize, qInstallMessageHandler
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton

from quiz_desktop import theme
from quiz_desktop.main_window import MainWindow
from quiz_desktop.screens.game_common import Countdown, Leaderboard, OptionButtons
from quiz_desktop.theme import DARK, LIGHT, apply_theme, set_role, set_variant


@pytest.fixture(autouse=True)
def reset_theme(qapp):
    """Тема меняет настройки всего приложения — после теста возвращаем как было,
    чтобы остальные тесты шли без таблицы стилей. qapp: приложение Qt от pytest-qt."""
    yield
    qapp.setStyleSheet("")
    theme._current = LIGHT


@pytest.fixture
def qt_messages():
    """Предупреждения Qt (например, «Could not parse stylesheet») собираются в список."""
    messages = []
    previous = qInstallMessageHandler(lambda mode, context, message: messages.append(message))
    yield messages
    qInstallMessageHandler(previous)


@pytest.mark.parametrize("palette", [LIGHT, DARK], ids=lambda p: p.name)
def test_stylesheet_is_valid(qt_messages, palette):
    css = theme.stylesheet(palette)
    assert "$" not in css  # все подстановки выполнены
    app = QApplication.instance()
    app.setStyleSheet(css)
    # Qt разбирает стили при первом применении к виджету.
    button = QPushButton("проверка")
    set_variant(button, "primary")
    button.show()
    button.ensurePolished()
    problems = [m for m in qt_messages if "stylesheet" in m.lower() or "unknown property" in m.lower()]
    assert problems == []


def test_palettes_have_all_colors():
    for p in (LIGHT, DARK):
        for name, value in vars(p).items():
            assert value, f"{p.name}: пустое значение {name}"


@pytest.mark.parametrize("mode, expected", [("light", LIGHT), ("dark", DARK)])
def test_apply_theme(mode, expected):
    assert apply_theme(QApplication.instance(), mode) is expected
    assert theme.palette() is expected
    assert QApplication.instance().styleSheet() == theme.stylesheet(expected)


def test_auto_follows_system(monkeypatch):
    app = QApplication.instance()
    monkeypatch.setattr(theme, "resolve_mode", theme.resolve_mode)  # настоящая функция, но смотрим на результат
    scheme = app.styleHints().colorScheme()
    expected = DARK if scheme == theme.Qt.ColorScheme.Dark else LIGHT
    assert theme.resolve_mode("auto", app) is expected


def test_roles_and_variants_are_properties():
    label = set_role(QLabel("текст"), "error")
    assert label.property("role") == "error"
    button = set_variant(QPushButton("ок"), "danger")
    assert button.property("variant") == "danger"


# --- настройка и меню ---


def test_setting_default_and_validation(settings):
    assert settings.theme == "auto"
    settings.theme = "dark"
    assert settings.theme == "dark"
    with pytest.raises(ValueError):
        settings.theme = "розовая"


def test_broken_saved_value_falls_back(settings):
    settings._s.setValue("theme", "что-то")
    assert settings.theme == "auto"


@pytest.fixture
def window(qtbot, settings):
    w = MainWindow(settings)
    qtbot.addWidget(w)
    return w


def test_menu_switches_theme(window, settings):
    assert window._theme_actions["auto"].isChecked()
    window._theme_actions["dark"].trigger()
    assert settings.theme == "dark"
    assert theme.palette() is DARK
    assert window._theme_actions["dark"].isChecked()
    window._theme_actions["light"].trigger()
    assert theme.palette() is LIGHT and settings.theme == "light"


def test_saved_theme_is_checked_in_menu(qtbot, settings):
    settings.theme = "dark"
    w = MainWindow(settings)
    qtbot.addWidget(w)
    assert w._theme_actions["dark"].isChecked()
    assert not w._theme_actions["auto"].isChecked()


def test_unknown_mode_is_ignored(window, settings):
    window.set_theme("неизвестная")
    assert settings.theme == "auto"


def test_cards_are_flat(window):
    """Карточки плоские: тонкая рамка вместо теней, без графических эффектов."""
    cards = window.findChildren(QFrame, "card")
    assert cards
    assert all(c.graphicsEffect() is None for c in cards)


def test_no_emoji_in_interface():
    """В интерфейсе нет эмодзи и декоративных значков: стиль держится на типографике.
    Разрешены только галочка и крестик как обычные типографские знаки."""
    import pathlib
    import re

    emoji = re.compile("[🀀-🫿☀-➿⬀-⯿]")
    allowed = {"✓", "✕"}
    found = []
    for path in sorted(pathlib.Path(theme.__file__).parent.rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            found += [f"{path.name}:{number}: {m.group()}" for m in emoji.finditer(line) if m.group() not in allowed]
    assert found == []


def test_no_gradients_in_stylesheet():
    for p in (LIGHT, DARK):
        css = theme.stylesheet(p)
        assert "qlineargradient" not in css  # плоские заливки; радиальный градиент только внутри «точки» радиокнопки


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_every_screen_renders_in_theme(qtbot, settings, mode):
    """Все экраны открываются и рисуются в обеих темах без ошибок."""
    apply_theme(QApplication.instance(), mode)
    w = MainWindow(settings)
    qtbot.addWidget(w)
    w.show()
    for name in ("start", "login", "quizzes", "history", "editor", "join"):
        w.navigate(name)
        pixmap = w.grab()
        assert not pixmap.isNull(), name
    # Фон окна взят из темы, а не стандартный серый.
    color = w.grab().toImage().pixelColor(10, w.height() // 2).name().upper()
    assert color == (DARK if mode == "dark" else LIGHT).bg.upper()


# --- виджеты игры ---


def test_leaderboard_medals(qtbot):
    board = Leaderboard()
    qtbot.addWidget(board)
    board.show_entries([{"rank": r, "player_id": r, "nickname": f"игрок {r}", "score": 100 - r} for r in (1, 2, 3, 4)], me=1)
    alpha = [board.item(i).icon().pixmap(QSize(18, 18)).toImage().pixelColor(9, 9).alpha() for i in range(4)]
    assert all(a > 0 for a in alpha[:3])  # у первой тройки цветная медаль
    assert alpha[3] == 0  # у остальных пустое место для выравнивания
    assert board.item(0).text() == "1. игрок 1 — 99"  # текст не менялся
    assert board.item(0).font().bold()  # свою строку по-прежнему выделяем жирным


def test_countdown_turns_red_in_last_seconds(qtbot):
    countdown = Countdown()
    qtbot.addWidget(countdown)
    countdown.start(20)
    assert countdown._label.property("low") != "true"
    countdown.stop()
    countdown.start(3)  # меньше порога: сразу красный
    assert countdown._label.property("low") == "true"
    assert countdown._bar.property("low") == "true"
    countdown.stop()
    countdown.start(20)  # новый вопрос — снова обычный цвет
    assert countdown._label.property("low") == "false"
    countdown.stop()


# --- ширина содержимого ---


def test_content_is_centered_on_wide_window(qtbot, window):
    window.resize(2400, 900)
    window.show()
    window.navigate("quizzes")
    screen = window._screens["quizzes"]
    qtbot.waitUntil(lambda: screen.page.width() <= screen.MAX_WIDTH and screen.width() >= 2300, timeout=3000)
    assert screen.page.width() == screen.MAX_WIDTH
    # По центру: слева и справа от страницы поровну.
    assert abs(screen.page.x() - (screen.width() - screen.page.x() - screen.page.width())) <= 2


def test_content_fills_narrow_window(qtbot, window):
    window.resize(1000, 700)
    window.show()
    window.navigate("quizzes")
    screen = window._screens["quizzes"]
    qtbot.waitUntil(lambda: screen.page.width() > 0, timeout=3000)
    assert screen.page.width() == screen.width() - 48  # только обычные отступы 24 + 24


def test_window_does_not_grow_when_switching_screens(qtbot, window):
    """Раньше боковые поля росли вместе с окном, и оно «убегало» вширь при каждом переходе."""
    window.resize(1400, 800)
    window.show()
    widths = []
    for name in ("start", "login", "quizzes", "editor", "history", "join", "start"):
        window.navigate(name)
        qtbot.wait(30)
        widths.append(window.width())
    assert set(widths) == {1400}


def test_window_can_shrink_after_growing(qtbot, window):
    window.resize(2400, 800)
    window.show()
    for name in ("quizzes", "history", "editor"):
        window.navigate(name)
        qtbot.wait(30)
    window.resize(1100, 800)
    qtbot.wait(100)
    assert window.width() <= 1200


def test_option_buttons_have_letters_but_keep_text(qtbot):
    options = OptionButtons()
    qtbot.addWidget(options)
    options.set_options([{"option_id": i, "text": text} for i, text in enumerate(["Сидней", "Канберра", "Мельбурн", "Перт"], start=10)])
    buttons = list(options.buttons.values())
    assert [b.text() for b in buttons] == ["Сидней", "Канберра", "Мельбурн", "Перт"]  # буква дорисовывается, текст не меняется
    assert [b._letter for b in buttons] == ["A", "B", "C", "D"]
    assert len({b.styleSheet() for b in buttons}) == 4  # у каждого варианта свой цвет
    options.show()
    for b in buttons:
        assert not b.grab().isNull()
