"""Экран ведущего: комната → лобби → вопросы → итоги.

Открывается из списка викторин: navigate("host_game", quiz_id=3) — экран
сам создаёт комнату (POST /live/api/rooms) и подключается к ней по
WebSocket с токеном ведущего. Протокол — docs/quiz-design.md, разделы 3–5.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from quiz_desktop.api import ApiClient
from quiz_desktop.live_client import LiveClient, live_http_base
from quiz_desktop.screens.base import Screen
from quiz_desktop.screens.game_common import (
    ROOM_CLOSED_REASONS,
    AnswerStats,
    Countdown,
    Leaderboard,
    OptionButtons,
    big_label,
)

# Куда возвращаться после игры: к списку викторин, если он уже есть.
BACK_SCREENS = ("quizzes", "start")


class HostScreen(Screen):
    def __init__(self, window):
        super().__init__(window)
        self.live: LiveClient | None = None
        self._reset_game_state()

        self.views = QStackedWidget()
        self._build_message()
        self._build_lobby()
        self._build_question()
        self._build_result()
        self._build_final()

        layout = QVBoxLayout(self)
        layout.addWidget(self.views)

    def _reset_game_state(self) -> None:
        self.quiz_id: int | None = None
        self.room_code = ""
        self.question: dict | None = None
        self.question_count = 0
        self.player_count = 0
        self._room_closed = ""
        self._game_over = False

    # --- виды ---

    def _build_message(self) -> None:
        """Служебный вид: «создаём комнату…» или ошибка с кнопкой «Назад»."""
        self.m_text = big_label(size=18, bold=False)
        self.m_back = QPushButton("← К викторинам")
        self.m_back.clicked.connect(self.go_back)
        view = QWidget()
        layout = QVBoxLayout(view)
        layout.addStretch()
        layout.addWidget(self.m_text)
        layout.addWidget(self.m_back, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
        self.message_view = view
        self.views.addWidget(view)

    def _build_lobby(self) -> None:
        self.l_title = big_label(size=16, bold=False)
        self.l_code = big_label(size=48)
        self.l_code.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.l_count = QLabel()
        self.l_players = QListWidget()
        self.start_button = QPushButton("Начать игру")
        self.start_button.setMinimumHeight(44)
        self.start_button.clicked.connect(self.start_game)

        view = QWidget()
        layout = QVBoxLayout(view)
        layout.addWidget(self.l_title)
        layout.addWidget(big_label("Код комнаты — продиктуйте его игрокам:", 12, bold=False))
        layout.addWidget(self.l_code)
        layout.addWidget(self.l_count)
        layout.addWidget(self.l_players)
        buttons = QHBoxLayout()
        buttons.addWidget(self._close_button())
        buttons.addStretch()
        buttons.addWidget(self.start_button)
        layout.addLayout(buttons)
        self.lobby_view = view
        self.views.addWidget(view)

    def _build_question(self) -> None:
        self.q_header = big_label(size=12, bold=False)
        self.q_text = big_label(size=22)
        self.countdown = Countdown()
        self.options = OptionButtons()  # ведущий только показывает варианты
        self.q_progress = big_label(size=16, bold=False)

        view = QWidget()
        layout = QVBoxLayout(view)
        layout.addWidget(self.q_header)
        layout.addWidget(self.q_text)
        layout.addWidget(self.countdown)
        layout.addWidget(self.options, stretch=1)
        layout.addWidget(self.q_progress)
        layout.addWidget(self._close_button(), alignment=Qt.AlignmentFlag.AlignLeft)
        self.question_view = view
        self.views.addWidget(view)

    def _build_result(self) -> None:
        self.r_header = big_label(size=16)
        self.r_stats = AnswerStats()
        self.r_board = Leaderboard()
        self.next_button = QPushButton("Следующий вопрос")
        self.next_button.setMinimumHeight(44)
        self.next_button.clicked.connect(self.next_question)

        view = QWidget()
        layout = QVBoxLayout(view)
        layout.addWidget(self.r_header)
        layout.addWidget(self.r_stats)
        layout.addWidget(QLabel("Таблица лидеров (первые 10):"))
        layout.addWidget(self.r_board, stretch=1)
        buttons = QHBoxLayout()
        buttons.addWidget(self._close_button())
        buttons.addStretch()
        buttons.addWidget(self.next_button)
        layout.addLayout(buttons)
        self.result_view = view
        self.views.addWidget(view)

    def _build_final(self) -> None:
        self.f_title = big_label(size=26)
        self.f_subtitle = big_label(size=14, bold=False)
        self.f_board = Leaderboard()
        done = QPushButton("Готово")
        done.clicked.connect(self.go_back)
        view = QWidget()
        layout = QVBoxLayout(view)
        layout.addWidget(self.f_title)
        layout.addWidget(self.f_subtitle)
        layout.addWidget(self.f_board, stretch=1)
        layout.addWidget(done, alignment=Qt.AlignmentFlag.AlignCenter)
        self.final_view = view
        self.views.addWidget(view)

    def _close_button(self) -> QPushButton:
        button = QPushButton("Закрыть комнату")
        button.clicked.connect(self.close_room)
        return button

    # --- жизненный цикл экрана ---

    def entered(self, quiz_id: int | None = None, **_params) -> None:
        self._drop_connection()
        self._reset_game_state()
        if quiz_id is None:
            self._show_message("Сначала выберите викторину")
            return
        self.quiz_id = quiz_id
        self._create_room()

    def hideEvent(self, event) -> None:
        # Ведущий ушёл с экрана — комната закрывается для всех (host_left).
        if not event.spontaneous():
            self._drop_connection()
        super().hideEvent(event)

    def go_back(self) -> None:
        self.navigate(next(name for name in BACK_SCREENS if name in self.window_._screens))

    def _show_message(self, text: str, back: bool = True) -> None:
        self.m_text.setText(text)
        self.m_back.setVisible(back)
        self.views.setCurrentWidget(self.message_view)

    # --- комната ---

    def _live_api(self) -> ApiClient:
        """REST-клиент для /live/api. Через nginx это общий self.api; без nginx
        (QUIZ_LIVE_URL) — отдельный клиент к live с тем же токеном."""
        base = live_http_base(self.window_.settings.server_url)
        if base == self.api.base_url:
            return self.api
        client = ApiClient(base, self)
        client.token = self.api.token
        # 401 от live — тоже «сессия истекла»: пусть окно обработает как обычно.
        client.unauthorized.connect(self.api.unauthorized)
        return client

    def _create_room(self) -> None:
        self._show_message("Создаём комнату…", back=False)
        reply = self._live_api().post("/live/api/rooms", {"quiz_id": self.quiz_id}, auth=True)
        reply.succeeded.connect(self._on_room_created)
        reply.failed.connect(lambda error: self._show_message(f"Не удалось создать комнату: {error.message}"))

    def _on_room_created(self, data: dict) -> None:
        if not self.isVisible():
            return  # пока создавали, ведущий ушёл с экрана
        self.room_code = data["room_code"]
        self._show_message(f"Подключаемся к комнате {self.room_code}…", back=False)
        self.live = LiveClient(self.window_.settings.server_url, self)
        self.live.message.connect(self.on_message)
        self.live.failed.connect(self._on_failed)
        self.live.closed.connect(self._on_closed)
        self.live.open(self.room_code, token=self.api.token)

    def _on_failed(self, error) -> None:
        self._forget_live()
        if error.code == 401:
            self.api.unauthorized.emit()  # окно откроет экран входа
            return
        self._show_message(f"Не удалось подключиться к комнате: {error.message}")

    def start_game(self) -> None:
        self.start_button.setEnabled(False)  # второй клик не нужен
        self.live.send("start")

    def next_question(self) -> None:
        self.next_button.setEnabled(False)
        self.live.send("next")

    def close_room(self) -> None:
        if not self._game_over and self.live is not None:
            answer = QMessageBox.question(
                self, "Закрыть комнату", "Игра закончится для всех игроков. Закрыть комнату?"
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._drop_connection()
        self.go_back()

    # --- сообщения сервера ---

    def on_message(self, type_: str, data: dict) -> None:
        handler = {
            "joined": self._on_joined,
            "lobby_update": self._on_lobby_update,
            "question": self._on_question,
            "answer_progress": self._on_answer_progress,
            "question_result": self._on_question_result,
            "player_left": self._on_player_left,
            "game_over": self._on_game_over,
            "room_closed": self._on_room_closed,
            "error": lambda d: self._status(d.get("message", "")),
        }.get(type_)
        if handler:
            handler(data)

    def _on_joined(self, data: dict) -> None:
        self.question_count = data["question_count"]
        self.l_title.setText(f"«{data['quiz_title']}» — вопросов: {data['question_count']}")
        self.l_code.setText(data["room_code"])
        self._on_lobby_update(data)
        self.views.setCurrentWidget(self.lobby_view)

    def _on_lobby_update(self, data: dict) -> None:
        players = data["players"]
        self.player_count = len(players)
        self.l_players.clear()
        for p in players:
            self.l_players.addItem(p["nickname"])
        self.l_count.setText(f"Игроков: {len(players)} из 50")
        # Без игроков сервер ответит invalid_state — не даём нажать зря.
        self.start_button.setEnabled(bool(players))

    def _on_question(self, data: dict) -> None:
        self.question = data
        index = data["question_index"]
        self.q_header.setText(f"Вопрос {index + 1} из {data['question_count']}")
        self.q_text.setText(data["text"])
        self.options.set_options(data["options"])
        self.options.lock()  # ведущий не отвечает, варианты только для показа
        self.q_progress.setText(f"Ответили: 0 из {self.player_count}")
        self.countdown.start(data["time_limit_sec"])
        last = index + 1 == data["question_count"]
        self.next_button.setText("Показать итоги" if last else "Следующий вопрос")
        self.views.setCurrentWidget(self.question_view)

    def _on_answer_progress(self, data: dict) -> None:
        self.player_count = data["total"]
        self.q_progress.setText(f"Ответили: {data['answered']} из {data['total']}")

    def _on_question_result(self, data: dict) -> None:
        self.countdown.stop()
        q = self.question
        correct = next((o["text"] for o in q["options"] if o["option_id"] == data["correct_option_id"]), "?")
        self.r_header.setText(f"Вопрос {q['question_index'] + 1}: правильный ответ — {correct}")
        self.r_stats.show_counts(q["options"], data.get("option_counts", {}), data["correct_option_id"])
        self.r_board.show_entries(data["leaderboard"])
        self.next_button.setEnabled(True)
        self.views.setCurrentWidget(self.result_view)

    def _on_player_left(self, data: dict) -> None:
        self._status(f"{data['nickname']} выбыл из игры")

    def _on_game_over(self, data: dict) -> None:
        self._game_over = True
        self.countdown.stop()
        board = data["leaderboard"]
        self.f_title.setText("Игра окончена")
        self.f_subtitle.setText(f"Победитель: {board[0]['nickname']} — {board[0]['score']}" if board else "")
        self.f_board.show_entries(board)
        self.f_board.show()
        self.views.setCurrentWidget(self.final_view)

    def _on_room_closed(self, data: dict) -> None:
        self._room_closed = ROOM_CLOSED_REASONS.get(data.get("reason"), "Игра прервана")

    # --- закрытие соединения ---

    def _on_closed(self, error) -> None:
        self._forget_live()
        self.countdown.stop()
        if self._game_over:
            return  # после game_over сервер закрывает соединение сам
        self.f_title.setText("Игра прервана")
        self.f_subtitle.setText(self._room_closed or error.message)
        self.f_board.hide()
        self.views.setCurrentWidget(self.final_view)

    def _drop_connection(self) -> None:
        if self.live is None:
            return
        live = self.live
        self._forget_live()
        live.close()

    def _forget_live(self) -> None:
        if self.live is None:
            return
        live, self.live = self.live, None
        for signal in (live.message, live.failed, live.closed):
            signal.disconnect()
        live.deleteLater()

    def _status(self, text: str) -> None:
        if text:
            self.window_.statusBar().showMessage(text, 5000)
