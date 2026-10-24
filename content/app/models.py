"""Таблицы схемы content для SQLAlchemy.

Описания должны совпадать с deploy/migrations/: таблицы создают миграции,
а здесь только объясняем ORM, как они устроены.
"""

from datetime import datetime

from sqlalchemy import MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    # Все таблицы сервиса лежат в схеме content, а не в public.
    metadata = MetaData(schema="content")


class User(Base):
    __tablename__ = "users"

    # id выдаёт PostgreSQL (GENERATED ALWAYS AS IDENTITY), поэтому
    # при вставке ORM его не передаёт, а забирает из RETURNING.
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str]
    password_hash: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
