"""История игр ведущего и результаты выбранной игры.

GET /live/api/games и /live/api/games/{id} — live (docs/quiz-design.md, 5.3).
Текстов вопросов в live нет, только question_id: тексты берутся
из content, GET /api/quizzes/{quiz_id} (5.1).
"""

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from quiz_desktop.api import ApiError
from quiz_desktop.screens.base import Screen
from quiz_desktop.screens.quizzes import format_time

STATUS_NAMES = {
    "lobby": "в лобби",
    "running": "идёт",
    "finished": "завершена",
    "cancelled": "прервана",
}


def format_duration(started: str | None, finished: str | None) -> str:
    """Сколько шла игра: '4:05'. Пусто, если игра не начиналась или ещё идёт."""
    if not started or not finished:
        return ""
    try:
        seconds = int((datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds())
    except ValueError:
        return ""
    return f"{seconds // 60}:{seconds % 60:02d}"


def _table(headers: list[str], stretch: int) -> QTableWidget:
    """Таблица только для чтения; столбец stretch занимает оставшееся место."""
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.verticalHeader().hide()
    header = table.horizontalHeader()
    for col in range(len(headers)):
        mode = QHeaderView.ResizeMode.Stretch if col == stretch else QHeaderView.ResizeMode.ResizeToContents
        header.setSectionResizeMode(col, mode)
    return table


def _item(text, center: bool = False) -> QTableWidgetItem:
    item = QTableWidgetItem("" if text is None else str(text))
    if center:
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    return item


class HistoryScreen(Screen):
    def __init__(self, window):
        super().__init__(window)
        self._games: list[dict] = []
        # Тексты вопросов по quiz_id: {question_id: текст} или None, если викторину удалили.
        self._question_texts: dict[int, dict[int, str] | None] = {}
        # Номера последних запросов: ответ на устаревший запрос отбрасываем
        # (например, быстро щёлкнули по двум играм подряд).
        self._list_seq = 0
        self._details_seq = 0

        title = QLabel("История игр")
        font = QFont()
        font.setPointSize(18)
        font.setBold(True)
        title.setFont(font)
        back = QPushButton("← К викторинам")
        back.clicked.connect(lambda: self.navigate("quizzes"))
        self.refresh_button = QPushButton("Обновить")
        self.refresh_button.clicked.connect(lambda: self.load())
        top = QHBoxLayout()
        top.addWidget(back)
        top.addWidget(title)
        top.addStretch()
        top.addWidget(self.refresh_button)

        # --- слева: список игр ---
        self.games = _table(["Викторина", "Дата", "Статус", "Игроков"], stretch=0)
        self.games.itemSelectionChanged.connect(self._on_game_selected)
        self.list_message = QLabel()
        self.list_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.list_message.setWordWrap(True)
        self.list_view = QStackedWidget()
        self.list_view.addWidget(self.games)
        self.list_view.addWidget(self.list_message)

        # --- справа: результаты выбранной игры ---
        self.d_title = QLabel()
        bold = QFont()
        bold.setPointSize(14)
        bold.setBold(True)
        self.d_title.setFont(bold)
        self.d_info = QLabel()
        self.d_info.setWordWrap(True)
        self.players = _table(["Место", "Игрок", "Очки"], stretch=1)
        self.questions = _table(["№", "Вопрос", "Ответили", "Верно", "Доля верных"], stretch=1)
        self.d_note = QLabel()
        self.d_note.setStyleSheet("color: gray")
        self.d_note.setWordWrap(True)

        details = QWidget()
        d_layout = QVBoxLayout(details)
        d_layout.setContentsMargins(0, 0, 0, 0)
        d_layout.addWidget(self.d_title)
        d_layout.addWidget(self.d_info)
        d_layout.addWidget(QLabel("Игроки:"))
        d_layout.addWidget(self.players, stretch=1)
        d_layout.addWidget(QLabel("Вопросы:"))
        d_layout.addWidget(self.questions, stretch=1)
        d_layout.addWidget(self.d_note)

        self.details_message = QLabel("Выберите игру слева")
        self.details_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.details_message.setWordWrap(True)
        self.details_view = QStackedWidget()
        self.details_view.addWidget(details)
        self.details_view.addWidget(self.details_message)
        self.details_view.setCurrentWidget(self.details_message)
        self._details_widget = details

        splitter = QSplitter()
        splitter.addWidget(self.list_view)
        splitter.addWidget(self.details_view)
        splitter.setSizes([420, 540])

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(splitter, stretch=1)

    def entered(self, **params) -> None:
        # Викторины могли изменить с прошлого раза — тексты вопросов перечитаем.
        self._question_texts.clear()
        self.load()

    # --- список игр ---

    def load(self) -> None:
        self._list_seq += 1
        seq = self._list_seq
        if not self._games:
            self._show_list_message("Загрузка…")
        reply = self.window_.live_api().get("/live/api/games", auth=True)
        reply.succeeded.connect(lambda data: seq == self._list_seq and self._show_games(data))
        reply.failed.connect(lambda err: seq == self._list_seq and self._on_list_failed(err))

    def _show_games(self, games: list[dict]) -> None:
        selected = self.selected_game_id()
        self._games = games
        self.games.blockSignals(True)  # заполнение таблицы — не выбор пользователя
        self.games.clearSelection()
        self.games.setRowCount(len(games))
        for row, game in enumerate(games):
            title = _item(game["quiz_title"])
            title.setData(Qt.ItemDataRole.UserRole, game["id"])
            self.games.setItem(row, 0, title)
            self.games.setItem(row, 1, _item(format_time(game["created_at"])))
            self.games.setItem(row, 2, _item(STATUS_NAMES.get(game["status"], game["status"])))
            self.games.setItem(row, 3, _item(game["player_count"], center=True))
        self.games.blockSignals(False)

        if not games:
            self._show_list_message("Вы ещё не провели ни одной игры.\nЗапустите викторину кнопкой «Провести игру».")
            self.details_view.setCurrentWidget(self.details_message)
            return
        self.list_view.setCurrentWidget(self.games)
        ids = [g["id"] for g in games]
        # После обновления остаёмся на той же игре, иначе выбираем самую новую.
        self.games.selectRow(ids.index(selected) if selected in ids else 0)

    def _on_list_failed(self, error: ApiError) -> None:
        if error.status == 401:
            return  # главное окно само откроет экран входа
        self._show_list_message(f"Не удалось загрузить историю:\n{error}")

    def _show_list_message(self, text: str) -> None:
        self.list_message.setText(text)
        self.list_view.setCurrentWidget(self.list_message)

    def selected_game_id(self) -> int | None:
        rows = self.games.selectionModel().selectedRows()
        if not rows:
            return None
        return self.games.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)

    # --- результаты игры ---

    def _on_game_selected(self) -> None:
        game_id = self.selected_game_id()
        if game_id is None:
            return
        self._details_seq += 1
        seq = self._details_seq
        self.details_message.setText("Загрузка…")
        self.details_view.setCurrentWidget(self.details_message)
        reply = self.window_.live_api().get(f"/live/api/games/{game_id}", auth=True)
        reply.succeeded.connect(lambda data: seq == self._details_seq and self._with_question_texts(seq, data))
        reply.failed.connect(lambda err: seq == self._details_seq and self._on_details_failed(err))

    def _with_question_texts(self, seq: int, game: dict) -> None:
        """Показывает игру, когда известны тексты её вопросов (из кэша или из content)."""
        quiz_id = game["quiz_id"]
        if quiz_id in self._question_texts or not game["questions"]:
            self._show_details(game)
            return
        reply = self.api.get(f"/api/quizzes/{quiz_id}", auth=True)

        def got(quiz: dict) -> None:
            self._question_texts[quiz_id] = {q["id"]: q["text"] for q in quiz["questions"]}
            if seq == self._details_seq:
                self._show_details(game)

        def failed(error: ApiError) -> None:
            if error.status == 404:
                self._question_texts[quiz_id] = None  # викторину удалили, спрашивать снова незачем
            if seq == self._details_seq:
                # Тексты не обязательны: без них покажем номера вопросов.
                self._show_details(game)

        reply.succeeded.connect(got)
        reply.failed.connect(failed)

    def _show_details(self, game: dict) -> None:
        self.d_title.setText(game["quiz_title"])
        info = [f"Статус: {STATUS_NAMES.get(game['status'], game['status'])}"]
        if game.get("started_at"):
            info.append(f"начало: {format_time(game['started_at'])}")
        duration = format_duration(game.get("started_at"), game.get("finished_at"))
        if duration:
            info.append(f"длительность: {duration}")
        info.append(f"игроков: {game['player_count']}")
        self.d_info.setText(", ".join(info))

        players = game["players"]
        self.players.setRowCount(len(players))
        for row, p in enumerate(players):
            nickname = p["nickname"] + (" (выбыл)" if p.get("left") else "")
            # rank и score — null, если игра не дошла до конца (раздел 5.3).
            self.players.setItem(row, 0, _item(p["rank"] if p["rank"] is not None else "—", center=True))
            self.players.setItem(row, 1, _item(nickname))
            self.players.setItem(row, 2, _item(p["score"] if p["score"] is not None else "—", center=True))

        texts = self._question_texts.get(game["quiz_id"]) or {}
        missing = False
        questions = game["questions"]
        self.questions.setRowCount(len(questions))
        for row, q in enumerate(questions):
            text = texts.get(q["question_id"])
            if text is None:
                # Викторину удалили или после игры переписали (PUT выдаёт вопросам новые id).
                missing = True
                text = "—"
            self.questions.setItem(row, 0, _item(q["question_index"] + 1, center=True))
            self.questions.setItem(row, 1, _item(text))
            self.questions.setItem(row, 2, _item(f"{q['answered']} из {q['total']}", center=True))
            self.questions.setItem(row, 3, _item(q["correct"], center=True))
            self.questions.setItem(row, 4, _item(f"{round(q['correct_ratio'] * 100)}%", center=True))

        notes = []
        if game["status"] != "finished":
            notes.append("Игра не дошла до конца, поэтому мест и очков нет.")
        if missing:
            notes.append("Тексты некоторых вопросов недоступны: викторину удалили или изменили после игры.")
        if not questions:
            notes.append("До вопросов игра не дошла.")
        self.d_note.setText(" ".join(notes))
        self.details_view.setCurrentWidget(self._details_widget)

    def _on_details_failed(self, error: ApiError) -> None:
        if error.status == 401:
            return
        self.details_message.setText(f"Не удалось загрузить результаты игры:\n{error}")
        self.details_view.setCurrentWidget(self.details_message)
