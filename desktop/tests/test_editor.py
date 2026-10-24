"""Редактор викторины."""

import copy
import json

import pytest
from PySide6.QtWidgets import QMessageBox

from quiz_desktop.main_window import MainWindow
from quiz_desktop.screens.editor import validate_quiz

# Ответ GET /api/quizzes/3 — с id и position, как отдаёт content.
QUIZ_3 = {
    "id": 3,
    "title": "Столицы мира",
    "description": "Разминка",
    "created_at": "2026-10-24T10:00:00Z",
    "updated_at": "2026-10-24T10:00:00Z",
    "questions": [
        {
            "id": 41, "position": 0, "text": "Столица Австралии?", "time_limit_sec": 20,
            "options": [
                {"id": 17, "position": 0, "text": "Сидней", "is_correct": False},
                {"id": 18, "position": 1, "text": "Канберра", "is_correct": True},
            ],
        },
        {
            "id": 42, "position": 1, "text": "Столица Канады?", "time_limit_sec": 10,
            "options": [
                {"id": 19, "position": 0, "text": "Оттава", "is_correct": True},
                {"id": 20, "position": 1, "text": "Торонто", "is_correct": False},
                {"id": 21, "position": 2, "text": "Монреаль", "is_correct": False},
            ],
        },
    ],
}
# То же в виде тела PUT: без id, position и дат.
QUIZ_3_BODY = {
    "title": "Столицы мира",
    "description": "Разминка",
    "questions": [
        {"text": "Столица Австралии?", "time_limit_sec": 20, "options": [
            {"text": "Сидней", "is_correct": False}, {"text": "Канберра", "is_correct": True}]},
        {"text": "Столица Канады?", "time_limit_sec": 10, "options": [
            {"text": "Оттава", "is_correct": True}, {"text": "Торонто", "is_correct": False},
            {"text": "Монреаль", "is_correct": False}]},
    ],
}


@pytest.fixture
def window(qtbot, settings, server):
    server.routes["GET /api/quizzes"] = (200, [])
    server.routes["GET /api/quizzes/3"] = (200, QUIZ_3)
    settings.server_url = server.url
    w = MainWindow(settings)
    qtbot.addWidget(w)
    w.api.token = "jwt-token"
    return w


@pytest.fixture
def new(window):
    window.navigate("editor", quiz_id=None)
    return window._screens["editor"]


@pytest.fixture
def edit(qtbot, window):
    window.navigate("editor", quiz_id=3)
    e = window._screens["editor"]
    qtbot.waitUntil(lambda: e.view.currentWidget() is e._editor_widget, timeout=5000)
    return e


def sent(server, method):
    return [json.loads(r["body"]) for r in server.requests if r["method"] == method and r["path"].startswith("/api/quizzes")]


def list_texts(e):
    return [e.question_list.item(i).text() for i in range(e.question_list.count())]


# --- проверка правил ---

def _body(**changes):
    body = copy.deepcopy(QUIZ_3_BODY)
    body.update(changes)
    return body


def _q(**changes):
    q = copy.deepcopy(QUIZ_3_BODY["questions"][0])
    q.update(changes)
    return q


@pytest.mark.parametrize(
    "body, error",
    [
        (_body(), None),
        (_body(title=""), "Введите название викторины"),
        (_body(title="x" * 101), "Название длиннее 100 символов"),
        (_body(description="x" * 1001), "Описание длиннее 1000 символов"),
        (_body(questions=[]), "Добавьте хотя бы один вопрос"),
        (_body(questions=[_q()] * 51), "Вопросов больше 50"),
        (_body(questions=[_q(), _q(text="")]), "Вопрос 2: введите текст вопроса"),
        (_body(questions=[_q(time_limit_sec=4)]), "Вопрос 1: время на ответ от 5 до 120 секунд"),
        (_body(questions=[_q(options=[{"text": "a", "is_correct": True}])]), "Вопрос 1: нужно от 2 до 4 вариантов ответа"),
        (_body(questions=[_q(options=[{"text": "a", "is_correct": True}, {"text": "", "is_correct": False}])]),
         "Вопрос 1: введите текст варианта 2"),
        (_body(questions=[_q(options=[{"text": "a", "is_correct": False}, {"text": "b", "is_correct": False}])]),
         "Вопрос 1: отметьте один правильный вариант"),
    ],
)
def test_validate(body, error):
    assert validate_quiz(body) == error


# --- новая викторина ---

def test_new_quiz(qtbot, window, new, server):
    server.routes["POST /api/quizzes"] = (201, dict(QUIZ_3, id=7, title="Моя викторина"))
    assert new.heading.text() == "Новая викторина"
    assert list_texts(new) == ["1. (без текста)"]  # сразу один пустой вопрос

    new.title.setText("  Моя викторина ")
    new.q_text.setPlainText("2 + 2?")
    new._rows[0].text.setText("4")
    new._rows[1].text.setText("5")
    new.q_time.setValue(15)
    assert list_texts(new) == ["1. 2 + 2?"]  # список обновляется сразу

    new.save()
    qtbot.waitUntil(lambda: window.current_screen_name() == "quizzes", timeout=5000)
    assert sent(server, "POST") == [{
        "title": "Моя викторина",
        "description": "",
        "questions": [{"text": "2 + 2?", "time_limit_sec": 15, "options": [
            {"text": "4", "is_correct": True}, {"text": "5", "is_correct": False}]}],
    }]
    assert "сохранена" in window.statusBar().currentMessage()


