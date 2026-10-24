"""Проверки каркаса: /health и единый формат ошибок.

БД здесь не нужна: create_engine не подключается, пока нет запросов к ней.
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app import config
from app.config import Config
from app.main import create_app


@pytest.fixture
def app():
    app = create_app(Config(port=8000, database_url="postgresql+psycopg://u:p@localhost:1/db"))

    # Тестовые ручки, чтобы вызвать каждый вид ошибки.
    class Body(BaseModel):
        title: str
        count: int

    @app.post("/test/validate")
    def validate(body: Body) -> dict:
        return {}

    @app.get("/test/forbidden")
    def forbidden() -> dict:
        raise HTTPException(403, "нет доступа")

    @app.get("/test/crash")
    def crash() -> dict:
        raise RuntimeError("секретные подробности")

    return app


@pytest.fixture
def client(app):
    # raise_server_exceptions=False: проверяем ответ клиенту, а не исключение в тесте.
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_unknown_path(client):
    r = client.get("/nope")
    assert r.status_code == 404
    assert r.json() == {"error": "Not Found"}


def test_wrong_method(client):
    r = client.post("/health")
    assert r.status_code == 405
    assert set(r.json()) == {"error"}


def test_http_exception(client):
    r = client.get("/test/forbidden")
    assert r.status_code == 403
    assert r.json() == {"error": "нет доступа"}


def test_validation_error(client):
    r = client.post("/test/validate", json={"count": "много"})
    assert r.status_code == 422
    msg = r.json()["error"]
    assert "title" in msg and "count" in msg


def test_invalid_json(client):
    r = client.post("/test/validate", content="{", headers={"Content-Type": "application/json"})
    assert r.status_code == 422
    assert r.json() == {"error": "тело запроса не является корректным JSON"}


def test_unhandled_error_hides_details(client):
    r = client.get("/test/crash")
    assert r.status_code == 500
    assert r.json() == {"error": "внутренняя ошибка сервера"}


def test_config_converts_postgres_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://content_user:pw@postgres:5432/quiz")
    monkeypatch.delenv("PORT", raising=False)
    cfg = config.load()
    assert cfg.port == 8000
    assert cfg.database_url == "postgresql+psycopg://content_user:pw@postgres:5432/quiz"


@pytest.mark.parametrize("env", [{"PORT": "abc"}, {"PORT": "70000"}, {"DATABASE_URL": ""}])
def test_config_errors(monkeypatch, env):
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@h/db")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    with pytest.raises(config.ConfigError):
        config.load()
