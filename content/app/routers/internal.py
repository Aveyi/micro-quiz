"""Внутренний API для live: /internal (docs/quiz-design.md, раздел 5.2).

nginx эту ветку наружу не пропускает, live обращается напрямую по сети
Docker. Здесь отдаются правильные ответы, поэтому дополнительно нужен
общий секрет в заголовке X-Internal-Token.
"""

from fastapi import APIRouter, Depends, HTTPException

from app.deps import SessionDep, require_internal_token
from app.routers.quizzes import QuizId, load_quiz
from app.schemas import InternalQuiz

router = APIRouter(
    prefix="/internal",
    tags=["internal"],
    # Проверка токена для всех ручек ветки сразу: новую ручку нельзя
    # случайно оставить открытой.
    dependencies=[Depends(require_internal_token)],
    # В /docs не показываем: это не API для клиентов.
    include_in_schema=False,
)


@router.get("/quizzes/{quiz_id}")
def get_quiz(quiz_id: QuizId, session: SessionDep) -> InternalQuiz:
    quiz = load_quiz(session, quiz_id)
    if quiz is None:
        raise HTTPException(404, "викторина не найдена")
    return InternalQuiz.model_validate(quiz)
