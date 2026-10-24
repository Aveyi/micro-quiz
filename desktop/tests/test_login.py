"""Экран входа и регистрации ведущего."""

import json

import pytest
from PySide6.QtCore import Qt

from quiz_desktop.main_window import MainWindow
from quiz_desktop.screens.login import validate

TOKEN = {"access_token": "jwt-token", "token_type": "bearer"}


@pytest.fixture
def window(qtbot, settings, server):
    settings.server_url = server.url
    w = MainWindow(settings)
    qtbot.addWidget(w)
    w.navigate("login")
    return w


@pytest.fixture
def screen(window):
    return window._screens["login"]


def fill(screen, username="teacher", password="password123", confirm=None):
    screen.username.setText(username)
    screen.password.setText(password)
    if confirm is not None:
        screen.confirm.setText(confirm)


def auth_requests(server):
    return [(r["path"], json.loads(r["body"])) for r in server.requests if r["path"].startswith("/api/auth/")]


@pytest.mark.parametrize(
    "username, password, confirm, ok",
    [
        ("teacher", "password123", None, True),
        ("Учитель_1", "password123", "password123", True),
        ("ab", "password123", None, False),
        ("with space", "password123", None, False),
        ("teacher", "short", None, False),
        ("teacher", "я" * 40, None, False),  # 80 байт
        ("teacher", "password123", "password124", False),
    ],
)
def test_validate(username, password, confirm, ok):
    assert (validate(username, password, confirm) is None) == ok


def test_login(qtbot, window, screen, server, settings):
    server.routes["/api/auth/login"] = (200, TOKEN)
    fill(screen)
    qtbot.mouseClick(screen.submit_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.current_screen_name() == "quizzes", timeout=5000)

    assert auth_requests(server) == [("/api/auth/login", {"username": "teacher", "password": "password123"})]
    assert window.api.token == "jwt-token"
    assert window.username == "teacher"
    assert "teacher" in window._user_label.text()
    assert settings.last_username == "teacher"


def test_login_by_enter(qtbot, window, screen, server):
    server.routes["/api/auth/login"] = (200, TOKEN)
    fill(screen)
    qtbot.keyClick(screen.password, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: window.current_screen_name() == "quizzes", timeout=5000)


def test_login_wrong_password(qtbot, window, screen, server):
    server.routes["/api/auth/login"] = (401, {"error": "неверное имя пользователя или пароль"})
    fill(screen)
    screen.submit()
    assert not screen.submit_button.isEnabled()  # пока ждём ответ, кнопка недоступна
    qtbot.waitUntil(lambda: screen.submit_button.isEnabled(), timeout=5000)

    assert screen.error.text() == "неверное имя пользователя или пароль"
    assert window.current_screen_name() == "login"
    assert window.api.token is None


def test_invalid_input_not_sent(window, screen, server):
    fill(screen, username="ab")
    screen.submit()
    assert "Имя пользователя" in screen.error.text()
    assert auth_requests(server) == []


def test_register_then_login(qtbot, window, screen, server):
    server.routes["/api/auth/register"] = (201, {"id": 1, "username": "teacher"})
    server.routes["/api/auth/login"] = (200, TOKEN)
    qtbot.mouseClick(screen.switch_button, Qt.MouseButton.LeftButton)
    assert screen.submit_button.text() == "Зарегистрироваться"
    fill(screen, confirm="password123")
    screen.submit()
    qtbot.waitUntil(lambda: window.current_screen_name() == "quizzes", timeout=5000)

    body = {"username": "teacher", "password": "password123"}
    assert auth_requests(server) == [("/api/auth/register", body), ("/api/auth/login", body)]
    assert window.api.token == "jwt-token"


def test_register_mismatch(window, screen, server):
    screen.set_register_mode(True)
    fill(screen, confirm="другой-пароль")
    screen.submit()
    assert screen.error.text() == "Пароли не совпадают"
    assert auth_requests(server) == []


def test_register_taken(qtbot, window, screen, server):
    server.routes["/api/auth/register"] = (409, {"error": "имя пользователя уже занято"})
    screen.set_register_mode(True)
    fill(screen, confirm="password123")
    screen.submit()
    qtbot.waitUntil(lambda: screen.submit_button.isEnabled(), timeout=5000)
    assert screen.error.text() == "имя пользователя уже занято"
    assert [p for p, _ in auth_requests(server)] == ["/api/auth/register"]


def test_confirm_only_in_register_mode(screen):
    assert screen.confirm.isHidden()
    screen.set_register_mode(True)
    assert not screen.confirm.isHidden()


def test_server_down(qtbot, settings, free_url):
    settings.server_url = free_url
    w = MainWindow(settings)
    qtbot.addWidget(w)
    w.navigate("login")
    screen = w._screens["login"]
    fill(screen)
    screen.submit()
    qtbot.waitUntil(lambda: screen.submit_button.isEnabled(), timeout=10000)
    assert screen.error.text().startswith("Сервер недоступен")


def test_logout_and_remembered_username(qtbot, window, screen, server):
    server.routes["/api/auth/login"] = (200, TOKEN)
    fill(screen)
    screen.submit()
    qtbot.waitUntil(lambda: window.current_screen_name() == "quizzes", timeout=5000)

    window.logout()
    assert window.api.token is None
    assert window.current_screen_name() == "start"
    assert not window._logout_action.isEnabled()

    window.navigate("login")
    # Имя осталось, пароль стёрт.
    assert screen.username.text() == "teacher"
    assert screen.password.text() == ""


def test_username_from_settings(qtbot, settings, server):
    settings.last_username = "Учитель"
    w = MainWindow(settings)
    qtbot.addWidget(w)
    w.navigate("login")
    assert w._screens["login"].username.text() == "Учитель"
