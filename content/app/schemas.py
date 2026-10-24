"""JSON викторин: что приходит в запросах и что уходит в ответах.

Правила проверки — docs/quiz-design.md, раздел 5.1. Они дублируют
ограничения таблиц в БД: так клиент получает понятную ошибку 422,
а не 500 от нарушенного CHECK.
"""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PlainSerializer, StringConstraints

# Пробелы по краям обрезаются до проверки длины: название «   » не пройдёт.
Text100 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Text300 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


# Время всегда отдаём в UTC (docs/quiz-design.md, раздел 9), даже если
# у сервера PostgreSQL настроен другой часовой пояс.
UtcDatetime = Annotated[
    datetime, PlainSerializer(lambda d: d.astimezone(UTC).isoformat().replace("+00:00", "Z"), return_type=str)
]


# --- Запрос: POST и PUT /api/quizzes ---


class OptionIn(BaseModel):
    text: Text100
    is_correct: bool = False


def _exactly_one_correct(options: list[OptionIn]) -> list[OptionIn]:
    correct = sum(o.is_correct for o in options)
    if correct != 1:
        raise ValueError(f"нужен ровно один правильный вариант, отмечено {correct}")
    return options


class QuestionIn(BaseModel):
    text: Text300
    time_limit_sec: int = Field(default=20, ge=5, le=120)
    options: Annotated[list[OptionIn], Field(min_length=2, max_length=4), AfterValidator(_exactly_one_correct)]


class QuizIn(BaseModel):
    title: Text100
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] = ""
    questions: list[QuestionIn] = Field(min_length=1, max_length=50)


# --- Ответы ---


class QuizSummary(BaseModel):
    """Строка списка «мои викторины»: без вопросов."""

    id: int
    title: str
    question_count: int
    updated_at: UtcDatetime


class OptionOut(BaseModel):
    # from_attributes: модель собирается прямо из объектов SQLAlchemy.
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    text: str
    is_correct: bool


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    text: str
    time_limit_sec: int
    options: list[OptionOut]


class QuizOut(BaseModel):
    """Викторина целиком, с правильными ответами — для редактора владельца."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    created_at: UtcDatetime
    updated_at: UtcDatetime
    questions: list[QuestionOut]

