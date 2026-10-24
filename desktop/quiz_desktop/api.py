"""REST-клиент к серверу (через nginx: /api/... и /live/api/...).

Запросы асинхронные, через QNetworkAccessManager: интерфейс не зависает,
пока ждём сервер. Вместо результата метод сразу возвращает ApiReply,
а ответ приходит позже сигналом:

    reply = api.get("/api/quizzes", auth=True)
    reply.succeeded.connect(self.show_quizzes)   # data — разобранный JSON
    reply.failed.connect(self.show_error)        # ApiError
"""

import json
from dataclasses import dataclass
from typing import Any

import shiboken6
from PySide6.QtCore import QByteArray, QCoreApplication, QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

# Сколько ждём ответа. Без таймаута при «повисшем» сервере
# кнопка навсегда осталась бы в состоянии «загрузка».
TIMEOUT_MS = 10_000

_manager: QNetworkAccessManager | None = None


def _shared_manager() -> QNetworkAccessManager:
    """Один QNetworkAccessManager на всё приложение, как советует документация Qt.

    Свой менеджер у каждого клиента опасен: если удалить менеджер сразу после
    ответа «соединение отклонено» (например, закрыть диалог настроек, когда
    сервер выключен), сетевой поток Qt ещё доделывает работу, и процесс падает.
    Родитель — само приложение, поэтому менеджер живёт до выхода.
    """
    global _manager
    if _manager is None:
        _manager = QNetworkAccessManager(QCoreApplication.instance())
    return _manager


@dataclass
class ApiError:
    # HTTP-код ответа; 0 — до сервера не достучались (нет сети, таймаут).
    status: int
    message: str

    def __str__(self) -> str:
        return self.message


class ApiReply(QObject):
    """Один запрос. Ровно один из сигналов придёт ровно один раз."""

    succeeded = Signal(object)  # разобранный JSON или None (ответ 204)
    failed = Signal(object)  # ApiError


class ApiClient(QObject):
    # Сервер ответил 401 на запрос с токеном: токен просрочен (живёт 12 ч)
    # или недействителен. Главное окно по этому сигналу возвращает на вход.
    unauthorized = Signal()

    def __init__(self, base_url: str, parent: QObject | None = None):
        super().__init__(parent)
        self.base_url = base_url
        self.token: str | None = None

    def get(self, path: str, *, auth: bool = False) -> ApiReply:
        return self.request("GET", path, auth=auth)

    def post(self, path: str, body: Any = None, *, auth: bool = False) -> ApiReply:
        return self.request("POST", path, body, auth=auth)

    def put(self, path: str, body: Any = None, *, auth: bool = False) -> ApiReply:
        return self.request("PUT", path, body, auth=auth)

    def delete(self, path: str, *, auth: bool = False) -> ApiReply:
        return self.request("DELETE", path, auth=auth)

    def request(self, method: str, path: str, body: Any = None, *, auth: bool = False) -> ApiReply:
        request = QNetworkRequest(QUrl(self.base_url + path))
        request.setTransferTimeout(TIMEOUT_MS)
        request.setRawHeader(b"Accept", b"application/json")
        if auth and self.token:
            request.setRawHeader(b"Authorization", f"Bearer {self.token}".encode())

        data = QByteArray()
        if body is not None:
            request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
            # ensure_ascii=False + UTF-8: кириллица уходит как есть, сервер ждёт UTF-8.
            data = QByteArray(json.dumps(body, ensure_ascii=False).encode())

        # У ApiReply нет родителя: его держит лямбда ниже, пока запрос не завершится.
        result = ApiReply()
        reply = _shared_manager().sendCustomRequest(request, method.encode(), data)
        reply.finished.connect(lambda: self._finish(reply, result, auth))
        return result

    def _finish(self, reply: QNetworkReply, result: ApiReply, auth: bool) -> None:
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) or 0
        raw = bytes(reply.readAll().data())
        timed_out = reply.error() == QNetworkReply.NetworkError.OperationCanceledError
        error_text = reply.errorString()
        # Сам reply удаляем через deleteLater: прямо сейчас идёт его сигнал finished.
        reply.deleteLater()

        # Обработчики вызываем на следующем шаге цикла событий, а не прямо здесь.
        # Обработчик может закрыть окно и вместе с ним удалить этот клиент,
        # а удалять объекты Qt посреди сигнала запроса нельзя: процесс падает.
        QTimer.singleShot(0, lambda: self._deliver(result, status, raw, timed_out, error_text, auth))

    def _deliver(self, result: ApiReply, status: int, raw: bytes, timed_out: bool, error_text: str, auth: bool) -> None:
        # Клиент удалён вместе со своим окном, пока шёл запрос. Ответ отбрасываем:
        # обработчики (часто лямбды) обратились бы к уже удалённым виджетам окна,
        # а лямбды, в отличие от методов виджетов, Qt сам не отключает.
        if not shiboken6.isValid(self):
            return
        if status == 0:
            # Ответа нет вовсе: сервер выключен, неверный адрес или таймаут.
            if timed_out:
                error_text = "сервер не ответил вовремя"
            result.failed.emit(ApiError(0, f"Сервер недоступен: {error_text}"))
            return

        try:
            data = json.loads(raw) if raw else None
        except ValueError:
            data = None

        if 200 <= status < 300:
            result.succeeded.emit(data)
            return

        # Все сервисы отвечают ошибкой в виде {"error": "текст"} (раздел 9 дизайна).
        if isinstance(data, dict) and isinstance(data.get("error"), str):
            message = data["error"]
        else:
            message = f"ошибка сервера (код {status})"
        if status == 401 and auth:
            self.unauthorized.emit()
        result.failed.emit(ApiError(status, message))
