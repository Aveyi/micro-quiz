"""Викторины ведущего: /api/quizzes (docs/quiz-design.md, раздел 5.1)."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.deps import CurrentUser, SessionDep
from app.models import AnswerOption, Question, Quiz
from app.schemas import QuizIn, QuizOut, QuizSummary

router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])

# id в БД — BIGINT. Без верхней границы число вроде 10**20 дошло бы
# до PostgreSQL и вернулось ошибкой 500 вместо понятной 422.
QuizId = Annotated[int, Path(ge=1, le=2**63 - 1)]


def _build_questions(body: QuizIn) -> list[Question]:
    """Вопросы и варианты из запроса. position — порядок в присланном списке."""
    return [
        Question(
            position=qi,
            text=q.text,
            time_limit_sec=q.time_limit_sec,
            options=[AnswerOption(position=oi, text=o.text, is_correct=o.is_correct) for oi, o in enumerate(q.options)],
        )
        for qi, q in enumerate(body.questions)
    ]


def _get_own_quiz(session: Session, quiz_id: int, user: CurrentUser) -> Quiz:
    quiz = session.scalar(
        select(Quiz)
        .where(Quiz.id == quiz_id)
        # Подгружаем вопросы и варианты двумя запросами с IN (...),
        # а не отдельным запросом на каждый вопрос (проблема N+1).
        .options(selectinload(Quiz.questions).selectinload(Question.options))
    )
    # Чужая викторина отвечает так же, как несуществующая: иначе по коду
    # 403 можно было бы перебором узнать, какие id викторин существуют.
    if quiz is None or quiz.owner_id != user.id:
        raise HTTPException(404, "викторина не найдена")
    return quiz


@router.get("")
def list_quizzes(session: SessionDep, user: CurrentUser) -> list[QuizSummary]:
    question_count = (
        select(func.count(Question.id)).where(Question.quiz_id == Quiz.id).correlate(Quiz).scalar_subquery()
    )
    rows = session.execute(
        select(Quiz.id, Quiz.title, question_count.label("question_count"), Quiz.updated_at)
        .where(Quiz.owner_id == user.id)
        .order_by(Quiz.updated_at.desc(), Quiz.id.desc())
    )
    return [QuizSummary.model_validate(row, from_attributes=True) for row in rows]


@router.post("", status_code=201)
def create_quiz(body: QuizIn, session: SessionDep, user: CurrentUser) -> QuizOut:
    quiz = Quiz(owner_id=user.id, title=body.title, description=body.description, questions=_build_questions(body))
    session.add(quiz)
    session.commit()
    # Перечитываем, чтобы в ответе были id и время, которые выдала БД.
    return QuizOut.model_validate(_get_own_quiz(session, quiz.id, user))


@router.get("/{quiz_id}")
def get_quiz(quiz_id: QuizId, session: SessionDep, user: CurrentUser) -> QuizOut:
    return QuizOut.model_validate(_get_own_quiz(session, quiz_id, user))


@router.put("/{quiz_id}")
def replace_quiz(quiz_id: QuizId, body: QuizIn, session: SessionDep, user: CurrentUser) -> QuizOut:
    quiz = _get_own_quiz(session, quiz_id, user)
    quiz.title = body.title
    quiz.description = body.description
    quiz.updated_at = func.now()

    # Сначала удаляем старые вопросы и сразу отправляем это в БД (flush),
    # потом добавляем новые. Если сделать всё одним flush, SQLAlchemy может
    # вставить новые раньше, чем удалит старые, и сработает UNIQUE (quiz_id, position).
    # У новых вопросов и вариантов будут новые id.
    quiz.questions.clear()
    session.flush()
    quiz.questions = _build_questions(body)
    session.commit()

    session.expire_all()
    return QuizOut.model_validate(_get_own_quiz(session, quiz_id, user))


@router.delete("/{quiz_id}", status_code=204)
def delete_quiz(quiz_id: QuizId, session: SessionDep, user: CurrentUser) -> Response:
    # Вопросы и варианты удаляются вместе с викториной: так настроен cascade
    # в моделях, а в БД то же гарантирует ON DELETE CASCADE.
    session.delete(_get_own_quiz(session, quiz_id, user))
    session.commit()
    return Response(status_code=204)
