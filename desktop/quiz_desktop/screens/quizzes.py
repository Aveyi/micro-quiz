"""«Мои викторины»: список викторин ведущего и действия с ними.

GET /api/quizzes и DELETE /api/quizzes/{id} — content (docs/quiz-design.md, 5.1).
Игру проводит экран host_game (участник 1): он сам создаёт комнату в live.
"""

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from quiz_desktop.api import ApiError
from quiz_desktop.screens.base import Screen


def format_time(value: str) -> str:
    """'2026-10-24T10:28:00.123456Z' → '24.10.2026 13:28' в часовом поясе компьютера."""
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return value


class QuizzesScreen(Screen):
    def __init__(self, window):
        super().__init__(window)
        self._quizzes: list[dict] = []
        # Номер последнего запроса списка. Если «Обновить» нажали дважды, ответ
        # на первый запрос может прийти позже второго — его нужно отбросить.
        self._load_seq = 0

        title = QLabel("Мои викторины")
        font = QFont()
        font.setPointSize(18)
        font.setBold(True)
        title.setFont(font)

        self.create_button = QPushButton("+ Создать")
        self.create_button.clicked.connect(lambda: self.navigate("editor", quiz_id=None))
        self.history_button = QPushButton("История игр")
        self.history_button.clicked.connect(lambda: self.navigate("history"))
        self.refresh_button = QPushButton("Обновить")
        self.refresh_button.clicked.connect(lambda: self.load())

        top = QHBoxLayout()
        top.addWidget(title)
        top.addStretch()
        top.addWidget(self.history_button)
        top.addWidget(self.refresh_button)
        top.addWidget(self.create_button)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Название", "Вопросов", "Изменена"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.cellDoubleClicked.connect(lambda row, _: self.edit_selected())

        # Вместо таблицы показываем текст, когда викторин нет, идёт загрузка или ошибка.
        self.message = QLabel()
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setWordWrap(True)
        self.content = QStackedWidget()
        self.content.addWidget(self.table)
        self.content.addWidget(self.message)

        self.play_button = QPushButton("▶ Провести игру")
        self.play_button.clicked.connect(self.play_selected)
        self.edit_button = QPushButton("Изменить")
        self.edit_button.clicked.connect(self.edit_selected)
        self.delete_button = QPushButton("Удалить")
        self.delete_button.clicked.connect(self.delete_selected)
        self.status = QLabel()
        self.status.setStyleSheet("color: #c00")

        bottom = QHBoxLayout()
        bottom.addWidget(self.status, stretch=1)
        bottom.addWidget(self.delete_button)
        bottom.addWidget(self.edit_button)
        bottom.addWidget(self.play_button)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.content, stretch=1)
        layout.addLayout(bottom)

        self._update_buttons()

    def entered(self, **params) -> None:
        self.load()

    # --- список ---

    def load(self, notice: str = "") -> None:
        """Перезагружает список. notice — что написать под списком вместо старых ошибок."""
        self._load_seq += 1
        seq = self._load_seq
        self.status.setText(notice)
        if not self._quizzes:
            self._show_message("Загрузка…")
        reply = self.api.get("/api/quizzes", auth=True)
        reply.succeeded.connect(lambda data: seq == self._load_seq and self._show_quizzes(data))
        reply.failed.connect(lambda err: seq == self._load_seq and self._on_load_failed(err))

    def _show_quizzes(self, quizzes: list[dict]) -> None:
        selected = self.selected_quiz()
        self._quizzes = quizzes
        self.table.setRowCount(len(quizzes))
        for row, quiz in enumerate(quizzes):
            title = QTableWidgetItem(quiz["title"])
            # id храним в ячейке: строки таблицы можно будет сортировать,
            # и номер строки перестанет совпадать с индексом в списке.
            title.setData(Qt.ItemDataRole.UserRole, quiz["id"])
            count = QTableWidgetItem(str(quiz["question_count"]))
            count.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, title)
            self.table.setItem(row, 1, count)
            self.table.setItem(row, 2, QTableWidgetItem(format_time(quiz["updated_at"])))
            if selected and quiz["id"] == selected["id"]:
                self.table.selectRow(row)  # после обновления выделение не теряется

        if quizzes:
            self.content.setCurrentWidget(self.table)
        else:
            self._show_message("У вас пока нет викторин.\nНажмите «+ Создать», чтобы сделать первую.")
        self._update_buttons()

    def _on_load_failed(self, error: ApiError) -> None:
        if error.status == 401:
            return  # главное окно само откроет экран входа
        if self._quizzes:
            self.status.setText(f"Не удалось обновить список: {error}")
        else:
            self._show_message(f"Не удалось загрузить викторины:\n{error}")

    def _show_message(self, text: str) -> None:
        self.message.setText(text)
        self.content.setCurrentWidget(self.message)

    # --- выбранная викторина ---

    def selected_quiz(self) -> dict | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        quiz_id = self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        return next((q for q in self._quizzes if q["id"] == quiz_id), None)

    def _update_buttons(self, busy: bool = False) -> None:
        has = self.selected_quiz() is not None
        for button in (self.play_button, self.edit_button, self.delete_button):
            button.setEnabled(has and not busy)

    def edit_selected(self) -> None:
        quiz = self.selected_quiz()
        if quiz:
            self.navigate("editor", quiz_id=quiz["id"])

    def delete_selected(self) -> None:
        quiz = self.selected_quiz()
        if not quiz:
            return
        answer = QMessageBox.question(
            self,
            "Удалить викторину",
            f"Удалить викторину «{quiz['title']}»? Это нельзя отменить.\n"
            "История уже проведённых игр сохранится.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._update_buttons(busy=True)
        reply = self.api.delete(f"/api/quizzes/{quiz['id']}", auth=True)
        reply.succeeded.connect(lambda _: self.load())
        reply.failed.connect(self._on_action_failed)

    def play_selected(self) -> None:
        quiz = self.selected_quiz()
        if quiz:
            # Экран ведущего сам создаёт комнату (POST /live/api/rooms)
            # и подключается к ней по WebSocket.
            self.navigate("host_game", quiz_id=quiz["id"])

    def _on_action_failed(self, error: ApiError) -> None:
        self._update_buttons()
        if error.status == 401:
            return
        if error.status == 404:
            # Викторину удалили, например, в другом окне приложения.
            self.load(notice="Викторина не найдена — список обновлён")
            return
        self.status.setText(str(error))
