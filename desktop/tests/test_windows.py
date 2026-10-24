"""Настройки, главное окно и диалог настроек."""

import pytest
from PySide6.QtCore import Qt

from quiz_desktop.main_window import MainWindow
from quiz_desktop.settings import DEFAULT_SERVER_URL, normalize_server_url
from quiz_desktop.settings_dialog import SettingsDialog


@pytest.mark.parametrize(
    "text, expected",
    [
        ("http://localhost:8000", "http://localhost:8000"),
        ("  http://localhost:8000/ ", "http://localhost:8000"),
        ("https://quiz.example.com", "https://quiz.example.com"),
        ("http://192.168.1.10:8000", "http://192.168.1.10:8000"),
    ],
)
def test_normalize_url(text, expected):
    assert normalize_server_url(text) == expected


@pytest.mark.parametrize(
    "text",
    ["", "localhost:8000", "ftp://host", "http://", "http://host:abc", "http://host:70000", "http://host/api"],
)
def test_normalize_url_rejects(text):
    with pytest.raises(ValueError):
        normalize_server_url(text)


def test_settings_default_and_save(settings):
    assert settings.server_url == DEFAULT_SERVER_URL
    settings.server_url = "http://10.0.0.5:8000/"
    assert settings.server_url == "http://10.0.0.5:8000"


@pytest.fixture
def window(qtbot, settings):
    w = MainWindow(settings)
    qtbot.addWidget(w)
    return w


def test_navigation(qtbot, window):
    assert window.current_screen_name() == "start"
    start = window._screens["start"]
    qtbot.mouseClick(start.host_button, Qt.MouseButton.LeftButton)
    assert window.current_screen_name() == "login"
    window.navigate("start")
    qtbot.mouseClick(start.player_button, Qt.MouseButton.LeftButton)
    assert window.current_screen_name() == "join"


def test_unauthorized_returns_to_login(window):
    window.login("old", "teacher")
    window.api.unauthorized.emit()
    assert window.api.token is None and window.username is None
    assert window.current_screen_name() == "login"


def test_status_bar_shows_server(window):
    assert DEFAULT_SERVER_URL in window._server_label.text()


def _dialog(qtbot, url):
    d = SettingsDialog(url)
    qtbot.addWidget(d)
    return d


def test_dialog_check_ok(qtbot, server):
    """Ответ 401 от ручки с токеном означает, что сервер викторины на месте."""
    d = _dialog(qtbot, server.url)
    d.check_connection()
    qtbot.waitUntil(lambda: "Соединение есть" in d.status_label.text(), timeout=5000)
    assert server.requests[-1]["path"] == "/api/quizzes"


def test_dialog_check_down(qtbot, free_url):
    d = _dialog(qtbot, free_url)
    d.check_connection()
    qtbot.waitUntil(lambda: "недоступен" in d.status_label.text(), timeout=5000)
    assert d.check_button.isEnabled()


def test_dialog_rejects_bad_url(qtbot):
    d = _dialog(qtbot, DEFAULT_SERVER_URL)
    d.url_edit.setText("localhost")
    d.accept()
    assert d.result() == 0  # окно не закрылось
    assert "Неверный адрес" in d.status_label.text()


def test_dialog_accept_normalizes(qtbot):
    d = _dialog(qtbot, DEFAULT_SERVER_URL)
    d.url_edit.setText(" http://10.0.0.5:8000/ ")
    d.accept()
    assert d.server_url == "http://10.0.0.5:8000"
