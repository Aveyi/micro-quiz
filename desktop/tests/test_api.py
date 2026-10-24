"""REST-клиент: разбор ответов, ошибки, токен."""

import json

import pytest

from quiz_desktop.api import ApiClient, ApiError


def wait(qtbot, reply):
    """Ждёт ответа и возвращает ("ok", data) или ("error", ApiError)."""
    result = []
    reply.succeeded.connect(lambda data: result.append(("ok", data)))
    reply.failed.connect(lambda err: result.append(("error", err)))
    qtbot.waitUntil(lambda: bool(result), timeout=5000)
    return result[0]


@pytest.fixture
def api(qtbot, server):
    return ApiClient(server.url)


def test_success(qtbot, api):
    assert wait(qtbot, api.get("/ok")) == ("ok", {"value": 1, "text": "привет"})


def test_no_content(qtbot, api):
    assert wait(qtbot, api.delete("/empty")) == ("ok", None)


def test_error_message_from_server(qtbot, api):
    kind, err = wait(qtbot, api.post("/conflict", {"username": "teacher"}))
    assert kind == "error"
    assert err == ApiError(409, "имя пользователя уже занято")


def test_error_without_json(qtbot, api):
    assert wait(qtbot, api.get("/html")) == ("error", ApiError(500, "ошибка сервера (код 500)"))


def test_server_down(qtbot, free_url):
    # Клиент держим в переменной: иначе Python удалит его посреди запроса.
    api = ApiClient(free_url)
    kind, err = wait(qtbot, api.get("/ok"))
    assert kind == "error"
    assert err.status == 0
    assert err.message.startswith("Сервер недоступен")


def test_json_body_in_utf8(qtbot, api, server):
    wait(qtbot, api.put("/ok", {"title": "Столицы мира"}))
    req = server.requests[-1]
    assert req["method"] == "PUT"
    assert req["headers"]["Content-Type"] == "application/json"
    assert json.loads(req["body"]) == {"title": "Столицы мира"}


def test_token_only_when_auth(qtbot, api, server):
    api.token = "abc"
    wait(qtbot, api.get("/ok"))
    assert "Authorization" not in server.requests[-1]["headers"]
    wait(qtbot, api.get("/ok", auth=True))
    assert server.requests[-1]["headers"]["Authorization"] == "Bearer abc"


def test_unauthorized_signal(qtbot, api, server):
    server.routes["/expired"] = (401, {"error": "токен невалиден или просрочен"})
    api.token = "expired"
    with qtbot.waitSignal(api.unauthorized, timeout=5000):
        kind, err = wait(qtbot, api.get("/expired", auth=True))
    assert err.status == 401


def test_no_unauthorized_signal_without_auth(qtbot, api):
    """401 на запрос без токена (например, неверный пароль при входе) — не «сессия истекла»."""
    with qtbot.assertNotEmitted(api.unauthorized):
        wait(qtbot, api.get("/api/quizzes"))


def test_client_deleted_in_handler(qtbot, free_url):
    """Обработчик ответа удаляет клиент (так бывает, когда закрывают окно).

    Раньше это роняло процесс: объекты Qt удалялись посреди сигнала запроса.
    Повторяем несколько раз, потому что сбой был не каждый раз.
    """
    for _ in range(3):
        holder = {"api": ApiClient(free_url)}
        done = []
        reply = holder["api"].get("/ok")
        reply.failed.connect(lambda err: (holder.clear(), done.append(err)))
        qtbot.waitUntil(lambda: bool(done), timeout=5000)
        qtbot.wait(10)  # даём Qt доделать отложенные удаления