def test_new_quiz_invalid_not_sent(new, server):
    new.save()
    assert new.error.text() == "Введите название викторины"
    assert sent(server, "POST") == []


def test_error_opens_question(new):
    new.title.setText("Викторина")
    new.q_text.setPlainText("Первый")
    new._rows[0].text.setText("a")
    new._rows[1].text.setText("b")
    new.add_question()  # второй вопрос пустой
    new.question_list.setCurrentRow(0)
    new.save()
    assert new.error.text() == "Вопрос 2: введите текст вопроса"
    assert new.question_list.currentRow() == 1


# --- изменение ---

def test_edit_loads_quiz(edit):
    assert edit.heading.text() == "Изменение викторины"
    assert edit.title.text() == "Столицы мира"
    assert edit.description.text() == "Разминка"
    assert list_texts(edit) == ["1. Столица Австралии?", "2. Столица Канады?"]
    assert edit.q_text.toPlainText() == "Столица Австралии?"
    assert edit._rows[1].correct.isChecked()
    assert edit._rows[2].text.isHidden()  # у первого вопроса два варианта
    # Тело для PUT без id и position: сервер выдаст их заново.
    assert edit.body() == QUIZ_3_BODY
    assert not edit.is_dirty()


def test_edit_and_save(qtbot, window, edit, server):
    server.routes["PUT /api/quizzes/3"] = (200, QUIZ_3)
    edit.question_list.setCurrentRow(1)
    assert edit.q_time.value() == 10
    edit._rows[1].correct.setChecked(True)  # правильный теперь «Торонто» (для теста)
    edit._rows[2].text.setText("Ванкувер")
    edit.question_list.setCurrentRow(0)  # правки второго вопроса не теряются при переходе
    assert edit.is_dirty()

    edit.save()
    qtbot.waitUntil(lambda: window.current_screen_name() == "quizzes", timeout=5000)
    body = sent(server, "PUT")[0]
    assert body["questions"][1]["options"] == [
        {"text": "Оттава", "is_correct": False},
        {"text": "Торонто", "is_correct": True},
        {"text": "Ванкувер", "is_correct": False},
    ]
    assert body["questions"][0] == QUIZ_3_BODY["questions"][0]


def test_edit_load_failed(qtbot, window, server):
    window.navigate("editor", quiz_id=99)
    e = window._screens["editor"]
    qtbot.waitUntil(lambda: "Не удалось открыть" in e.message.text(), timeout=5000)
    assert not e.save_button.isEnabled()


@pytest.mark.parametrize(
    "status, error, shown",
    [
        (422, {"error": "questions.0.text: String should have at most 300 characters"}, "questions.0.text"),
        (404, {"error": "викторина не найдена"}, "Викторину уже удалили"),
    ],
)
def test_save_failed(qtbot, window, edit, server, status, error, shown):
    server.routes["PUT /api/quizzes/3"] = (status, error)
    edit.save()
    qtbot.waitUntil(lambda: edit.save_button.isEnabled(), timeout=5000)
    assert shown in edit.error.text()
    assert window.current_screen_name() == "editor"


# --- вопросы ---

def test_add_remove_move_questions(edit):
    edit.question_list.setCurrentRow(0)
    edit.add_question()  # вставляется после текущего
    assert list_texts(edit) == ["1. Столица Австралии?", "2. (без текста)", "3. Столица Канады?"]
    assert edit.question_list.currentRow() == 1

    edit.q_text.setPlainText("Новый")
    edit.move_question(1)
    assert list_texts(edit) == ["1. Столица Австралии?", "2. Столица Канады?", "3. Новый"]
    assert edit.question_list.currentRow() == 2
    assert not edit.down_button.isEnabled()

    edit.remove_question()
    assert list_texts(edit) == ["1. Столица Австралии?", "2. Столица Канады?"]
    assert edit.question_list.currentRow() == 1


def test_last_question_cannot_be_removed(new):
    assert not new.remove_question_button.isEnabled()
    new.remove_question()
    assert new.question_list.count() == 1


# --- варианты ---

def test_options(edit):
    edit.add_option()
    edit.add_option()
    assert len(edit._questions[0]["options"]) == 4
    assert not edit.add_option_button.isEnabled()  # больше 4 нельзя

    edit.remove_option(1)  # удаляем правильный «Канберра»
    opts = edit._questions[0]["options"]
    assert [o["text"] for o in opts] == ["Сидней", "", ""]
    assert sum(o["is_correct"] for o in opts) == 1  # правильный вариант остался
    assert edit._rows[0].correct.isChecked()

    edit.remove_option(2)
    assert len(edit._questions[0]["options"]) == 2
    assert not edit._rows[0].remove.isEnabled()  # меньше 2 нельзя


# --- выход ---

@pytest.mark.parametrize("answer, leaves", [(QMessageBox.StandardButton.Yes, True), (QMessageBox.StandardButton.No, False)])
def test_back_with_changes_asks(monkeypatch, window, edit, answer, leaves):
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: asked.append(1) or answer)
    edit.title.setText("Другое название")
    edit.go_back()
    assert asked == [1]
    assert (window.current_screen_name() == "quizzes") == leaves


def test_back_without_changes(monkeypatch, window, edit):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: pytest.fail("не должен спрашивать"))
    edit.question_list.setCurrentRow(1)  # просто посмотрели — это не правка
    edit.go_back()
    assert window.current_screen_name() == "quizzes"
