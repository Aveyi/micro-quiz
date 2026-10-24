"""Экран ведущего против поддельного live: комната, лобби, вопросы, итоги."""

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMessageBox
from PySide6.QtWebSockets import QWebSocketProtocol

from quiz_desktop.api import ApiError, ApiReply
from quiz_desktop.live_client import LiveError
from quiz_desktop.main_window import MainWindow

QUESTION = {
    "question_index": 0,
    "question_count": 2,
    "text": "Столица Австралии?",
    "options": [{"option_id": 17, "text": "Сидней"}, {"option_id": 18, "text": "Канберра"}],
    "time_limit_sec": 20,
}
PLAYERS = [{"player_id": 5, "nickname": "Вася"}, {"player_id": 6, "nickname": "Петя"}]


class StubLiveApi:
    """Подмена REST к live: POST /live/api/rooms сразу «отвечает» заданным."""

    def __init__(self, ok=None, error=None):
        self.calls, self.ok, self.error, self._replies = [], ok, error, []

    def post(self, path, body=None, *, auth=False):
        self.calls.append((path, body, auth))
        reply = ApiReply()
        self._replies.append(reply)  # держим ссылку, пока ответ не доставлен
        if self.error:
            QTimer.singleShot(0, lambda: reply.failed.emit(self.error))
        else:
            QTimer.singleShot(0, lambda: reply.succeeded.emit(self.ok))
        return reply


@pytest.fixture
def window(qtbot, settings, live):
    settings.server_url = live.url
    w = MainWindow(settings)
    qtbot.addWidget(w)
    w.show()
    w.api.token = "host-token"
    return w


def open_host(window, stub):
    screen = window._screens["host_game"]
    screen._live_api = lambda: stub
    window.navigate("host_game")  # пока без quiz_id
    screen.entered(quiz_id=3)  # так позовёт navigate("host_game", quiz_id=3)
    return screen


def items(list_widget):
    return [list_widget.item(i).text() for i in range(list_widget.count())]


@pytest.fixture
def host(qtbot, window, live):
    """Ведущий в лобби: комната создана, WebSocket подключён, joined получен."""
    stub = StubLiveApi(ok={"room_code": "482913"})
    screen = open_host(window, stub)
    qtbot.waitUntil(lambda: len(live.sockets) == 1, timeout=5000)
    live.send_msg("joined", {"role": "host", "room_code": "482913", "quiz_title": "Столицы мира",
                             "question_count": 2, "players": []})
    qtbot.waitUntil(lambda: screen.views.currentWidget() is screen.lobby_view, timeout=5000)
    screen.stub = stub
    return screen


def test_creates_room_and_connects_with_token(host, live):
    assert host.stub.calls == [("/live/api/rooms", {"quiz_id": 3}, True)]
    request = live.requests[0]
    assert request.url().query() == "room=482913"
    assert bytes(request.rawHeader("Authorization")) == b"Bearer host-token"
    assert host.l_code.text() == "482913"
    assert "Столицы мира" in host.l_title.text()
    assert not host.start_button.isEnabled()  # игроков ещё нет


