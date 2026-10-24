"""Экран «Мои викторины»."""

import json
from datetime import datetime, timezone

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from quiz_desktop.main_window import MainWindow
from quiz_desktop.screens.quizzes import format_time

QUIZZES = [
    {"id": 3, "title": "Столицы мира", "question_count": 10, "updated_at": "2026-10-24T10:28:00.123456Z"},
    {"id": 1, "title": "Разминка", "question_count": 2, "updated_at": "2026-10-23T08:00:00Z"},
]


@pytest.fixture
def window(qtbot, settings, server):
    server.routes["GET /api/quizzes"] = (200, QUIZZES)
    settings.server_url = server.url
    w = MainWindow(settings)
    qtbot.addWidget(w)
    return w


@pytest.fixture
def screen(qtbot, window):
    window.login("jwt-token", "teacher")  # сразу открывает «Мои викторины»
    s = window._screens["quizzes"]
    qtbot.waitUntil(lambda: s.table.rowCount() == 2, timeout=5000)
    return s


def requests_to(server, method, path_prefix):
    return [r for r in server.requests if r["method"] == method and r["path"].startswith(path_prefix)]


def test_format_time():
    utc = datetime(2026, 10, 24, 10, 28, tzinfo=timezone.utc)
    assert format_time("2026-10-24T10:28:00.123456Z") == utc.astimezone().strftime("%d.%m.%Y %H:%M")
    assert format_time("не дата") == "не дата"


def test_list(screen, server):
    assert screen.content.currentWidget() is screen.table
    rows = [[screen.table.item(r, c).text() for c in range(2)] for r in range(2)]
    assert rows == [["Столицы мира", "10"], ["Разминка", "2"]]
    # Список запрошен с токеном.
    assert requests_to(server, "GET", "/api/quizzes")[0]["headers"]["Authorization"] == "Bearer jwt-token"


def test_buttons_need_selection(screen):
    assert not screen.play_button.isEnabled()
    assert not screen.edit_button.isEnabled()
    assert not screen.delete_button.isEnabled()
    screen.table.selectRow(0)
    assert screen.play_button.isEnabled() and screen.edit_button.isEnabled() and screen.delete_button.isEnabled()
    assert screen.selected_quiz()["id"] == 3


def test_empty(qtbot, window, server):
    server.routes["GET /api/quizzes"] = (200, [])
    window.login("jwt-token", "teacher")
    s = window._screens["quizzes"]
    qtbot.waitUntil(lambda: "пока нет викторин" in s.message.text(), timeout=5000)
    assert s.content.currentWidget() is s.message


def test_load_failed(qtbot, window, server):
    server.routes["GET /api/quizzes"] = (500, "<h1>oops</h1>")
    window.login("jwt-token", "teacher")
    s = window._screens["quizzes"]
    qtbot.waitUntil(lambda: "Не удалось загрузить" in s.message.text(), timeout=5000)


def test_refresh_failed_keeps_list(qtbot, screen, server):
    server.routes["GET /api/quizzes"] = (500, "<h1>oops</h1>")
    screen.load()
    qtbot.waitUntil(lambda: "Не удалось обновить" in screen.status.text(), timeout=5000)
    assert screen.table.rowCount() == 2  # старый список остался на экране


def test_refresh_keeps_selection(qtbot, screen, server):
    screen.table.selectRow(1)
    server.routes["GET /api/quizzes"] = (200, list(reversed(QUIZZES)))
    screen.load()
    qtbot.waitUntil(lambda: screen.table.item(0, 0).text() == "Разминка", timeout=5000)
    assert screen.selected_quiz()["id"] == 1


def test_create(qtbot, window, screen):
    qtbot.mouseClick(screen.create_button, Qt.MouseButton.LeftButton)
    assert window.current_screen_name() == "editor"
    assert window._screens["editor"].quiz_id is None


def test_edit(window, screen):
    screen.table.selectRow(0)
    screen.edit_selected()
    assert window.current_screen_name() == "editor"
    assert window._screens["editor"].quiz_id == 3


def test_double_click_edits(qtbot, window, screen):
    screen.table.selectRow(1)
    screen.table.cellDoubleClicked.emit(1, 0)
    assert window._screens["editor"].quiz_id == 1


def test_history(window, screen):
    screen.history_button.click()
    assert window.current_screen_name() == "history"


@pytest.mark.parametrize("answer, deleted", [(QMessageBox.StandardButton.Yes, True), (QMessageBox.StandardButton.No, False)])
def test_delete(qtbot, monkeypatch, screen, server, answer, deleted):
    # Окно подтверждения в тесте не показываем: подставляем ответ пользователя.
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: answer)
    server.routes["DELETE /api/quizzes/3"] = (204, None)
    loads_before = len(requests_to(server, "GET", "/api/quizzes"))

    screen.table.selectRow(0)
    screen.delete_selected()
    if deleted:
        qtbot.waitUntil(lambda: len(requests_to(server, "GET", "/api/quizzes")) > loads_before, timeout=5000)
        assert len(requests_to(server, "DELETE", "/api/quizzes/3")) == 1
    else:
        qtbot.wait(200)
        assert requests_to(server, "DELETE", "/api/quizzes") == []


def test_delete_missing_reloads(qtbot, monkeypatch, screen, server):
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    server.routes["DELETE /api/quizzes/3"] = (404, {"error": "викторина не найдена"})
    screen.table.selectRow(0)
    screen.delete_selected()
    qtbot.waitUntil(lambda: "список обновлён" in screen.status.text(), timeout=5000)


def test_play_opens_host_screen(qtbot, monkeypatch, window, screen):
    """«Провести игру» передаёт quiz_id экрану ведущего; комнату создаёт уже он."""
    host = window._screens["host_game"]
    got = []
    monkeypatch.setattr(host, "entered", lambda **params: got.append(params))
    screen.table.selectRow(0)
    qtbot.mouseClick(screen.play_button, Qt.MouseButton.LeftButton)
    assert window.current_screen_name() == "host_game"
    assert got == [{"quiz_id": 3}]


def test_expired_token_goes_to_login(qtbot, window, server):
    server.routes["GET /api/quizzes"] = (401, {"error": "токен невалиден или просрочен"})
    window.login("old-token", "teacher")
    qtbot.waitUntil(lambda: window.current_screen_name() == "login", timeout=5000)
    assert window.api.token is None
