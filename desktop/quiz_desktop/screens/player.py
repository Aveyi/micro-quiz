"""Экран игрока: вход по коду и нику → лобби → вопросы → итоги.

Это один экран приложения ("join") со своими видами внутри: соединение
с live живёт всю игру, и передавать его между экранами не нужно.
Протокол — docs/quiz-design.md, раздел 4.
"""

from PySide6.QtCore import QRegularExpression, Qt
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from quiz_desktop.live_client import LiveClient
from quiz_desktop.screens.base import Screen
from quiz_desktop.screens.game_common import ROOM_CLOSED_REASONS, Countdown, Leaderboard, OptionButtons, big_label

MAX_NICKNAME = 20  # раздел 2 дизайна; сервер проверяет то же самое


class PlayerScreen(Screen):
    def __init__(self, window):
        super().__init__(window)
        self.live: LiveClient | None = None
        self._reset_game_state()

        self.views = QStackedWidget()
        self._build_form()
        self._build_lobby()
        self._build_question()
        self._build_result()
        self._build_final()

        layout = QVBoxLayout(self)
        layout.addWidget(self.views)

    def _reset_game_state(self) -> None:
        self.room_code = ""
        self.player_id: int | None = None
        self.question: dict | None = None
        self.answered: int | None = None  # option_id выбранного варианта
        self._join_error = ""  # room_full / game_already_started до закрытия
        self._room_closed = ""  # причина из room_closed
        self._game_over = False

    # --- виды ---

    def _build_form(self) -> None:
        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("6 цифр")
        self.code_edit.setValidator(QRegularExpressionValidator(QRegularExpression(r"\d{0,6}")))
        self.nick_edit = QLineEdit()
        self.nick_edit.setPlaceholderText("как вас показывать в таблице")
        self.nick_edit.setMaxLength(MAX_NICKNAME)
        self.join_button = QPushButton("Войти")
        self.join_button.setMinimumHeight(40)
        self.form_error = QLabel()
        self.form_error.setStyleSheet("color: #c62828")
        self.form_error.setWordWrap(True)
        back = QPushButton("← Назад")

        for edit in (self.code_edit, self.nick_edit):
            edit.textChanged.connect(self._update_join_button)
            edit.returnPressed.connect(self.join)
        # Сменили код, пока висело соединение к старой комнате, — рвём его.
        self.code_edit.textChanged.connect(lambda _: self._drop_connection())
        self.join_button.clicked.connect(self.join)
        back.clicked.connect(lambda: self.navigate("start"))

        form = QFormLayout()
        form.addRow("Код комнаты:", self.code_edit)
        form.addRow("Ник:", self.nick_edit)

        view = QWidget()
        layout = QVBoxLayout(view)
        layout.addStretch()
        layout.addWidget(big_label("Вход в комнату", 24))
        layout.addSpacing(16)
        layout.addLayout(form)
        layout.addWidget(self.join_button)
        layout.addWidget(self.form_error)
        layout.addWidget(back, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        self.form_view = view
        self.views.addWidget(view)
        self._update_join_button()

    def _build_lobby(self) -> None:
        self.lobby_title = big_label(size=20)
        self.lobby_players = QListWidget()
        view = QWidget()
        layout = QVBoxLayout(view)
        layout.addWidget(self.lobby_title)
        layout.addWidget(big_label("Ждём, пока ведущий начнёт игру…", 14, bold=False))
        layout.addWidget(QLabel("В комнате:"))
        layout.addWidget(self.lobby_players)
        layout.addWidget(self._leave_button(), alignment=Qt.AlignmentFlag.AlignLeft)
        self.lobby_view = view
        self.views.addWidget(view)

    def _build_question(self) -> None:
        self.q_header = big_label(size=12, bold=False)
        self.q_text = big_label(size=22)
        self.countdown = Countdown()
        self.options = OptionButtons()
        self.q_status = big_label(size=14, bold=False)
        self.countdown.expired.connect(self._on_time_up)
        self.options.chosen.connect(self.answer)

        view = QWidget()
        layout = QVBoxLayout(view)
        layout.addWidget(self.q_header)
        layout.addWidget(self.q_text)
        layout.addWidget(self.countdown)
        layout.addWidget(self.options, stretch=1)
        layout.addWidget(self.q_status)
        layout.addWidget(self._leave_button(), alignment=Qt.AlignmentFlag.AlignLeft)
        self.question_view = view
        self.views.addWidget(view)

    def _build_result(self) -> None:
        self.r_verdict = big_label(size=26)
        self.r_points = big_label(size=16, bold=False)
        self.r_correct = big_label(size=14, bold=False)
        self.r_board = Leaderboard()
        view = QWidget()
        layout = QVBoxLayout(view)
        layout.addWidget(self.r_verdict)
        layout.addWidget(self.r_points)
        layout.addWidget(self.r_correct)
        layout.addWidget(QLabel("Таблица лидеров (первые 10):"))
        layout.addWidget(self.r_board)
        layout.addWidget(big_label("Ждём следующий вопрос от ведущего…", 12, bold=False))
        layout.addWidget(self._leave_button(), alignment=Qt.AlignmentFlag.AlignLeft)
        self.result_view = view
        self.views.addWidget(view)

    def _build_final(self) -> None:
        self.f_title = big_label(size=26)
        self.f_subtitle = big_label(size=16, bold=False)
        self.f_board = Leaderboard()
        home = QPushButton("На главную")
        home.clicked.connect(lambda: self.navigate("start"))
        view = QWidget()
        layout = QVBoxLayout(view)
        layout.addWidget(self.f_title)
        layout.addWidget(self.f_subtitle)
        layout.addWidget(self.f_board)
        layout.addWidget(home, alignment=Qt.AlignmentFlag.AlignCenter)
        self.final_view = view
        self.views.addWidget(view)

    def _leave_button(self) -> QPushButton:
        button = QPushButton("Выйти из игры")
        button.clicked.connect(self.leave)
        return button

    # --- жизненный цикл экрана ---

    def entered(self) -> None:
        self._drop_connection()
        self._reset_game_state()
        self.form_error.clear()
        self._set_form_busy(False)
        self.views.setCurrentWidget(self.form_view)

    def hideEvent(self, event) -> None:
        # Ушли с экрана (например, сменили сервер в настройках) — выходим из
        # комнаты. Сворачивание окна — «спонтанное» событие, его не трогаем.
        if not event.spontaneous():
            self._drop_connection()
        super().hideEvent(event)

    # --- вход ---

    def _update_join_button(self) -> None:
        ready = len(self.code_edit.text()) == 6 and bool(self.nick_edit.text().strip())
        self.join_button.setEnabled(ready)

    def _set_form_busy(self, busy: bool) -> None:
        for widget in (self.code_edit, self.nick_edit):
            widget.setEnabled(not busy)
        self.join_button.setText("Подключаемся…" if busy else "Войти")
        if busy:
            self.join_button.setEnabled(False)
        else:
            self._update_join_button()

    def join(self) -> None:
        if not self.join_button.isEnabled():
            return
        self.form_error.clear()
        self._set_form_busy(True)
        if self.live and self.live.is_open:
            # Соединение осталось после «ник занят» — просто пробуем другой ник.
            self._send_join()
            return
        self.room_code = self.code_edit.text()
        self.live = LiveClient(self.window_.settings.server_url, self)
        self.live.opened.connect(self._send_join)
        self.live.message.connect(self.on_message)
        self.live.failed.connect(self._on_failed)
        self.live.closed.connect(self._on_closed)
        self.live.open(self.room_code)  # игрок подключается без токена

    def _send_join(self) -> None:
        self.live.send("join", {"nickname": self.nick_edit.text().strip()})

    def _on_failed(self, error) -> None:
        self._forget_live()
        self._show_form_error(error.message)

    def _show_form_error(self, text: str) -> None:
        self.views.setCurrentWidget(self.form_view)
        self.form_error.setText(text)
        self._set_form_busy(False)

    # --- сообщения сервера ---

    def on_message(self, type_: str, data: dict) -> None:
        handler = {
            "joined": self._on_joined,
            "lobby_update": self._on_lobby_update,
            "question": self._on_question,
            "answer_accepted": self._on_answer_accepted,
            "question_result": self._on_question_result,
            "player_left": self._on_player_left,
            "game_over": self._on_game_over,
            "room_closed": self._on_room_closed,
            "error": self._on_error,
        }.get(type_)
        # Неизвестные type игнорируем (раздел 4.2): сервер новее клиента.
        if handler:
            handler(data)

    def _on_joined(self, data: dict) -> None:
        self.player_id = data["player_id"]
        self.lobby_title.setText(f"Комната {data['room_code']} — «{data['quiz_title']}»")
        self._on_lobby_update(data)
        self.views.setCurrentWidget(self.lobby_view)

    def _on_lobby_update(self, data: dict) -> None:
        self.lobby_players.clear()
        for p in data["players"]:
            mark = "  ← вы" if p["player_id"] == self.player_id else ""
            self.lobby_players.addItem(p["nickname"] + mark)

    def _on_error(self, data: dict) -> None:
        code, message = data.get("code"), data.get("message", "")
        if self.player_id is None:
            if code in ("room_full", "game_already_started"):
                # Сервер сейчас закроет соединение — покажем причину, а не «закрыто».
                self._join_error = message
            else:
                # nickname_taken, invalid_nickname, server_error: соединение
                # остаётся, можно исправить ник и войти снова.
                self._show_form_error(message)
                self.nick_edit.setFocus()
                self.nick_edit.selectAll()
            return
        self._status(message)

    def _on_question(self, data: dict) -> None:
        self.question = data
        self.answered = None
        self.q_header.setText(f"Вопрос {data['question_index'] + 1} из {data['question_count']}")
        self.q_text.setText(data["text"])
        self.options.set_options(data["options"])
        self.q_status.setText("Выберите ответ")
        self.countdown.start(data["time_limit_sec"])
        self.views.setCurrentWidget(self.question_view)

    def answer(self, option_id: int) -> None:
        if self.answered is not None or self.question is None:
            return  # отвечать можно один раз
        self.answered = option_id
        self.options.lock(chosen=option_id)
        self.q_status.setText("Отправляем ответ…")
        self.live.send("answer", {"question_index": self.question["question_index"], "option_id": option_id})

    def _on_answer_accepted(self, data: dict) -> None:
        self.q_status.setText("Ответ принят! Ждём остальных…")

    def _on_time_up(self) -> None:
        if self.answered is None:
            self.options.lock()
            self.q_status.setText("Время вышло")

    def _on_question_result(self, data: dict) -> None:
        self.countdown.stop()
        you = data["you"]
        if you["correct"]:
            self.r_verdict.setText("Верно!")
            self.r_verdict.setStyleSheet("color: #2e7d32")
            self.r_points.setText(f"+{you['points']} очков")
        else:
            self.r_verdict.setText("Неверно" if self.answered is not None else "Нет ответа")
            self.r_verdict.setStyleSheet("color: #c62828")
            self.r_points.setText("0 очков")
        self.r_points.setText(self.r_points.text() + f"  ·  счёт {you['score']}  ·  место {you['rank']}")
        correct = next((o["text"] for o in self.question["options"] if o["option_id"] == data["correct_option_id"]), "?")
        self.r_correct.setText(f"Правильный ответ: {correct}")
        self.r_board.show_entries(data["leaderboard"], me=self.player_id)
        self.views.setCurrentWidget(self.result_view)

    def _on_player_left(self, data: dict) -> None:
        self._status(f"{data['nickname']} выбыл из игры")

    def _on_game_over(self, data: dict) -> None:
        self._game_over = True
        self.countdown.stop()
        you = data["you"]
        self.f_title.setText("Игра окончена")
        self.f_subtitle.setText(f"Ваше место: {you['rank']}  ·  счёт {you['score']}")
        self.f_board.show_entries(data["leaderboard"], me=self.player_id)
        self.f_board.show()
        self.views.setCurrentWidget(self.final_view)

    def _on_room_closed(self, data: dict) -> None:
        self._room_closed = ROOM_CLOSED_REASONS.get(data.get("reason"), "Игра прервана")

    # --- закрытие соединения ---

    def _on_closed(self, error) -> None:
        self._forget_live()
        self.countdown.stop()
        if self._game_over:
            return  # после game_over сервер закрывает соединение сам (код 1000)
        if self.player_id is None:
            # Не успели войти: room_full, game_already_started, таймаут join…
            self._show_form_error(self._join_error or error.message)
            return
        self.f_title.setText("Игра прервана")
        self.f_subtitle.setText(self._room_closed or error.message)
        self.f_board.hide()
        self.views.setCurrentWidget(self.final_view)

    def leave(self) -> None:
        self._drop_connection()
        self.navigate("start")

    def _drop_connection(self) -> None:
        """Закрыть соединение самим, не реагируя на его закрытие."""
        if self.live is None:
            return
        live = self.live
        self._forget_live()
        live.close()

    def _forget_live(self) -> None:
        if self.live is None:
            return
        live, self.live = self.live, None
        # Отключаем обработчики: события старого соединения экрану уже не нужны.
        for signal in (live.opened, live.message, live.failed, live.closed):
            signal.disconnect()
        live.deleteLater()  # не delete: мы можем быть внутри его сигнала

    def _status(self, text: str) -> None:
        self.window_.statusBar().showMessage(text, 5000)
