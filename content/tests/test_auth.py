"""Регистрация и вход: /api/auth. Нужен PostgreSQL (TEST_DATABASE_URL)."""

import pytest
from sqlalchemy import text

from app.security import decode_token
from tests.conftest import SECRET


def register(client, username="teacher", password="password123"):
    return client.post("/api/auth/register", json={"username": username, "password": password})


def login(client, username="teacher", password="password123"):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def test_register(db_client):
    r = register(db_client)
    assert r.status_code == 201
    assert r.json() == {"id": 1, "username": "teacher"}

    # В БД лежит хэш, а не сам пароль.
    with db_client.app.state.engine.connect() as conn:
        stored = conn.execute(text("SELECT password_hash FROM content.users")).scalar_one()
    assert stored != "password123" and stored.startswith("$2b$")


def test_register_russian_username(db_client):
    assert register(db_client, username="Учитель_1").status_code == 201


def test_register_duplicate(db_client):
    register(db_client)
    r = register(db_client, password="other-password")
    assert r.status_code == 409
    assert r.json() == {"error": "имя пользователя уже занято"}


@pytest.mark.parametrize(
    "username, password",
    [
        ("ab", "password123"),
        ("x" * 33, "password123"),
        ("with space", "password123"),
        ("teacher", "short"),
        ("teacher", "я" * 40),  # 80 байт, больше лимита bcrypt
    ],
    ids=["короткий логин", "длинный логин", "пробел в логине", "короткий пароль", "пароль > 72 байт"],
)
def test_register_invalid(db_client, username, password):
    r = register(db_client, username, password)
    assert r.status_code == 422
    assert set(r.json()) == {"error"}


def test_login(db_client):
    register(db_client)
    r = login(db_client)
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    user = decode_token(body["access_token"], SECRET)
    assert (user.id, user.username) == (1, "teacher")


@pytest.mark.parametrize(
    "username, password",
    [("teacher", "wrong-password"), ("nobody", "password123"), ("teacher", "я" * 40)],
    ids=["неверный пароль", "нет пользователя", "пароль > 72 байт"],
)
def test_login_rejected(db_client, username, password):
    register(db_client)
    r = login(db_client, username, password)
    assert r.status_code == 401
    # Один и тот же ответ: по нему нельзя понять, существует ли логин.
    assert r.json() == {"error": "неверное имя пользователя или пароль"}