def test_full_game(qtbot, host, live):
    live.send_msg("lobby_update", {"players": PLAYERS})
    qtbot.waitUntil(lambda: host.l_players.count() == 2, timeout=5000)
    assert host.start_button.isEnabled() and host.l_count.text() == "Игроков: 2 из 50"
    qtbot.mouseClick(host.start_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: live.received == [{"type": "start", "data": {}}], timeout=5000)

    live.send_msg("question", QUESTION)
    qtbot.waitUntil(lambda: host.views.currentWidget() is host.question_view, timeout=5000)
    assert host.q_header.text() == "Вопрос 1 из 2"
    assert not any(b.isEnabled() for b in host.options.buttons.values())  # ведущий не отвечает
    assert host.q_progress.text() == "Ответили: 0 из 2"
    live.send_msg("answer_progress", {"answered": 1, "total": 2})
    qtbot.waitUntil(lambda: host.q_progress.text() == "Ответили: 1 из 2", timeout=5000)

    live.send_msg("question_result", {
        "question_index": 0, "correct_option_id": 18,
        "leaderboard": [{"rank": 1, "player_id": 5, "nickname": "Вася", "score": 912},
                        {"rank": 2, "player_id": 6, "nickname": "Петя", "score": 0}],
        "option_counts": {"17": 1, "18": 1},
    })
    qtbot.waitUntil(lambda: host.views.currentWidget() is host.result_view, timeout=5000)
    assert "Канберра" in host.r_header.text()
    label, bar = host.r_stats.rows[18]
    assert label.text() == "Канберра  ✓ — 1" and bar.value() == 1
    assert host.r_stats.rows[17][0].text() == "Сидней — 1"
    assert items(host.r_board) == ["1. Вася — 912", "2. Петя — 0"]
    assert host.next_button.text() == "Следующий вопрос" and host.next_button.isEnabled()

    qtbot.mouseClick(host.next_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: live.received[-1] == {"type": "next", "data": {}}, timeout=5000)
    assert not host.next_button.isEnabled()

    # Последний вопрос: кнопка ведёт к итогам. Петя выбывает.
    live.send_msg("question", {**QUESTION, "question_index": 1})
    qtbot.waitUntil(lambda: host.q_header.text() == "Вопрос 2 из 2", timeout=5000)
    live.send_msg("player_left", {"player_id": 6, "nickname": "Петя"})
    qtbot.waitUntil(lambda: "Петя" in host.window_.statusBar().currentMessage(), timeout=5000)
    live.send_msg("question_result", {
        "question_index": 1, "correct_option_id": 17,
        "leaderboard": [{"rank": 1, "player_id": 5, "nickname": "Вася", "score": 1900}],
        "option_counts": {"17": 1, "18": 0},
    })
    qtbot.waitUntil(lambda: host.views.currentWidget() is host.result_view, timeout=5000)
    assert host.next_button.text() == "Показать итоги"
    qtbot.mouseClick(host.next_button, Qt.MouseButton.LeftButton)

    live.send_msg("game_over", {"leaderboard": [
        {"rank": 1, "player_id": 5, "nickname": "Вася", "score": 1900},
        {"rank": 2, "player_id": 6, "nickname": "Петя", "score": 0, "left": True},
    ]})
    qtbot.waitUntil(lambda: host.views.currentWidget() is host.final_view, timeout=5000)
    assert host.f_subtitle.text() == "Победитель: Вася — 1900"
    assert items(host.f_board) == ["1. Вася — 1900", "2. Петя — 0 (выбыл)"]
    live.close(QWebSocketProtocol.CloseCode.CloseCodeNormal, "game over")
    qtbot.waitUntil(lambda: host.live is None, timeout=5000)
    assert host.f_title.text() == "Игра окончена"


def test_without_quiz(qtbot, window):
    window.navigate("host_game")
    screen = window._screens["host_game"]
    assert screen.m_text.text() == "Сначала выберите викторину"


def test_create_room_error(qtbot, window, live):
    stub = StubLiveApi(error=ApiError(403, "викторина принадлежит другому пользователю"))
    screen = open_host(window, stub)
    qtbot.waitUntil(lambda: "другому пользователю" in screen.m_text.text(), timeout=5000)
    assert screen.m_back.isVisible()
    assert live.sockets == []  # к WebSocket даже не подключались


def test_ws_401_returns_to_login(qtbot, host, window):
    # Токен истёк между созданием комнаты и подключением.
    host._on_failed(LiveError(401, "Сессия ведущего истекла, войдите снова"))
    assert window.current_screen_name() == "login"
    assert window.api.token is None


def test_lobby_timeout(qtbot, host, live):
    live.send_msg("room_closed", {"reason": "lobby_timeout"})
    live.close(QWebSocketProtocol.CloseCode.CloseCodeNormal, "lobby_timeout")
    qtbot.waitUntil(lambda: host.views.currentWidget() is host.final_view, timeout=5000)
    assert host.f_title.text() == "Игра прервана"
    assert "30 минут" in host.f_subtitle.text()


def test_close_room_asks_first(qtbot, host, live, monkeypatch, window):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    host.close_room()
    assert host.live is not None and window.current_screen_name() == "host_game"

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    host.close_room()
    assert window.current_screen_name() == "quizzes"  # обратно к списку викторин
    qtbot.waitUntil(live.is_disconnected, timeout=5000)


def test_navigating_away_closes_room(qtbot, host, live, window):
    window.navigate("start")
    qtbot.waitUntil(live.is_disconnected, timeout=5000)
    assert host.live is None
