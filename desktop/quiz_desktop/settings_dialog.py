"""Диалог «Настройки сервера»: адрес и проверка соединения."""

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from quiz_desktop.api import ApiClient, ApiError
from quiz_desktop.settings import DEFAULT_SERVER_URL, normalize_server_url

# Через nginx наружу открыты только /api/, /live/api/ и /live/ws, а /health
# сервисов — нет (docs/quiz-design.md, раздел 8.2). Поэтому проверяем ручку
# content, которой нужен токен: ответ 401 в нашем формате {"error": ...}
# означает, что отвечают и nginx, и content.
CHECK_PATH = "/api/quizzes"


class SettingsDialog(QDialog):
    def __init__(self, server_url: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки сервера")
        self.setMinimumWidth(460)
        self.server_url = server_url

        self.url_edit = QLineEdit(server_url)
        self.url_edit.setPlaceholderText(DEFAULT_SERVER_URL)
        self.check_button = QPushButton("Проверить соединение")
        self.check_button.clicked.connect(self.check_connection)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)

        row = QHBoxLayout()
        row.addWidget(self.url_edit)
        row.addWidget(self.check_button)
        form = QFormLayout()
        form.addRow("Адрес сервера:", row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.status_label)
        layout.addWidget(buttons)

        # Отдельный клиент: проверяем введённый адрес, не трогая основной.
        self._api = ApiClient(server_url, self)

    def _read_url(self) -> str | None:
        try:
            return normalize_server_url(self.url_edit.text())
        except ValueError as e:
            self._show_status(f"Неверный адрес: {e}", ok=False)
            return None

    def check_connection(self) -> None:
        url = self._read_url()
        if url is None:
            return
        self._api.base_url = url
        self.check_button.setEnabled(False)
        self._show_status("Проверяю…", ok=None)

        reply = self._api.get(CHECK_PATH)
        reply.succeeded.connect(lambda _: self._on_checked(ApiError(200, "")))
        reply.failed.connect(self._on_checked)

    def _on_checked(self, error: ApiError) -> None:
        self.check_button.setEnabled(True)
        if error.status == 401:
            self._show_status("Соединение есть, сервер отвечает", ok=True)
        elif error.status == 0:
            self._show_status(str(error), ok=False)
        else:
            self._show_status(f"По этому адресу отвечает не сервер викторины (код {error.status})", ok=False)

    def _show_status(self, text: str, ok: bool | None) -> None:
        color = {True: "green", False: "#c00", None: "gray"}[ok]
        self.status_label.setStyleSheet(f"color: {color}")
        self.status_label.setText(text)

    def accept(self) -> None:
        url = self._read_url()
        if url is None:
            return  # окно остаётся открытым, ошибка уже показана
        self.server_url = url
        super().accept()
