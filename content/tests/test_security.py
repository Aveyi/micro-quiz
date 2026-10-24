"""Пароли, выпуск и проверка JWT, зависимость current_user. БД не нужна."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from app.deps import CurrentUser
from app.main import create_app
from app.security import InvalidToken, TokenUser, create_token, decode_token, hash_password, verify_password
from tests.conftest import SECRET, make_config


def test_password_hash():
    h = hash_password("correct horse")
    assert h != "correct horse" and h.startswith("$2b$")
    assert verify_password("correct horse", h)
    assert not verify_password("wrong horse", h)
    # Соль случайная: одинаковые пароли дают разные хэши.
    assert hash_password("correct horse") != h


def test_password_longer_than_bcrypt_limit():
    assert not verify_password("я" * 40, hash_password("short-password"))  # 80 байт


def test_token_roundtrip():
    now = datetime.now(UTC)
    token = create_token(1, "teacher", SECRET, now=now)
    assert decode_token(token, SECRET) == TokenUser(id=1, username="teacher")

    # Формат, который ждёт live (docs/quiz-design.md, раздел 6).
    payload = jwt.decode(token, SECRET, algorithms=["HS256"], issuer="quiz-content")
    assert payload["sub"] == "1"
    assert payload["username"] == "teacher"
    assert payload["exp"] == int((now + timedelta(hours=12)).timestamp())
    assert jwt.get_unverified_header(token)["alg"] == "HS256"


def _sign(payload: dict, key: str = SECRET, algorithm: str = "HS256") -> str:
    return jwt.encode(payload, key, algorithm=algorithm)


def _good(**changes) -> dict:
    payload = {"sub": "1", "username": "teacher", "iss": "quiz-content", "exp": datetime.now(UTC) + timedelta(hours=1)}
    for k, v in changes.items():
        if v is None:
            payload.pop(k)
        else:
            payload[k] = v
    return payload


def test_token_within_leeway():
    token = _sign(_good(exp=datetime.now(UTC) - timedelta(seconds=10)))
    assert decode_token(token, SECRET).id == 1


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(_sign(_good(), key="other-secret-other-secret-other!!"), id="чужой секрет"),
        pytest.param(jwt.encode(_good(), None, algorithm="none"), id="alg none"),
        pytest.param(_sign(_good(), algorithm="HS512"), id="alg HS512"),
        pytest.param(_sign(_good(exp=datetime.now(UTC) - timedelta(hours=1))), id="истёк"),
        pytest.param(_sign(_good(exp=None)), id="нет exp"),
        pytest.param(_sign(_good(iss="evil")), id="чужой iss"),
        pytest.param(_sign(_good(iss=None)), id="нет iss"),
        pytest.param(_sign(_good(sub=None)), id="нет sub"),
        pytest.param(_sign(_good(sub="abc")), id="sub не число"),
        pytest.param(_sign(_good(sub="0")), id="sub ноль"),
        pytest.param(_sign(_good(sub="²")), id="sub юникод-цифра"),
        pytest.param(_sign(_good(username=None)), id="нет username"),
        pytest.param("not.a.jwt", id="мусор"),
        pytest.param("", id="пустая строка"),
    ],
)
def test_token_rejected(token):
    with pytest.raises(InvalidToken):
        decode_token(token, SECRET)


@pytest.fixture
def client():
    app = create_app(make_config())

    @app.get("/test/me")
    def me(user: CurrentUser) -> dict:
        return {"id": user.id, "username": user.username}

    with TestClient(app) as c:
        yield c


def test_current_user(client):
    token = create_token(7, "teacher", SECRET)
    r = client.get("/test/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == {"id": 7, "username": "teacher"}


@pytest.mark.parametrize(
    "header",
    [
        None,
        "Bearer not.a.jwt",
        "Basic dXNlcjpwYXNz",
        "Bearer " + _sign(_good(exp=datetime.now(UTC) - timedelta(hours=1))),
    ],
    ids=["нет заголовка", "мусор", "другая схема", "истёк"],
)
def test_current_user_rejected(client, header):
    headers = {"Authorization": header} if header else {}
    r = client.get("/test/me", headers=headers)
    assert r.status_code == 401
    assert set(r.json()) == {"error"}
    assert r.headers["WWW-Authenticate"] == "Bearer"
