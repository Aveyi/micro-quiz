"""Экран «История игр»."""

import pytest

from quiz_desktop.main_window import MainWindow
from quiz_desktop.screens.history import format_duration

GAMES = [
    {
        "id": 5, "quiz_id": 1, "quiz_title": "Столицы мира", "status": "cancelled", "player_count": 1,
        "created_at": "2026-10-24T11:00:00Z", "started_at": None, "finished_at": "2026-10-24T11:05:00Z",
    },
    {
        "id": 4, "quiz_id": 1, "quiz_title": "Столицы мира", "status": "finished", "player_count": 2,
        "created_at": "2026-10-24T10:50:01Z", "started_at": "2026-10-24T10:50:04Z", "finished_at": "2026-10-24T10:54:09Z",
    },
]
GAME_4 = dict(
    GAMES[1],
    players=[
        {"player_id": 5, "nickname": "Вася", "score": 1936, "rank": 1, "left": False},
        {"player_id": 6, "nickname": "Петя", "score": 0, "rank": 2, "left": True},
    ],
    questions=[
        {"question_index": 0, "question_id": 11, "total": 2, "answered": 2, "correct": 1, "correct_ratio": 0.5},
        {"question_index": 1, "question_id": 12, "total": 1, "answered": 1, "correct": 1, "correct_ratio": 1.0},
    ],
)
GAME_5 = dict(GAMES[0], players=[{"player_id": 7, "nickname": "Оля", "score": None, "rank": None, "left": False}], questions=[])
QUIZ_1 = {"id": 1, "questions": [{"id": 11, "text": "Столица Австралии?"}, {"id": 12, "text": "Столица Канады?"}]}


@pytest.fixture
def server_games(server):
    server.routes["GET /live/api/games"] = (200, GAMES)
    server.routes["GET /live/api/games/4"] = (200, GAME_4)
    server.routes["GET /live/api/games/5"] = (200, GAME_5)
    server.routes["GET /api/quizzes/1"] = (200, QUIZ_1)
    return server


@pytest.fixture
def window(qtbot, settings, server_games, monkeypatch):
    monkeypatch.delenv("QUIZ_LIVE_URL", raising=False)  # live — тот же адрес, что и content
    settings.server_url = server_games.url
    w = MainWindow(settings)
    qtbot.addWidget(w)
    w.api.token = "jwt-token"
    return w


@pytest.fixture
def screen(window):
    window.navigate("history")
    return window._screens["history"]


def cell(table, row, col):
    return table.item(row, col).text()


def requests_to(server, path):
    return [r for r in server.requests if r["path"] == path]


def test_format_duration():
    assert format_duration("2026-10-24T10:50:04Z", "2026-10-24T10:54:09Z") == "4:05"
    assert format_duration(None, "2026-10-24T10:54:09Z") == ""
    assert format_duration("2026-10-24T10:50:04Z", None) == ""


def test_list_and_newest_selected(qtbot, screen, server_games):
    qtbot.waitUntil(lambda: screen.games.rowCount() == 2, timeout=5000)
    assert [cell(screen.games, r, 2) for r in range(2)] == ["прервана", "завершена"]
    assert cell(screen.games, 1, 3) == "2"
    # Сразу выбрана самая новая игра, и её результаты загружены.
    assert screen.selected_game_id() == 5
    assert requests_to(server_games, "/live/api/games")[0]["headers"]["Authorization"] == "Bearer jwt-token"


def test_finished_game_details(qtbot, screen, server_games):
    qtbot.waitUntil(lambda: screen.games.rowCount() == 2, timeout=5000)
    screen.games.selectRow(1)
    qtbot.waitUntil(lambda: screen.questions.rowCount() == 2, timeout=5000)

    assert "завершена" in screen.d_info.text() and "длительность: 4:05" in screen.d_info.text()
    assert [[cell(screen.players, r, c) for c in range(3)] for r in range(2)] == [
        ["1", "Вася", "1936"],
        ["2", "Петя (выбыл)", "0"],
    ]
    # Тексты вопросов пришли из content.
    assert [[cell(screen.questions, r, c) for c in range(5)] for r in range(2)] == [
        ["1", "Столица Австралии?", "2 из 2", "1", "50%"],
        ["2", "Столица Канады?", "1 из 1", "1", "100%"],
    ]
    assert screen.d_note.text() == ""


