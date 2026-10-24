"""Редактор викторины: создание (POST /api/quizzes) и изменение (PUT /api/quizzes/{id}).

Викторина сохраняется целиком, вместе со всеми вопросами
(docs/quiz-design.md, раздел 5.1): так проще, чем править вопросы по одному.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from quiz_desktop.api import ApiError
from quiz_desktop.screens.base import Screen

# Правила те же, что проверяет content (docs/quiz-design.md, раздел 5.1).
# Здесь они нужны, чтобы показать ошибку сразу и с номером вопроса;
# окончательно всё равно решает сервер.
MAX_TITLE = 100
MAX_DESCRIPTION = 1000
MAX_QUESTIONS = 50
MAX_QUESTION_TEXT = 300
MIN_OPTIONS, MAX_OPTIONS = 2, 4
MAX_OPTION_TEXT = 100
MIN_TIME, MAX_TIME, DEFAULT_TIME = 5, 120, 20


def new_question() -> dict:
    return {
        "text": "",
        "time_limit_sec": DEFAULT_TIME,
        "options": [{"text": "", "is_correct": True}, {"text": "", "is_correct": False}],
    }


def validate_quiz(body: dict) -> str | None:
    """Текст первой ошибки или None. body — как в POST /api/quizzes, уже без пробелов по краям."""
    if not body["title"]:
        return "Введите название викторины"
    if len(body["title"]) > MAX_TITLE:
        return f"Название длиннее {MAX_TITLE} символов"
    if len(body["description"]) > MAX_DESCRIPTION:
        return f"Описание длиннее {MAX_DESCRIPTION} символов"
    questions = body["questions"]
    if not questions:
        return "Добавьте хотя бы один вопрос"
    if len(questions) > MAX_QUESTIONS:
        return f"Вопросов больше {MAX_QUESTIONS}"
    for n, q in enumerate(questions, start=1):
        if not q["text"]:
            return f"Вопрос {n}: введите текст вопроса"
        if len(q["text"]) > MAX_QUESTION_TEXT:
            return f"Вопрос {n}: текст длиннее {MAX_QUESTION_TEXT} символов"
        if not MIN_TIME <= q["time_limit_sec"] <= MAX_TIME:
            return f"Вопрос {n}: время на ответ от {MIN_TIME} до {MAX_TIME} секунд"
        if not MIN_OPTIONS <= len(q["options"]) <= MAX_OPTIONS:
            return f"Вопрос {n}: нужно от {MIN_OPTIONS} до {MAX_OPTIONS} вариантов ответа"
        for m, o in enumerate(q["options"], start=1):
            if not o["text"]:
                return f"Вопрос {n}: введите текст варианта {m}"
            if len(o["text"]) > MAX_OPTION_TEXT:
                return f"Вопрос {n}: вариант {m} длиннее {MAX_OPTION_TEXT} символов"
        if sum(o["is_correct"] for o in q["options"]) != 1:
            return f"Вопрос {n}: отметьте один правильный вариант"
    return None


class _OptionRow:
    """Строка варианта ответа: «правильный» + текст + удалить."""

    def __init__(self, number: int):
        self.correct = QRadioButton()
        self.correct.setToolTip("Правильный ответ")
        self.text = QLineEdit()
        self.text.setPlaceholderText(f"Вариант {number}")
        self.text.setMaxLength(MAX_OPTION_TEXT)
        self.remove = QToolButton()
        self.remove.setText("✕")
        self.remove.setToolTip("Удалить вариант")

    def set_visible(self, visible: bool) -> None:
        for w in (self.correct, self.text, self.remove):
            w.setVisible(visible)


class EditorScreen(Screen):
    def __init__(self, window):
        super().__init__(window)
        self.quiz_id: int | None = None
        self._questions: list[dict] = []
        self._current = -1  # номер вопроса, открытого справа
        self._saved_body: dict | None = None  # что было при загрузке — чтобы понять, есть ли изменения
        self._load_seq = 0
        self._filling = False  # заполняем поля из данных — это не правка пользователя

        # --- шапка ---
        self.heading = QLabel()
        font = QFont()
        font.setPointSize(18)
        font.setBold(True)
        self.heading.setFont(font)
        self.back_button = QPushButton("← К викторинам")
        self.back_button.clicked.connect(self.go_back)
        self.save_button = QPushButton("Сохранить")
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.save)
        top = QHBoxLayout()
        top.addWidget(self.back_button)
        top.addWidget(self.heading)
        top.addStretch()
        top.addWidget(self.save_button)

        self.title = QLineEdit()
        self.title.setMaxLength(MAX_TITLE)
        self.title.setPlaceholderText("Например: Столицы мира")
        self.description = QLineEdit()
        self.description.setMaxLength(MAX_DESCRIPTION)
        self.description.setPlaceholderText("Необязательно")
        meta = QFormLayout()
        meta.addRow("Название:", self.title)
        meta.addRow("Описание:", self.description)

        # --- слева: список вопросов ---
        self.question_list = QListWidget()
        self.question_list.currentRowChanged.connect(self._on_question_selected)
        self.add_question_button = QPushButton("+ Вопрос")
        self.add_question_button.clicked.connect(self.add_question)
        self.remove_question_button = QPushButton("Удалить")
        self.remove_question_button.clicked.connect(self.remove_question)
        self.up_button = QToolButton()
        self.up_button.setText("↑")
        self.up_button.setToolTip("Выше")
        self.up_button.clicked.connect(lambda: self.move_question(-1))
        self.down_button = QToolButton()
        self.down_button.setText("↓")
        self.down_button.setToolTip("Ниже")
        self.down_button.clicked.connect(lambda: self.move_question(1))
        list_buttons = QHBoxLayout()
        list_buttons.addWidget(self.add_question_button)
        list_buttons.addWidget(self.remove_question_button)
        list_buttons.addStretch()
        list_buttons.addWidget(self.up_button)
        list_buttons.addWidget(self.down_button)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Вопросы:"))
        left_layout.addWidget(self.question_list, stretch=1)
        left_layout.addLayout(list_buttons)

        # --- справа: выбранный вопрос ---
        self.q_number = QLabel()
        self.q_text = QPlainTextEdit()
        self.q_text.setPlaceholderText("Текст вопроса")
        self.q_text.setFixedHeight(80)
        self.q_time = QSpinBox()
        self.q_time.setRange(MIN_TIME, MAX_TIME)
        self.q_time.setSuffix(" с")

        # Радиокнопки в одной группе: правильным может быть только один вариант.
        self._correct_group = QButtonGroup(self)
        self._rows = [_OptionRow(i + 1) for i in range(MAX_OPTIONS)]
        options = QGridLayout()
        for i, row in enumerate(self._rows):
            self._correct_group.addButton(row.correct, i)
            options.addWidget(row.correct, i, 0)
            options.addWidget(row.text, i, 1)
            options.addWidget(row.remove, i, 2)
            row.remove.clicked.connect(lambda _=False, i=i: self.remove_option(i))
        self.add_option_button = QPushButton("+ Вариант")
        self.add_option_button.clicked.connect(self.add_option)

        form = QFormLayout()
        form.addRow(self.q_number)
        form.addRow("Вопрос:", self.q_text)
        form.addRow("Время на ответ:", self.q_time)
        form.addRow(QLabel("Варианты ответа (отметьте правильный):"))
        form.addRow(options)
        form.addRow(self.add_option_button)
        self.add_option_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addLayout(form)
        # Растяжка снизу прижимает поля к верху, а не раздвигает их по высоте.
        right_layout.addStretch()

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([320, 640])

        self.error = QLabel()
        self.error.setStyleSheet("color: #c00")
        self.error.setWordWrap(True)

        editor = QWidget()
        editor_layout = QVBoxLayout(editor)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.addLayout(meta)
        editor_layout.addWidget(splitter, stretch=1)
        editor_layout.addWidget(self.error)
        self._editor_widget = editor

        # Пока викторина грузится или не загрузилась — сообщение вместо формы.
        self.message = QLabel()
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setWordWrap(True)
        self.view = QStackedWidget()
        self.view.addWidget(editor)
        self.view.addWidget(self.message)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.view, stretch=1)

        # Правки текста вопроса сразу видны в списке слева.
        self.q_text.textChanged.connect(self._on_question_edited)

    # --- открытие ---

    def entered(self, quiz_id: int | None = None, **params) -> None:
        self.quiz_id = quiz_id
        self._load_seq += 1
        self.error.clear()
        self._set_busy(False)
        if quiz_id is None:
            self.heading.setText("Новая викторина")
            self._fill({"title": "", "description": "", "questions": [new_question()]})
            self.title.setFocus()
            return

        self.heading.setText("Изменение викторины")
        self.message.setText("Загрузка…")
        self.view.setCurrentWidget(self.message)
        self.save_button.setEnabled(False)
        seq = self._load_seq
        reply = self.api.get(f"/api/quizzes/{quiz_id}", auth=True)
        reply.succeeded.connect(lambda quiz: seq == self._load_seq and self._fill(quiz))
        reply.failed.connect(lambda err: seq == self._load_seq and self._on_load_failed(err))

    def _on_load_failed(self, error: ApiError) -> None:
        if error.status == 401:
            return
        self.message.setText(f"Не удалось открыть викторину:\n{error}")

    def _fill(self, quiz: dict) -> None:
        """Показывает викторину в форме. quiz — из GET /api/quizzes/{id} или пустая."""
        self._filling = True
        self.title.setText(quiz["title"])
        self.description.setText(quiz["description"])
        # Оставляем только поля, которые уходят в PUT: id и position сервер выдаст заново.
        self._questions = [
            {
                "text": q["text"],
                "time_limit_sec": q["time_limit_sec"],
                "options": [{"text": o["text"], "is_correct": o["is_correct"]} for o in q["options"]],
            }
            for q in quiz["questions"]
        ]
        self._current = -1
        self._rebuild_list(select=0)
        self._filling = False
        self._saved_body = self.body()
        self.view.setCurrentWidget(self._editor_widget)
        self.save_button.setEnabled(True)

    # --- данные формы ---

    def body(self) -> dict:
        """Тело для POST/PUT /api/quizzes из текущего состояния формы."""
        self._store_current()
        return {
            "title": self.title.text().strip(),
            "description": self.description.text().strip(),
            "questions": [
                {
                    "text": q["text"].strip(),
                    "time_limit_sec": q["time_limit_sec"],
                    "options": [{"text": o["text"].strip(), "is_correct": o["is_correct"]} for o in q["options"]],
                }
                for q in self._questions
            ],
        }

    def is_dirty(self) -> bool:
        return self._saved_body is not None and self.body() != self._saved_body

    def _store_current(self) -> None:
        """Переносит поля справа в данные открытого вопроса."""
        if not 0 <= self._current < len(self._questions):
            return
        q = self._questions[self._current]
        q["text"] = self.q_text.toPlainText()
        q["time_limit_sec"] = self.q_time.value()
        checked = self._correct_group.checkedId()
        for i, o in enumerate(q["options"]):
            o["text"] = self._rows[i].text.text()
            o["is_correct"] = i == checked

    def _show_question(self, index: int) -> None:
        """Заполняет поля справа данными вопроса index."""
        self._current = index
        q = self._questions[index]
        filling, self._filling = self._filling, True
        self.q_number.setText(f"Вопрос {index + 1} из {len(self._questions)}")
        self.q_text.setPlainText(q["text"])
        self.q_time.setValue(q["time_limit_sec"])
        # Сначала снимаем отметку со всех: иначе в эксклюзивной группе её не снять.
        self._correct_group.setExclusive(False)
        for i, row in enumerate(self._rows):
            present = i < len(q["options"])
            row.set_visible(present)
            row.text.setText(q["options"][i]["text"] if present else "")
            row.correct.setChecked(present and q["options"][i]["is_correct"])
            row.remove.setEnabled(len(q["options"]) > MIN_OPTIONS)
        self._correct_group.setExclusive(True)
        self.add_option_button.setEnabled(len(q["options"]) < MAX_OPTIONS)
        self._filling = filling
        self._update_list_buttons()

    # --- список вопросов ---

    @staticmethod
    def _list_title(n: int, q: dict) -> str:
        text = " ".join(q["text"].split()) or "(без текста)"
        return f"{n}. {text[:40] + '…' if len(text) > 40 else text}"

    def _rebuild_list(self, select: int) -> None:
        self.question_list.blockSignals(True)
        self.question_list.clear()
        for n, q in enumerate(self._questions, start=1):
            self.question_list.addItem(self._list_title(n, q))
        self.question_list.blockSignals(False)
        self._current = -1
        self.question_list.setCurrentRow(select)
        self._show_question(select)

    def _on_question_selected(self, row: int) -> None:
        if row < 0 or row == self._current:
            return
        self._store_current()
        self._show_question(row)

    def _on_question_edited(self) -> None:
        if self._filling or self._current < 0:
            return
        item = self.question_list.item(self._current)
        if item:
            item.setText(self._list_title(self._current + 1, {"text": self.q_text.toPlainText()}))

    def _update_list_buttons(self) -> None:
        count = len(self._questions)
        self.add_question_button.setEnabled(count < MAX_QUESTIONS)
        self.remove_question_button.setEnabled(count > 1)
        self.up_button.setEnabled(self._current > 0)
        self.down_button.setEnabled(0 <= self._current < count - 1)

    def add_question(self) -> None:
        if len(self._questions) >= MAX_QUESTIONS:
            return
        self._store_current()
        self._questions.insert(self._current + 1, new_question())
        self._rebuild_list(select=self._current + 1)
        self.q_text.setFocus()

    def remove_question(self) -> None:
        if len(self._questions) <= 1:
            return
        self._store_current()
        index = self._current
        del self._questions[index]
        self._rebuild_list(select=min(index, len(self._questions) - 1))

    def move_question(self, delta: int) -> None:
        self._store_current()
        i, j = self._current, self._current + delta
        if not 0 <= j < len(self._questions):
            return
        self._questions[i], self._questions[j] = self._questions[j], self._questions[i]
        self._rebuild_list(select=j)

    # --- варианты ответа ---

    def add_option(self) -> None:
        self._store_current()
        options = self._questions[self._current]["options"]
        if len(options) >= MAX_OPTIONS:
            return
        options.append({"text": "", "is_correct": False})
        self._show_question(self._current)
        self._rows[len(options) - 1].text.setFocus()

    def remove_option(self, index: int) -> None:
        self._store_current()
        options = self._questions[self._current]["options"]
        if len(options) <= MIN_OPTIONS:
            return
        removed = options.pop(index)
        if removed["is_correct"]:
            options[0]["is_correct"] = True  # правильный вариант должен остаться
        self._show_question(self._current)

    # --- сохранение и выход ---

    def save(self) -> None:
        if not self.save_button.isEnabled():
            return
        body = self.body()
        problem = validate_quiz(body)
        if problem:
            self.error.setText(problem)
            self._select_question_from_error(problem)
            return
        self.error.clear()
        self._set_busy(True)
        if self.quiz_id is None:
            reply = self.api.post("/api/quizzes", body, auth=True)
        else:
            reply = self.api.put(f"/api/quizzes/{self.quiz_id}", body, auth=True)
        reply.succeeded.connect(self._on_saved)
        reply.failed.connect(self._on_save_failed)

    def _select_question_from_error(self, problem: str) -> None:
        # «Вопрос 3: …» — открываем этот вопрос, чтобы было видно, что исправить.
        if problem.startswith("Вопрос "):
            number = problem.split()[1].rstrip(":")
            if number.isdigit():
                self.question_list.setCurrentRow(int(number) - 1)

    def _on_saved(self, quiz: dict) -> None:
        self._set_busy(False)
        self._saved_body = self.body()
        self.window_.statusBar().showMessage(f"Викторина «{quiz['title']}» сохранена", 5000)
        self.navigate("quizzes")

    def _on_save_failed(self, error: ApiError) -> None:
        self._set_busy(False)
        if error.status == 401:
            return  # окно откроет экран входа; несохранённые правки, увы, пропадут
        if error.status == 404:
            self.error.setText("Викторину уже удалили — сохранить изменения нельзя")
            return
        self.error.setText(str(error))

    def _set_busy(self, busy: bool) -> None:
        self.save_button.setEnabled(not busy)
        self.save_button.setText("Сохраняем…" if busy else "Сохранить")

    def go_back(self) -> None:
        if self.view.currentWidget() is self._editor_widget and self.is_dirty():
            answer = QMessageBox.question(
                self,
                "Несохранённые изменения",
                "Выйти без сохранения? Изменения пропадут.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.navigate("quizzes")
