"""WebSocket-клиент к сервису live: комната, игра, таблица лидеров.

Протокол — docs/quiz-design.md, раздел 4. Все сообщения в обе стороны —
JSON-конверт {"type": ..., "data": {...}}. Клиент разбирает конверт и
отдаёт экранам сигнал message(type, data); что делать с сообщением,
решает экран.

    live = LiveClient(settings.server_url, parent=self)
    live.opened.connect(...)            # соединение установлено
    live.message.connect(self.on_message)  # (type: str, data: dict)
    live.failed.connect(...)            # не подключились: LiveError
    live.closed.connect(...)            # соединение закрылось: LiveError
    live.open("482913", token=api.token)  # токен только у ведущего

Удалять клиент прямо в обработчике его сигнала нельзя (объект Qt посреди
своего сигнала) — используйте deleteLater().
"""

import json
import os
import re
from dataclasses import dataclass
from urllib.parse import urlencode, urlsplit, urlunsplit

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QAbstractSocket, QNetworkRequest
from PySide6.QtWebSockets import QWebSocket, QWebSocketProtocol

from quiz_desktop.settings import normalize_server_url

# Для разработки без nginx: live запущен отдельно (обычно на :8080), а
# server_url указывает на content. Через nginx переменная не нужна.
LIVE_URL_ENV = "QUIZ_LIVE_URL"

# Сколько ждём рукопожатия. Без таймаута при «повисшем» сервере экран
# навсегда остался бы в состоянии «подключаемся…».
CONNECT_TIMEOUT_MS = 10_000


def live_http_base(server_url: str) -> str:
    """Адрес для REST-ручек live (/live/api/...): через nginx — тот же сервер,
    без nginx — QUIZ_LIVE_URL."""
    return normalize_server_url(os.environ.get(LIVE_URL_ENV) or server_url)


def live_ws_url(server_url: str, room_code: str) -> str:
    """Адрес WebSocket комнаты: http://хост → ws://хост/live/ws?room=код."""
    parts = urlsplit(live_http_base(server_url))
    scheme = "wss" if parts.scheme == "https" else "ws"
    # urlencode сам экранирует значение: «код» с пробелом или & не сломает адрес.
    return urlunsplit((scheme, parts.netloc, "/live/ws", urlencode({"room": room_code}), ""))


@dataclass
class LiveError:
    # Для failed — HTTP-код отказа (0 — сервер недоступен или код неизвестен).
    # Для closed — код закрытия WebSocket (1000, 1001, 1008…), раздел 4.6.
    code: int
    message: str

    def __str__(self) -> str:
        return self.message


# Отказы до переключения протокола (раздел 4.1). Тело ответа {"error": ...}
# QWebSocket не отдаёт, поэтому текст берём по коду.
HANDSHAKE_ERRORS = {
    400: "Не указан код комнаты",
    401: "Сессия ведущего истекла, войдите снова",
    403: "Эта комната создана другим ведущим",
    404: "Комнаты с таким кодом нет: она завершена или ведущий ещё не открыл её",
    409: "Ведущий уже подключён к этой комнате (возможно, в другом окне)",
    502: "Сервер не смог загрузить викторину, попробуйте позже",
    503: "Сервер перезапускается, попробуйте ещё раз через несколько секунд",
}

# Коды закрытия (раздел 4.6). 1000 — обычное завершение: что случилось,
# экран узнаёт из сообщения перед закрытием (game_over, room_closed, error).
CLOSE_MESSAGES = {
    1000: "Соединение закрыто",
    1001: "Сервер перезапускается",
    1006: "Связь с сервером потеряна",
    1009: "Сообщение слишком большое",
}
CLOSE_POLICY_REASONS = {
    "join timeout": "Вы слишком долго не входили в комнату",
    "too slow": "Соединение слишком медленное, сервер отключил вас",
}

_STATUS_RE = re.compile(r"status code: (\d{3})")


def handshake_error(error_string: str) -> LiveError:
    """Превращает ошибку QWebSocket при подключении в понятное сообщение.

    QWebSocket сообщает HTTP-код отказа только внутри текста ошибки:
    «…Unhandled http status code: 404 (Not Found).». На 400 кода нет вовсе,
    а на 401 Qt пытается найти способ авторизации и пишет про WWW-Authenticate.
    """
    if "WWW-Authenticate" in error_string:
        return LiveError(401, HANDSHAKE_ERRORS[401])
    match = _STATUS_RE.search(error_string)
    if match:
        status = int(match.group(1))
        return LiveError(status, HANDSHAKE_ERRORS.get(status, f"Сервер отказал в подключении (код {status})"))
    return LiveError(0, f"Сервер недоступен: {error_string}")