def test_unfinished_game(qtbot, screen):
    qtbot.waitUntil(lambda: screen.details_view.currentWidget() is screen._details_widget, timeout=5000)
    assert screen.d_title.text() == "Столицы мира"
    assert [cell(screen.players, 0, c) for c in range(3)] == ["—", "Оля", "—"]
    assert "не дошла до конца" in screen.d_note.text()
    assert "До вопросов игра не дошла" in screen.d_note.text()


def test_question_texts_cached(qtbot, screen, server_games):
    qtbot.waitUntil(lambda: screen.games.rowCount() == 2, timeout=5000)
    for _ in range(2):
        screen.games.selectRow(1)
        qtbot.waitUntil(lambda: screen.questions.rowCount() == 2, timeout=5000)
        screen.games.selectRow(0)
        qtbot.waitUntil(lambda: screen.questions.rowCount() == 0, timeout=5000)
    assert len(requests_to(server_games, "/api/quizzes/1")) == 1


def test_deleted_quiz(qtbot, screen, server_games):
    server_games.routes["GET /api/quizzes/1"] = (404, {"error": "викторина не найдена"})
    qtbot.waitUntil(lambda: screen.games.rowCount() == 2, timeout=5000)
    screen.games.selectRow(1)
    qtbot.waitUntil(lambda: screen.questions.rowCount() == 2, timeout=5000)
    # Статистика показана и без текстов.
    assert cell(screen.questions, 0, 1) == "—"
    assert cell(screen.questions, 0, 4) == "50%"
    assert "Тексты некоторых вопросов недоступны" in screen.d_note.text()


def test_edited_quiz(qtbot, screen, server_games):
    """После PUT у вопросов новые id: текст есть только у совпавших."""
    server_games.routes["GET /api/quizzes/1"] = (200, {"id": 1, "questions": [{"id": 11, "text": "Столица Австралии?"}]})
    qtbot.waitUntil(lambda: screen.games.rowCount() == 2, timeout=5000)
    screen.games.selectRow(1)
    qtbot.waitUntil(lambda: screen.questions.rowCount() == 2, timeout=5000)
    assert [cell(screen.questions, r, 1) for r in range(2)] == ["Столица Австралии?", "—"]


def test_empty(qtbot, window, server_games):
    server_games.routes["GET /live/api/games"] = (200, [])
    window.navigate("history")
    s = window._screens["history"]
    qtbot.waitUntil(lambda: "ни одной игры" in s.list_message.text(), timeout=5000)


def test_list_failed(qtbot, window, server_games):
    server_games.routes["GET /live/api/games"] = (502, {"error": "сервис временно недоступен"})
    window.navigate("history")
    s = window._screens["history"]
    qtbot.waitUntil(lambda: "сервис временно недоступен" in s.list_message.text(), timeout=5000)


def test_details_failed(qtbot, screen, server_games):
    server_games.routes["GET /live/api/games/4"] = (404, {"error": "игра не найдена"})
    qtbot.waitUntil(lambda: screen.games.rowCount() == 2, timeout=5000)
    screen.games.selectRow(1)
    qtbot.waitUntil(lambda: "игра не найдена" in screen.details_message.text(), timeout=5000)


def test_refresh_keeps_selection(qtbot, screen, server_games):
    qtbot.waitUntil(lambda: screen.games.rowCount() == 2, timeout=5000)
    screen.games.selectRow(1)
    screen.load()
    qtbot.waitUntil(lambda: len(requests_to(server_games, "/live/api/games")) == 2, timeout=5000)
    qtbot.wait(200)
    assert screen.selected_game_id() == 4


def test_separate_live_url(qtbot, settings, server_games, free_url, monkeypatch):
    """Без nginx (QUIZ_LIVE_URL) история идёт в live по его адресу, с тем же токеном."""
    monkeypatch.setenv("QUIZ_LIVE_URL", server_games.url)
    settings.server_url = free_url  # content «недоступен», но истории он не нужен
    w = MainWindow(settings)
    qtbot.addWidget(w)
    w.api.token = "jwt-token"
    w.navigate("history")
    s = w._screens["history"]
    qtbot.waitUntil(lambda: s.games.rowCount() == 2, timeout=5000)
    assert requests_to(server_games, "/live/api/games")[0]["headers"]["Authorization"] == "Bearer jwt-token"


def test_expired_token(qtbot, window, server_games):
    server_games.routes["GET /live/api/games"] = (401, {"error": "токен невалиден или просрочен"})
    window.username = "teacher"
    window.navigate("history")
    qtbot.waitUntil(lambda: window.current_screen_name() == "login", timeout=5000)
