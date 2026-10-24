"""Внутренний API для live: /internal/quizzes/{id}. Нужен PostgreSQL (TEST_DATABASE_URL)."""

import pytest

from tests.conftest import INTERNAL_TOKEN
from tests.test_quizzes import QUIZ, auth_header, create

INTERNAL = {"X-Internal-Token": INTERNAL_TOKEN}


@pytest.fixture
def alice(db_client):
    return auth_header(db_client, "alice")


def test_get_quiz(db_client, alice):
    created = create(db_client, alice)
    r = db_client.get(f"/internal/quizzes/{created['id']}", headers=INTERNAL)
    assert r.status_code == 200
    q = r.json()

    # Ровно поля из docs/quiz-design.md, раздел 5.2: их ждёт live/internal/content.
    assert set(q) == {"id", "owner_id", "title", "questions"}
    assert q["id"] == created["id"]
    assert q["owner_id"] == 1
    assert q["title"] == QUIZ["title"]
    assert q["questions"] == created["questions"]  # с правильными ответами, по position

    question = q["questions"][0]
    assert set(question) == {"id", "position", "text", "time_limit_sec", "options"}
    assert set(question["options"][0]) == {"id", "position", "text", "is_correct"}
    assert [o["is_correct"] for o in question["options"]] == [False, True]


def test_any_owner(db_client, alice):
    """Владельца проверяет live по owner_id, content отдаёт викторину любого ведущего."""
    bob = auth_header(db_client, "bob")
    created = create(db_client, bob)
    q = db_client.get(f"/internal/quizzes/{created['id']}", headers=INTERNAL).json()
    assert q["owner_id"] == 2


def test_after_replace(db_client, alice):
    created = create(db_client, alice)
    replaced = db_client.put(f"/api/quizzes/{created['id']}", json=QUIZ, headers=alice).json()
    q = db_client.get(f"/internal/quizzes/{created['id']}", headers=INTERNAL).json()
    assert q["questions"] == replaced["questions"]


def test_not_found(db_client):
    r = db_client.get("/internal/quizzes/999", headers=INTERNAL)
    assert r.status_code == 404
    assert r.json() == {"error": "викторина не найдена"}


@pytest.mark.parametrize(
    "headers",
    [{}, {"X-Internal-Token": ""}, {"X-Internal-Token": "wrong"}, {"X-Internal-Token": INTERNAL_TOKEN + "x"}],
    ids=["нет заголовка", "пустой", "чужой", "длиннее"],
)
@pytest.mark.parametrize("path", ["/internal/quizzes/1", "/internal/quizzes/999", "/internal/quizzes/abc"])
def test_wrong_token(db_client, alice, headers, path):
    create(db_client, alice)
    r = db_client.get(path, headers=headers)
    # 401 раньше 404 и 422: без токена нельзя узнать даже, есть ли викторина.
    assert r.status_code == 401
    assert r.json() == {"error": "неверный X-Internal-Token"}


def test_jwt_is_not_enough(db_client, alice):
    """Токен ведущего не открывает /internal: там правильные ответы."""
    created = create(db_client, alice)
    assert db_client.get(f"/internal/quizzes/{created['id']}", headers=alice).status_code == 401


def test_hidden_from_docs(db_client):
    paths = db_client.get("/openapi.json").json()["paths"]
    assert not any(p.startswith("/internal") for p in paths)
