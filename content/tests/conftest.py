"""Общие фикстуры тестов.

Тестам с БД нужен PostgreSQL: адрес берётся из TEST_DATABASE_URL
(как его поднять — content/README.md). Без переменной такие тесты
пропускаются. Схема content в тестовой БД пересоздаётся из файла
миграции, поэтому заодно проверяется и сама миграция.
"""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import Config, _sqlalchemy_url
from app.db import make_engine
from app.main import create_app

SECRET = "test-secret-test-secret-test-sec"  # 32 байта
MIGRATION = Path(__file__).parents[2] / "deploy" / "migrations" / "0001_content_init.up.sql"
# Порт 1 никто не слушает: для тестов без БД подключения быть не должно.
NO_DB_URL = "postgresql+psycopg://u:p@localhost:1/db"


def make_config(database_url: str = NO_DB_URL) -> Config:
    return Config(port=8000, database_url=database_url, jwt_secret=SECRET)


@pytest.fixture(scope="session")
def database_url():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL не задан")
    url = _sqlalchemy_url(url)

    engine = make_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS content CASCADE"))
        conn.execute(text("CREATE SCHEMA content"))
        # exec_driver_sql отправляет файл как есть, несколькими командами сразу.
        conn.exec_driver_sql(MIGRATION.read_text(encoding="utf-8"))
    engine.dispose()
    return url


@pytest.fixture
def db_client(database_url):
    """Клиент к приложению с чистой БД."""
    app = create_app(make_config(database_url))
    with app.state.engine.begin() as conn:
        # CASCADE очищает и таблицы, которые ссылаются на users.
        conn.execute(text("TRUNCATE content.users RESTART IDENTITY CASCADE"))
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
