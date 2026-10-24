"""Настройки сервиса из переменных окружения.

Список переменных — docs/quiz-design.md, раздел 8.3.
"""

import os
from dataclasses import dataclass


class ConfigError(Exception):
    """Неверные или отсутствующие настройки."""


@dataclass(frozen=True)
class Config:
    port: int
    database_url: str


def load() -> Config:
    """Собирает конфиг и сразу проверяет его: лучше упасть при старте
    с понятной ошибкой, чем работать с неверными настройками."""
    port = _int_env("PORT", 8000)
    if not 1 <= port <= 65535:
        raise ConfigError(f"PORT: {port} вне диапазона 1–65535")

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise ConfigError("DATABASE_URL не задан")

    return Config(port=port, database_url=_sqlalchemy_url(database_url))


def _int_env(name: str, default: int) -> int:
    """Число из переменной name или default, если переменная не задана."""
    value = os.environ.get(name, "")
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        raise ConfigError(f"{name}: {value!r} не число") from None


def _sqlalchemy_url(url: str) -> str:
    """В .env адрес общий для обоих сервисов: postgres://...
    SQLAlchemy же по схеме адреса выбирает драйвер, поэтому указываем psycopg явно."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url