def close_error(code: int, reason: str) -> LiveError:
    if code == 1008:
        return LiveError(code, CLOSE_POLICY_REASONS.get(reason, "Сервер отключил вас за нарушение правил"))
    return LiveError(code, CLOSE_MESSAGES.get(code, f"Соединение закрыто (код {code})"))


class LiveClient(QObject):
    opened = Signal()
    message = Signal(str, object)  # type, data (dict)
    failed = Signal(object)  # LiveError: подключиться не удалось
    closed = Signal(object)  # LiveError: соединение было и закрылось

    def __init__(self, server_url: str, parent: QObject | None = None):
        super().__init__(parent)
        self.server_url = server_url
        self._ws = QWebSocket()
        self._ws.setParent(self)
        self._ws.connected.connect(self._on_connected)
        self._ws.disconnected.connect(self._on_disconnected)
        self._ws.textMessageReceived.connect(self._on_text)
        self._is_open = False
        self._finished = False  # failed или closed уже отправлен
        self._closing = False  # закрываем сами, вызовом close()

        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._on_timeout)

    @property
    def is_open(self) -> bool:
        return self._is_open

    def open(self, room_code: str, token: str | None = None) -> None:
        request = QNetworkRequest(QUrl(live_ws_url(self.server_url, room_code)))
        # Токен — в заголовке, не в адресе: адреса попадают в логи (раздел 4.1).
        if token:
            request.setRawHeader(b"Authorization", f"Bearer {token}".encode())
        self._is_open = False
        self._finished = False
        self._closing = False
        self._timeout.start(CONNECT_TIMEOUT_MS)
        self._ws.open(request)

    def send(self, type_: str, data: dict | None = None) -> None:
        # data есть всегда, хотя бы {} (раздел 4.2).
        text = json.dumps({"type": type_, "data": data or {}}, ensure_ascii=False)
        self._ws.sendTextMessage(text)

    def close(self) -> None:
        """Закрыть соединение самим (игрок вышел, ведущий закрыл комнату)."""
        self._timeout.stop()
        self._closing = True
        self._ws.close(QWebSocketProtocol.CloseCode.CloseCodeNormal)

    def _on_connected(self) -> None:
        self._timeout.stop()
        self._is_open = True
        self.opened.emit()

    def _on_text(self, text: str) -> None:
        try:
            envelope = json.loads(text)
        except ValueError:
            return
        if not isinstance(envelope, dict) or not isinstance(envelope.get("type"), str):
            return
        data = envelope.get("data")
        self.message.emit(envelope["type"], data if isinstance(data, dict) else {})

    def _on_disconnected(self) -> None:
        self._timeout.stop()
        if self._is_open:
            self._is_open = False
            code, reason = self._ws.closeCode().value, self._ws.closeReason()
            # Обрыв без close-фрейма QWebSocket тоже показывает как 1000.
            # live же, закрывая соединение кодом 1000 сам, всегда пишет
            # причину (game over, host_left, room_full…). Пустая причина без
            # нашего close() — значит, связь просто пропала.
            if code == 1000 and not reason and not self._closing:
                code = 1006
            self._finish(self.closed, close_error(code, reason))
            return
        # Подключиться не удалось. QWebSocket иногда шлёт disconnected раньше,
        # чем errorOccurred, а closeCode тут бессмыслен (всегда 1000). Поэтому
        # читаем ошибку на следующем шаге цикла событий, когда она уже есть.
        QTimer.singleShot(0, self, lambda: self._finish(self.failed, handshake_error(self._ws.errorString())))

    def _on_timeout(self) -> None:
        if self._ws.state() != QAbstractSocket.SocketState.ConnectedState:
            self._ws.abort()
            self._finish(self.failed, LiveError(0, "Сервер не ответил вовремя"))

    def _finish(self, signal, error: LiveError) -> None:
        # Ровно одно итоговое событие на одно open(): abort после таймаута
        # вызовет ещё и disconnected, второй раз сообщать не нужно.
        if self._finished:
            return
        self._finished = True
        signal.emit(error)
