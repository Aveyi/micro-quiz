"""WebSocket-клиент к live: адрес, конверт, ошибки подключения, закрытие."""

import pytest
from PySide6.QtWebSockets import QWebSocketProtocol

from quiz_desktop.live_client import LIVE_URL_ENV, LiveClient, close_error, handshake_error, live_ws_url


@pytest.fixture
def client(qtbot, live):
    return LiveClient(live.url)


def open_client(qtbot, client, room="482913", token=None):
    with qtbot.waitSignal(client.opened, timeout=5000):
        client.open(room, token)


# --- адрес ---


@pytest.mark.parametrize(
    "server_url, expected",
    [
        ("http://localhost:8000", "ws://localhost:8000/live/ws?room=482913"),
        ("https://quiz.example.com", "wss://quiz.example.com/live/ws?room=482913"),
        ("http://127.0.0.1:8000/", "ws://127.0.0.1:8000/live/ws?room=482913"),
    ],
)
def test_url(monkeypatch, server_url, expected):
    monkeypatch.delenv(LIVE_URL_ENV, raising=False)
    assert live_ws_url(server_url, "482913") == expected


def test_url_escapes_room(monkeypatch):
    monkeypatch.delenv(LIVE_URL_ENV, raising=False)
    assert live_ws_url("http://h:1", "12 3&x=1") == "ws://h:1/live/ws?room=12+3%26x%3D1"


def test_url_env_override(monkeypatch):
    # Разработка без nginx: live на своём порту, server_url — content.
    monkeypatch.setenv(LIVE_URL_ENV, "http://localhost:8080")
    assert live_ws_url("http://localhost:8000", "1") == "ws://localhost:8080/live/ws?room=1"
    monkeypatch.setenv(LIVE_URL_ENV, "не адрес")
    with pytest.raises(ValueError):
        live_ws_url("http://localhost:8000", "1")


# --- разбор ошибок ---


@pytest.mark.parametrize(
    "error_string, code, fragment",
    [
        ("QWebSocketPrivate::processHandshake: Unhandled http status code: 404 (Not Found).", 404, "Комнаты с таким кодом нет"),
        ("QWebSocketPrivate::processHandshake: Unhandled http status code: 409 (Conflict).", 409, "уже подключён"),
        ("QWebSocketPrivate::processHandshake: Unhandled http status code: 418 (I'm a teapot).", 418, "код 418"),
        # Так Qt 6.12 сообщает об ответе 401 — проверено на настоящем live.
        ("QWebSocketPrivate::processHandshake: Unsupported WWW-Authenticate challenges encountered.", 401, "истекла"),
        ("QWebSocketPrivate::processHandshake: Unknown error condition encountered.", 0, "Сервер недоступен"),
        ("Connection refused", 0, "Connection refused"),
    ],
)
def test_handshake_error(error_string, code, fragment):
    err = handshake_error(error_string)
    assert err.code == code and fragment in err.message


def test_close_error():
    assert close_error(1001, "server_shutdown").message == "Сервер перезапускается"
    assert "долго не входили" in close_error(1008, "join timeout").message
    assert "медленное" in close_error(1008, "too slow").message
    assert "код 4000" in close_error(4000, "").message


# --- подключение и сообщения ---


def test_host_sends_token_in_header(qtbot, client, live):
    open_client(qtbot, client, token="abc.def.ghi")
    request = live.requests[0]
    assert request.url().path() == "/live/ws"
    assert request.url().query() == "room=482913"
    assert bytes(request.rawHeader("Authorization")) == b"Bearer abc.def.ghi"
    assert client.is_open


def test_player_has_no_token(qtbot, client, live):
    open_client(qtbot, client)
    assert not live.requests[0].hasRawHeader("Authorization")


def test_send_envelope_in_utf8(qtbot, client, live):
    open_client(qtbot, client)
    client.send("join", {"nickname": "Вася"})
    client.send("start")
    qtbot.waitUntil(lambda: len(live.received) == 2, timeout=5000)
    assert live.received == [
        {"type": "join", "data": {"nickname": "Вася"}},
        {"type": "start", "data": {}},  # data есть всегда
    ]


def test_receive_messages_skips_garbage(qtbot, client, live):
    open_client(qtbot, client)
    got = []
    client.message.connect(lambda t, d: got.append((t, d)))
    for text in ["не json", "[1, 2]", '{"data": {}}', '{"type": "lobby_update", "data": {"players": []}}']:
        live.send(text)
    qtbot.waitUntil(lambda: bool(got), timeout=5000)
    # Мусор пропущен, первым пришло настоящее сообщение.
    assert got == [("lobby_update", {"players": []})]


def test_server_close_code(qtbot, client, live):
    open_client(qtbot, client)
    with qtbot.waitSignal(client.closed, timeout=5000) as blocker:
        live.close(QWebSocketProtocol.CloseCode.CloseCodeGoingAway, "server_shutdown")
    assert blocker.args[0].code == 1001
    assert blocker.args[0].message == "Сервер перезапускается"
    assert not client.is_open


def test_join_timeout_close(qtbot, client, live):
    open_client(qtbot, client)
    with qtbot.waitSignal(client.closed, timeout=5000) as blocker:
        live.close(QWebSocketProtocol.CloseCode.CloseCodePolicyViolated, "join timeout")
    assert "долго не входили" in blocker.args[0].message


def test_connection_lost(qtbot, client, live):
    open_client(qtbot, client)
    with qtbot.waitSignal(client.closed, timeout=5000) as blocker:
        live.sockets[-1].abort()  # без close-фрейма, как при обрыве сети
    assert blocker.args[0].code == 1006
    assert blocker.args[0].message == "Связь с сервером потеряна"


def test_client_close(qtbot, client, live):
    open_client(qtbot, client)
    with qtbot.waitSignal(client.closed, timeout=5000) as blocker:
        client.close()
    assert blocker.args[0].code == 1000


# --- неудачное подключение ---


def test_server_down(qtbot, free_url):
    client = LiveClient(free_url)
    with qtbot.waitSignal(client.failed, timeout=5000) as blocker:
        client.open("482913")
    assert blocker.args[0].code == 0
    assert "Сервер недоступен" in blocker.args[0].message


def test_http_error_before_upgrade(qtbot, server):
    # Обычный HTTP-сервер отвечает на /live/ws?room=… кодом 404 —
    # так же отвечает live, если комнаты нет (раздел 4.1).
    client = LiveClient(server.url)
    closed = []
    client.closed.connect(closed.append)
    with qtbot.waitSignal(client.failed, timeout=5000) as blocker:
        client.open("000000")
    assert blocker.args[0].code == 404
    assert "Комнаты с таким кодом нет" in blocker.args[0].message
    qtbot.wait(100)
    assert closed == []  # ровно одно итоговое событие
