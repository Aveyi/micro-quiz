"""Общие фикстуры тестов десктопа."""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Окна рисуются в памяти, а не на экране: тесты не мигают окнами
# и работают там, где экрана нет (например, в CI).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QSettings  # noqa: E402

from quiz_desktop.settings import AppSettings  # noqa: E402


@pytest.fixture
def settings(tmp_path):
    """Настройки во временном файле, а не в реестре настоящего приложения."""
    return AppSettings(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))


class _Handler(BaseHTTPRequestHandler):
    # Ответы по пути запроса: (код, тело). Тело-словарь отдаётся как JSON.
    routes = {
        "/ok": (200, {"value": 1, "text": "привет"}),
        "/empty": (204, None),
        "/conflict": (409, {"error": "имя пользователя уже занято"}),
        "/html": (500, "<h1>Internal Server Error</h1>"),
        "/api/quizzes": (401, {"error": "нужна авторизация"}),
    }

    def _respond(self):
        length = int(self.headers.get("Content-Length") or 0)
        self.server.requests.append(
            {
                "method": self.command,
                "path": self.path,
                "headers": dict(self.headers),
                "body": self.rfile.read(length).decode() if length else None,
            }
        )
        status, body = self.routes.get(self.path, (404, {"error": "не найдено"}))
        raw = b"" if body is None else (json.dumps(body) if isinstance(body, dict) else body).encode()
        self.send_response(status)
        if raw:
            self.send_header("Content-Type", "application/json" if isinstance(body, dict) else "text/html")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    do_GET = do_POST = do_PUT = do_DELETE = _respond

    def log_message(self, *args):
        pass  # не засоряем вывод pytest


@pytest.fixture
def server():
    """Локальный HTTP-сервер с заготовленными ответами; адрес — server.url."""
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)  # порт 0 — любой свободный
    srv.requests = []
    srv.url = f"http://127.0.0.1:{srv.server_address[1]}"
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()


@pytest.fixture
def free_url():
    """Адрес, на котором точно никто не слушает."""
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = srv.server_address[1]
    srv.server_close()
    return f"http://127.0.0.1:{port}"
