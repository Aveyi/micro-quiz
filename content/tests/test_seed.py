"""Демонстрационные викторины (app/seed_quizzes.json) и их загрузка (app/seed.py)."""

import socket

import pytest

from app.schemas import QuizIn
from app.seed import SeedError, http_call, load_quizzes, seed

QUIZZES = load_quizzes()


def test_three_quizzes_with_unique_titles():
    titles = [q["title"] for q in QUIZZES]
    assert len(QUIZZES) == 3
    assert len(set(titles)) == 3
    assert any("Мем" in t for t in titles)  # викторина про мемы


@pytest.mark.parametrize("quiz", QUIZZES, ids=lambda q: q["title"])
def test_quiz_is_valid(quiz):
    # Те же проверки, что и у сервиса: 2–4 варианта, один правильный, таймер 5–120 и т. д.
    parsed = QuizIn.model_validate(quiz)
    assert len(parsed.questions) == 10
    for question in parsed.questions:
        assert len(question.options) in (2, 4)
        # Тексты в json уже без пробелов по краям: сервис ничего не должен обрезать.
        assert question.text == question.text.strip()
        assert all(o.text == o.text.strip() for o in question.options)


@pytest.mark.parametrize("quiz", QUIZZES, ids=lambda q: q["title"])
def test_correct_answer_position_varies(quiz):
    """Правильный ответ не всегда стоит на одном и том же месте."""
    positions = {[o["is_correct"] for o in q["options"]].index(True) for q in quiz["questions"]}
    assert len(positions) >= 3


def test_both_option_counts_are_used():
    counts = {len(q["options"]) for quiz in QUIZZES for q in quiz["questions"]}
    assert counts == {2, 4}


def test_unreachable_server():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]  # порт освобождается при выходе из with: слушать некому
    with pytest.raises(SeedError, match="недоступен"):
        http_call(f"http://127.0.0.1:{port}")("GET", "/health", None, None)


# --- загрузка в настоящий сервис (нужен PostgreSQL, TEST_DATABASE_URL) ---


def client_call(client):
    """Вызов API через TestClient вместо сети."""

    def call(method, path, body, token):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        response = client.request(method, path, json=body, headers=headers)
        return response.status_code, response.json() if response.content else None

    return call


def test_seed_creates_quizzes_once(db_client):
    log = []
    assert seed(client_call(db_client), QUIZZES, "demo", "demo12345", log.append) == 3
    assert log[0] == "Создан демо-ведущий «demo»"

    # Второй запуск ничего не дублирует.
    log.clear()
    assert seed(client_call(db_client), QUIZZES, "demo", "demo12345", log.append) == 0
    assert all(line.startswith("Уже есть") for line in log)

    token = db_client.post("/api/auth/login", json={"username": "demo", "password": "demo12345"}).json()["access_token"]
    listing = db_client.get("/api/quizzes", headers={"Authorization": f"Bearer {token}"}).json()
    assert sorted(q["title"] for q in listing) == sorted(q["title"] for q in QUIZZES)
    assert {q["question_count"] for q in listing} == {10}


def test_seed_adds_only_missing(db_client):
    seed(client_call(db_client), QUIZZES[:1], "demo", "demo12345", lambda _: None)
    assert seed(client_call(db_client), QUIZZES, "demo", "demo12345", lambda _: None) == 2


def test_seed_wrong_password(db_client):
    seed(client_call(db_client), [], "demo", "demo12345", lambda _: None)
    with pytest.raises(SeedError, match="войти"):
        seed(client_call(db_client), QUIZZES, "demo", "другой-пароль", lambda _: None)
