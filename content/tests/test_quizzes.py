"""CRUD викторин: /api/quizzes. Нужен PostgreSQL (TEST_DATABASE_URL)."""

import copy

import pytest
from sqlalchemy import text


def auth_header(client, username: str) -> dict[str, str]:
    client.post("/api/auth/register", json={"username": username, "password": "password123"})
    token = client.post("/api/auth/login", json={"username": username, "password": "password123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def alice(db_client):
    return auth_header(db_client, "alice")


@pytest.fixture
def bob(db_client):
    return auth_header(db_client, "bob")


QUIZ = {
    "title": "Столицы мира",
    "description": "Разминка",
    "questions": [
        {
            "text": "Столица Австралии?",
            "time_limit_sec": 20,
            "options": [
                {"text": "Сидней", "is_correct": False},
                {"text": "Канберра", "is_correct": True},
            ],
        },
        {
            "text": "Столица Канады?",
            "options": [
                {"text": "Торонто", "is_correct": False},
                {"text": "Оттава", "is_correct": True},
                {"text": "Монреаль", "is_correct": False},
            ],
        },
    ],
}


def quiz(**changes) -> dict:
    body = copy.deepcopy(QUIZ)
    body.update(changes)
    return body


def create(client, headers, body=None) -> dict:
    r = client.post("/api/quizzes", json=body or QUIZ, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def count_rows(client, table: str) -> int:
    with client.app.state.engine.connect() as conn:
        return conn.execute(text(f"SELECT count(*) FROM content.{table}")).scalar_one()


def test_create(db_client, alice):
    q = create(db_client, alice, quiz(title="  Столицы мира  "))
    assert q["title"] == "Столицы мира"  # пробелы по краям обрезаны
    assert q["description"] == "Разминка"
    assert q["created_at"].endswith("Z") and q["updated_at"].endswith("Z")

    first, second = q["questions"]
    assert [first["position"], second["position"]] == [0, 1]
    assert first["text"] == "Столица Австралии?"
    assert second["time_limit_sec"] == 20  # значение по умолчанию
    assert [(o["position"], o["text"], o["is_correct"]) for o in first["options"]] == [
        (0, "Сидней", False),
        (1, "Канберра", True),
    ]
    assert all(isinstance(o["id"], int) for o in first["options"])


def test_get(db_client, alice):
    created = create(db_client, alice)
    r = db_client.get(f"/api/quizzes/{created['id']}", headers=alice)
    assert r.status_code == 200
    assert r.json() == created


def test_list_only_own(db_client, alice, bob):
    first = create(db_client, alice, quiz(title="Первая"))
    second = create(db_client, alice, quiz(title="Вторая", questions=QUIZ["questions"][:1]))
    create(db_client, bob, quiz(title="Чужая"))

    r = db_client.get("/api/quizzes", headers=alice)
    assert r.status_code == 200
    # Сначала недавно изменённые.
    assert r.json() == [
        {"id": second["id"], "title": "Вторая", "question_count": 1, "updated_at": second["updated_at"]},
        {"id": first["id"], "title": "Первая", "question_count": 2, "updated_at": first["updated_at"]},
    ]


def test_list_empty(db_client, alice):
    assert db_client.get("/api/quizzes", headers=alice).json() == []


def test_replace(db_client, alice):
    created = create(db_client, alice)
    old_option_ids = {o["id"] for q in created["questions"] for o in q["options"]}

    new_body = quiz(
        title="Новое название",
        description="",
        questions=[
            {
                "text": "2 + 2?",
                "time_limit_sec": 10,
                "options": [{"text": "4", "is_correct": True}, {"text": "5", "is_correct": False}],
            }
        ],
    )
    r = db_client.put(f"/api/quizzes/{created['id']}", json=new_body, headers=alice)
    assert r.status_code == 200, r.text
    q = r.json()
    assert q["id"] == created["id"]
    assert q["title"] == "Новое название" and q["description"] == ""
    assert q["created_at"] == created["created_at"]
    assert q["updated_at"] > created["updated_at"]
    assert [x["text"] for x in q["questions"]] == ["2 + 2?"]
    # Вопросы заменены целиком: у вариантов новые id, старые строки удалены.
    assert not old_option_ids & {o["id"] for o in q["questions"][0]["options"]}
    assert count_rows(db_client, "questions") == 1
    assert count_rows(db_client, "answer_options") == 2

    assert db_client.get(f"/api/quizzes/{created['id']}", headers=alice).json() == q


def test_replace_same_positions(db_client, alice):
    """PUT с тем же числом вопросов: старые и новые позиции совпадают (UNIQUE (quiz_id, position))."""
    created = create(db_client, alice)
    r = db_client.put(f"/api/quizzes/{created['id']}", json=QUIZ, headers=alice)
    assert r.status_code == 200, r.text
    assert count_rows(db_client, "questions") == 2


def test_delete(db_client, alice):
    created = create(db_client, alice)
    r = db_client.delete(f"/api/quizzes/{created['id']}", headers=alice)
    assert r.status_code == 204
    assert r.content == b""
    assert db_client.get(f"/api/quizzes/{created['id']}", headers=alice).status_code == 404
    assert count_rows(db_client, "questions") == 0
    assert count_rows(db_client, "answer_options") == 0


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_foreign_quiz_is_not_found(db_client, alice, bob, method):
    created = create(db_client, alice)
    kwargs = {"json": QUIZ} if method == "put" else {}
    r = getattr(db_client, method)(f"/api/quizzes/{created['id']}", headers=bob, **kwargs)
    # Чужая викторина неотличима от несуществующей.
    assert r.status_code == 404
    assert r.json() == {"error": "викторина не найдена"}
    # И она не изменилась.
    assert db_client.get(f"/api/quizzes/{created['id']}", headers=alice).json() == created


def test_missing_quiz(db_client, alice):
    assert db_client.get("/api/quizzes/999", headers=alice).status_code == 404


@pytest.mark.parametrize("quiz_id", ["0", "abc", str(10**20)])
def test_bad_quiz_id(db_client, alice, quiz_id):
    r = db_client.get(f"/api/quizzes/{quiz_id}", headers=alice)
    assert r.status_code == 422
    assert set(r.json()) == {"error"}


@pytest.mark.parametrize(
    "request_args",
    [("get", "/api/quizzes"), ("post", "/api/quizzes"), ("get", "/api/quizzes/1"), ("put", "/api/quizzes/1"), ("delete", "/api/quizzes/1")],
    ids=lambda a: " ".join(a),
)
def test_requires_token(db_client, request_args):
    method, path = request_args
    kwargs = {"json": QUIZ} if method in ("post", "put") else {}
    r = getattr(db_client, method)(path, **kwargs)
    assert r.status_code == 401


def _question(options=None, **changes) -> dict:
    q = copy.deepcopy(QUIZ["questions"][0])
    if options is not None:
        q["options"] = options
    q.update(changes)
    return q


def _options(n: int, correct: int = 1) -> list[dict]:
    return [{"text": f"вариант {i}", "is_correct": i < correct} for i in range(n)]


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(quiz(title="   "), id="пустое название"),
        pytest.param(quiz(title="x" * 101), id="длинное название"),
        pytest.param(quiz(description="x" * 1001), id="длинное описание"),
        pytest.param(quiz(questions=[]), id="0 вопросов"),
        pytest.param(quiz(questions=[_question()] * 51), id="51 вопрос"),
        pytest.param(quiz(questions=[_question(text="")]), id="пустой вопрос"),
        pytest.param(quiz(questions=[_question(text="x" * 301)]), id="длинный вопрос"),
        pytest.param(quiz(questions=[_question(time_limit_sec=4)]), id="таймер 4"),
        pytest.param(quiz(questions=[_question(time_limit_sec=121)]), id="таймер 121"),
        pytest.param(quiz(questions=[_question(options=_options(1))]), id="1 вариант"),
        pytest.param(quiz(questions=[_question(options=_options(5))]), id="5 вариантов"),
        pytest.param(quiz(questions=[_question(options=_options(3, correct=0))]), id="нет правильного"),
        pytest.param(quiz(questions=[_question(options=_options(3, correct=2))]), id="два правильных"),
        pytest.param(quiz(questions=[_question(options=[{"text": " ", "is_correct": True}, {"text": "b"}])]), id="пустой вариант"),
    ],
)
def test_create_invalid(db_client, alice, body):
    r = db_client.post("/api/quizzes", json=body, headers=alice)
    assert r.status_code == 422, r.text
    assert set(r.json()) == {"error"}
    assert count_rows(db_client, "quizzes") == 0


def test_limits_are_inclusive(db_client, alice):
    body = quiz(questions=[_question(options=_options(4), time_limit_sec=5)] * 49 + [_question(time_limit_sec=120)])
    q = create(db_client, alice, body)
    assert len(q["questions"]) == 50
    assert len(q["questions"][0]["options"]) == 4


def test_invalid_put_keeps_quiz(db_client, alice):
    created = create(db_client, alice)
    r = db_client.put(f"/api/quizzes/{created['id']}", json=quiz(questions=[]), headers=alice)
    assert r.status_code == 422
    assert db_client.get(f"/api/quizzes/{created['id']}", headers=alice).json() == created
