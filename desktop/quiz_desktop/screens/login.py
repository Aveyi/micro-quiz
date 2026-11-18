"""Вход и регистрация ведущего: POST /api/auth/login и /api/auth/register."""

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from quiz_desktop.api import ApiError
from quiz_desktop.screens.base import Screen
from quiz_desktop.theme import set_role, set_variant
from quiz_desktop.ui import LogoMark, card

# Те же правила, что проверяет content (docs/quiz-design.md, раздел 5.1).
# Проверяем и здесь, чтобы показать ошибку сразу, не дожидаясь сервера;
# окончательно всё равно решает сервер.
USERNAME_RE = re.compile(r"^[\w.-]{3,32}$")
MIN_PASSWORD = 8
MAX_PASSWORD_BYTES = 72


def validate(username: str, password: str, confirm: str | None) -> str | None:
    """Текст ошибки или None. confirm — повтор пароля, только при регистрации."""
    if not USERNAME_RE.match(username):
        return "Имя пользователя: 3–32 символа, буквы, цифры, _ . -"
    if len(password) < MIN_PASSWORD:
        return f"Пароль должен быть не короче {MIN_PASSWORD} символов"
    if len(password.encode()) > MAX_PASSWORD_BYTES:
        return "Пароль слишком длинный"
    if confirm is not None and password != confirm:
        return "Пароли не совпадают"
    return None


class LoginScreen(Screen):
    def __init__(self, window):
        super().__init__(window)
        self._register_mode = False

        self.title = set_role(QLabel(), "h1")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = set_role(QLabel("Викторины, игры и результаты — в одном месте"), "muted")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)

        self.username = QLineEdit()
        self.username.setPlaceholderText("Например, teacher")
        self.password = QLineEdit()
        self.password.setPlaceholderText("Не короче 8 символов")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm = QLineEdit()
        self.confirm.setPlaceholderText("Ещё раз тот же пароль")
        self.confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_label = set_role(QLabel("Повторите пароль"), "muted")
        # Enter в любом поле — то же, что нажать кнопку.
        for edit in (self.username, self.password, self.confirm):
            edit.returnPressed.connect(self.submit)

        self.error = set_role(QLabel(), "error")
        self.error.setWordWrap(True)

        self.submit_button = set_variant(QPushButton(), "primary")
        self.submit_button.setMinimumHeight(44)
        self.submit_button.setDefault(True)
        self.submit_button.clicked.connect(self.submit)
        # Кнопка-ссылка: «Нет аккаунта? Зарегистрироваться».
        self.switch_button = set_variant(QPushButton(), "link")
        self.switch_button.clicked.connect(lambda: self.set_register_mode(not self._register_mode))
        back = set_variant(QPushButton("← Назад"), "ghost")
        back.clicked.connect(lambda: self.navigate("start"))

        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)  # подпись над полем
        form.setVerticalSpacing(6)
        form.addRow(set_role(QLabel("Имя пользователя"), "muted"), self.username)
        form.addRow(set_role(QLabel("Пароль"), "muted"), self.password)
        form.addRow(self.confirm_label, self.confirm)

        # Карточка фиксированной ширины по центру окна.
        box = card()
        box.setFixedWidth(440)
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(36, 32, 36, 24)
        box_layout.setSpacing(10)
        box_layout.addWidget(LogoMark(44), alignment=Qt.AlignmentFlag.AlignCenter)
        box_layout.addWidget(self.title)
        box_layout.addWidget(subtitle)
        box_layout.addSpacing(8)
        box_layout.addLayout(form)
        box_layout.addWidget(self.error)
        box_layout.addWidget(self.submit_button)
        box_layout.addWidget(self.switch_button, alignment=Qt.AlignmentFlag.AlignCenter)
        box_layout.addWidget(back, alignment=Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self.page)
        layout.addStretch()
        layout.addWidget(box, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()

        self.set_register_mode(False)

    def entered(self, **params) -> None:
        # Пароль на экране не оставляем: экран мог открыться после выхода из аккаунта.
        self.password.clear()
        self.confirm.clear()
        self.error.clear()
        self._set_busy(False)
        if not self.username.text():
            self.username.setText(self.window_.settings.last_username)
        (self.password if self.username.text() else self.username).setFocus()

    def set_register_mode(self, on: bool) -> None:
        self._register_mode = on
        self.title.setText("Регистрация ведущего" if on else "Вход ведущего")
        self.submit_button.setText("Зарегистрироваться" if on else "Войти")
        self.switch_button.setText("Уже есть аккаунт? Войти" if on else "Нет аккаунта? Зарегистрироваться")
        self.confirm.setVisible(on)
        self.confirm_label.setVisible(on)
        self.confirm.clear()
        self.error.clear()

    def submit(self) -> None:
        if not self.submit_button.isEnabled():
            return  # запрос уже идёт: Enter, нажатый дважды, не шлёт второй
        username = self.username.text().strip()
        password = self.password.text()
        problem = validate(username, password, self.confirm.text() if self._register_mode else None)
        if problem:
            self.error.setText(problem)
            return

        self.error.clear()
        self._set_busy(True)
        body = {"username": username, "password": password}
        if self._register_mode:
            reply = self.api.post("/api/auth/register", body)
            # После регистрации сразу входим, чтобы не вводить данные второй раз.
            reply.succeeded.connect(lambda _: self._login(body))
        else:
            reply = self._login_reply(body)
        reply.failed.connect(self._on_failed)

    def _login(self, body: dict) -> None:
        self._login_reply(body).failed.connect(self._on_failed)

    def _login_reply(self, body: dict):
        reply = self.api.post("/api/auth/login", body)
        reply.succeeded.connect(lambda data: self._on_logged_in(body["username"], data))
        return reply

    def _on_logged_in(self, username: str, data: dict) -> None:
        self._set_busy(False)
        self.window_.login(data["access_token"], username)

    def _on_failed(self, error: ApiError) -> None:
        self._set_busy(False)
        self.error.setText(str(error))

    def _set_busy(self, busy: bool) -> None:
        self.submit_button.setEnabled(not busy)
        self.switch_button.setEnabled(not busy)
        if busy:
            self.submit_button.setText("Подождите…")
        else:
            self.submit_button.setText("Зарегистрироваться" if self._register_mode else "Войти")
