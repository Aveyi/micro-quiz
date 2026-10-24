"""Таблицы схемы content для SQLAlchemy.

Описания должны совпадать с deploy/migrations/: таблицы создают миграции,
а здесь только объясняем ORM, как они устроены.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


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


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str]
    description: Mapped[str] = mapped_column(server_default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # cascade="all, delete-orphan": вопрос, убранный из списка, удаляется из БД.
    # Так PUT заменяет вопросы, просто подставляя новый список.
    questions: Mapped[list["Question"]] = relationship(
        order_by="Question.position", cascade="all, delete-orphan"
    )


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"))
    position: Mapped[int]
    text: Mapped[str]
    time_limit_sec: Mapped[int]

    options: Mapped[list["AnswerOption"]] = relationship(
        order_by="AnswerOption.position", cascade="all, delete-orphan"
    )


class AnswerOption(Base):
    __tablename__ = "answer_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"))
    position: Mapped[int]
    text: Mapped[str]
    is_correct: Mapped[bool]
