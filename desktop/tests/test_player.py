"""Экран игрока против поддельного live: вход, вопросы, итоги, ошибки."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWebSockets import QWebSocketProtocol

from quiz_desktop.main_window import MainWindow

QUESTION = {
    "question_index": 0,
    "question_count": 2,
    "text": "Столица Австралии?",
    "options": [{"option_id": 17, "text": "Сидней"}, {"option_id": 18, "text": "Канберра"}],
    "time_limit_sec": 20,
}


def joined(players=None):
    return {
        "role": "player",
        "player_id": 5,
        "room_code": "482913",
        "quiz_title": "Столицы мира",
        "question_count": 2,
        "players": players or [{"player_id": 5, "nickname": "Вася"}],
    }


@pytest.fixture
def screen(qtbot, settings, live):
    settings.server_url = live.url
    window = MainWindow(settings)
    qtbot.addWidget(window)
    window.show()
    window.navigate("join")
    return window._screens["join"]


def submit(qtbot, screen, code="482913", nick="Вася"):
    screen.code_edit.setText(code)
    screen.nick_edit.setText(nick)
    qtbot.mouseClick(screen.join_button, Qt.MouseButton.LeftButton)


def join(qtbot, screen, live):
    """Входит в комнату: форма → join → joined → лобби."""
    submit(qtbot, screen, nick="  Вася  ")
    qtbot.waitUntil(lambda: live.received == [{"type": "join", "data": {"nickname": "Вася"}}], timeout=5000)
    live.send_msg("joined", joined())
    qtbot.waitUntil(lambda: screen.views.currentWidget() is screen.lobby_view, timeout=5000)


def items(list_widget):
    return [list_widget.item(i).text() for i in range(list_widget.count())]


def test_join_button_needs_code_and_nick(qtbot, screen):
    assert not screen.join_button.isEnabled()
    screen.code_edit.setText("4829")
    screen.nick_edit.setText("Вася")
    assert not screen.join_button.isEnabled()  # в коде меньше 6 цифр
    screen.code_edit.setText("482913")
    assert screen.join_button.isEnabled()
    screen.nick_edit.setText("   ")
    assert not screen.join_button.isEnabled()
    # Валидатор проверяет ввод с клавиатуры (setText он не трогает).
    screen.code_edit.clear()
    qtbot.keyClicks(screen.code_edit, "12ab34567")
    assert screen.code_edit.text() == "123456"


def test_full_game(qtbot, screen, live):
    join(qtbot, screen, live)
    assert "482913" in screen.lobby_title.text() and "Столицы мира" in screen.lobby_title.text()
    assert items(screen.lobby_players) == ["Вася  ← вы"]
    live.send_msg("lobby_update", {"players": [{"player_id": 5, "nickname": "Вася"}, {"player_id": 6, "nickname": "Петя"}]})
    qtbot.waitUntil(lambda: screen.lobby_players.count() == 2, timeout=5000)

    # Вопрос 1: отвечаем верно, второй клик ничего не отправляет.
    live.send_msg("question", QUESTION)
    qtbot.waitUntil(lambda: screen.views.currentWidget() is screen.question_view, timeout=5000)
    assert screen.q_header.text() == "Вопрос 1 из 2"
    assert sorted(screen.options.buttons) == [17, 18]
    qtbot.mouseClick(screen.options.buttons[18], Qt.MouseButton.LeftButton)
    qtbot.mouseClick(screen.options.buttons[17], Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: len(live.received) == 2, timeout=5000)
    assert live.received[1] == {"type": "answer", "data": {"question_index": 0, "option_id": 18}}
    assert not any(b.isEnabled() for b in screen.options.buttons.values())
    live.send_msg("answer_accepted", {"question_index": 0})
    qtbot.waitUntil(lambda: "принят" in screen.q_status.text(), timeout=5000)

    live.send_msg("question_result", {
        "question_index": 0, "correct_option_id": 18,
        "leaderboard": [{"rank": 1, "player_id": 5, "nickname": "Вася", "score": 912},
                        {"rank": 2, "player_id": 6, "nickname": "Петя", "score": 0}],
        "you": {"correct": True, "points": 912, "score": 912, "rank": 1},
    })
    qtbot.waitUntil(lambda: screen.views.currentWidget() is screen.result_view, timeout=5000)
    assert screen.r_verdict.text() == "Верно!"
    assert "+912" in screen.r_points.text() and "место 1" in screen.r_points.text()
    assert screen.r_correct.text() == "Правильный ответ: Канберра"
    assert items(screen.r_board) == ["1. Вася — 912", "2. Петя — 0"]
    assert screen.r_board.item(0).font().bold()  # своя строка выделена

    # Вопрос 2: не отвечаем.
    live.send_msg("question", {**QUESTION, "question_index": 1})
    qtbot.waitUntil(lambda: screen.q_header.text() == "Вопрос 2 из 2", timeout=5000)
    live.send_msg("player_left", {"player_id": 6, "nickname": "Петя"})
    qtbot.waitUntil(lambda: "Петя" in screen.window_.statusBar().currentMessage(), timeout=5000)
    live.send_msg("question_result", {
        "question_index": 1, "correct_option_id": 17,
        "leaderboard": [{"rank": 1, "player_id": 5, "nickname": "Вася", "score": 912}],
        "you": {"correct": False, "points": 0, "score": 912, "rank": 1},
    })
    qtbot.waitUntil(lambda: screen.r_verdict.text() == "Нет ответа", timeout=5000)

    live.send_msg("game_over", {
        "leaderboard": [{"rank": 1, "player_id": 5, "nickname": "Вася", "score": 912},
                        {"rank": 2, "player_id": 6, "nickname": "Петя", "score": 0, "left": True}],
        "you": {"score": 912, "rank": 1},
    })
    qtbot.waitUntil(lambda: screen.views.currentWidget() is screen.final_view, timeout=5000)
    assert screen.f_title.text() == "Игра окончена"
    assert "место: 1" in screen.f_subtitle.text()
    assert items(screen.f_board) == ["1. Вася — 912", "2. Петя — 0 (выбыл)"]

    # После game_over сервер закрывает соединение — итоги остаются на экране.
    live.close(QWebSocketProtocol.CloseCode.CloseCodeNormal, "game over")
    qtbot.waitUntil(lambda: screen.live is None, timeout=5000)
    assert screen.views.currentWidget() is screen.final_view
    assert screen.f_title.text() == "Игра окончена"


def test_nickname_taken_then_retry(qtbot, screen, live):
    submit(qtbot, screen)
    qtbot.waitUntil(lambda: len(live.received) == 1, timeout=5000)
    live.send_msg("error", {"code": "nickname_taken", "message": "Ник уже занят"})
    qtbot.waitUntil(lambda: screen.form_error.text() == "Ник уже занят", timeout=5000)
    assert screen.join_button.isEnabled() and screen.nick_edit.isEnabled()

    # Соединение то же: пробуем другой ник без переподключения.
    screen.nick_edit.setText("Вася2")
    qtbot.mouseClick(screen.join_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: len(live.received) == 2, timeout=5000)
    assert live.received[1]["data"] == {"nickname": "Вася2"}
    assert len(live.sockets) == 1


@pytest.mark.parametrize("code, message", [
    ("room_full", "в комнате уже 50 игроков"),
    ("game_already_started", "игра уже началась"),
])
def test_rejected_join_shows_reason(qtbot, screen, live, code, message):
    submit(qtbot, screen)
    qtbot.waitUntil(lambda: len(live.received) == 1, timeout=5000)
    live.send_msg("error", {"code": code, "message": message})
    live.close(QWebSocketProtocol.CloseCode.CloseCodeNormal, code)
    # Показываем причину отказа, а не «соединение закрыто».
    qtbot.waitUntil(lambda: screen.form_error.text() == message, timeout=5000)
    assert screen.views.currentWidget() is screen.form_view
    assert screen.live is None


def test_room_not_found(qtbot, settings, server, monkeypatch):
    monkeypatch.delenv("QUIZ_LIVE_URL", raising=False)
    settings.server_url = server.url  # HTTP-сервер ответит 404, как live без комнаты
    window = MainWindow(settings)
    qtbot.addWidget(window)
    window.navigate("join")
    screen = window._screens["join"]
    submit(qtbot, screen, code="000000")
    qtbot.waitUntil(lambda: "Комнаты с таким кодом нет" in screen.form_error.text(), timeout=5000)
    assert screen.join_button.text() == "Войти"


def test_host_left(qtbot, screen, live):
    join(qtbot, screen, live)
    live.send_msg("room_closed", {"reason": "host_left"})
    live.close(QWebSocketProtocol.CloseCode.CloseCodeNormal, "host_left")
    qtbot.waitUntil(lambda: screen.views.currentWidget() is screen.final_view, timeout=5000)
    assert screen.f_title.text() == "Игра прервана"
    assert screen.f_subtitle.text() == "Ведущий вышел, игра прервана"
    assert screen.f_board.isHidden()


def test_connection_lost(qtbot, screen, live):
    join(qtbot, screen, live)
    live.sockets[-1].abort()  # обрыв без close-фрейма
    qtbot.waitUntil(lambda: screen.views.currentWidget() is screen.final_view, timeout=5000)
    assert screen.f_subtitle.text() == "Связь с сервером потеряна"


def test_time_up_locks_options(qtbot, screen, live):
    join(qtbot, screen, live)
    live.send_msg("question", {**QUESTION, "time_limit_sec": 1})
    qtbot.waitUntil(lambda: screen.views.currentWidget() is screen.question_view, timeout=5000)
    assert screen.options.buttons[17].isEnabled()
    qtbot.waitUntil(lambda: screen.q_status.text() == "Время вышло", timeout=3000)
    assert not any(b.isEnabled() for b in screen.options.buttons.values())


def test_leave_button(qtbot, screen, live):
    join(qtbot, screen, live)
    leave = next(b for b in screen.lobby_view.findChildren(type(screen.join_button)) if "Выйти" in b.text())
    qtbot.mouseClick(leave, Qt.MouseButton.LeftButton)
    assert screen.window_.current_screen_name() == "start"
    qtbot.waitUntil(live.is_disconnected, timeout=5000)


def test_navigating_away_leaves_room(qtbot, screen, live):
    # Например, сменили сервер в настройках — окно вернулось на старт.
    join(qtbot, screen, live)
    screen.window_.navigate("start")
    qtbot.waitUntil(live.is_disconnected, timeout=5000)
    assert screen.live is None
