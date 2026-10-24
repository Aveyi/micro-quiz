"""Настройки приложения, которые сохраняются между запусками.

QSettings сам выбирает место хранения: на Windows это реестр
(HKEY_CURRENT_USER\\Software\\micro-quiz\\desktop), на macOS — plist-файл.
"""

from urllib.parse import urlsplit

from PySide6.QtCore import QSettings

# Наружу открыт только nginx (docs/quiz-design.md, раздел 8.4).
DEFAULT_SERVER_URL = "http://localhost:8000"


def normalize_server_url(text: str) -> str:
    """Проверяет адрес сервера и приводит его к виду http(s)://хост[:порт].

    Завершающий «/» убирается, чтобы пути можно было просто дописывать:
    base + "/api/quizzes".
    """
    url = text.strip().rstrip("/")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("адрес должен быть вида http://хост:порт")
    if parts.path or parts.query or parts.fragment:
        raise ValueError("в адресе не должно быть пути, только http://хост:порт")
    try:
        parts.port  # бросает ValueError, если порт не число или вне 0–65535
    except ValueError:
        raise ValueError("неверный порт") from None
    return url


class AppSettings:
    def __init__(self, qsettings: QSettings | None = None):
        # В тестах подставляется QSettings с временным файлом,
        # чтобы не трогать настройки настоящего приложения.
        self._s = qsettings or QSettings("micro-quiz", "desktop")

    @property
    def server_url(self) -> str:
        value = self._s.value("server_url", DEFAULT_SERVER_URL, type=str)
        try:
            return normalize_server_url(value)
        except ValueError:
            # Испорченное значение (например, правили реестр вручную) — не падаем.
            return DEFAULT_SERVER_URL

    @server_url.setter
    def server_url(self, value: str) -> None:
        self._s.setValue("server_url", normalize_server_url(value))
        self._s.sync()
