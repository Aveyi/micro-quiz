"""Подключение к PostgreSQL.

Сервис работает только со схемой content (docs/quiz-design.md, раздел 7.1).
Таблицы создаёт не сервис, а миграции в deploy/migrations/.
"""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def make_engine(database_url: str) -> Engine:
    # create_engine ещё не подключается к БД: соединения открываются
    # при первом запросе и дальше переиспользуются из пула.
    return create_engine(
        database_url,
        # Перед выдачей соединения из пула проверяем, что оно живо:
        # иначе после перезапуска PostgreSQL первый запрос упадёт.
        pool_pre_ping=True,
    )


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def get_session(request: Request) -> Iterator[Session]:
    """Зависимость FastAPI: одна сессия на запрос, закрывается после ответа."""
    with request.app.state.session_factory() as session:
        yield session
