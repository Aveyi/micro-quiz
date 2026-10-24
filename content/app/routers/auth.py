"""Регистрация и вход ведущих: /api/auth (docs/quiz-design.md, раздел 5.1)."""

from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import AfterValidator, BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.deps import ConfigDep, SessionDep
from app.models import User
from app.security import DUMMY_HASH, MAX_PASSWORD_BYTES, create_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _password_bytes(value: str) -> str:
    if len(value.encode()) > MAX_PASSWORD_BYTES:
        raise ValueError(f"пароль длиннее {MAX_PASSWORD_BYTES} байт")
    return value


# Буквы (в том числе русские), цифры, _ . -; без пробелов, чтобы
# «teacher» и «teacher » не выглядели одинаково.
Username = Annotated[str, Field(min_length=3, max_length=32, pattern=r"^[\w.-]+$")]
Password = Annotated[str, Field(min_length=8), AfterValidator(_password_bytes)]


class RegisterRequest(BaseModel):
    username: Username
    password: Password


class RegisterResponse(BaseModel):
    id: int
    username: str


class LoginRequest(BaseModel):
    # При входе формат не проверяем: неверный логин — это просто 401.
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/register", status_code=201)
def register(body: RegisterRequest, session: SessionDep) -> RegisterResponse:
    user = User(username=body.username, password_hash=hash_password(body.password))
    session.add(user)
    try:
        session.commit()
    except IntegrityError as e:
        session.rollback()
        # Проверять заранее через SELECT ненадёжно: два одновременных запроса
        # оба увидят, что имя свободно. Уникальный индекс в БД решает это сам.
        if getattr(e.orig.diag, "constraint_name", None) == "users_username_key":
            raise HTTPException(409, "имя пользователя уже занято") from None
        raise
    return RegisterResponse(id=user.id, username=user.username)


@router.post("/login")
def login(body: LoginRequest, session: SessionDep, config: ConfigDep) -> TokenResponse:
    user = session.scalar(select(User).where(User.username == body.username))
    # Пароль проверяем даже для несуществующего логина (см. DUMMY_HASH).
    password_ok = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if user is None or not password_ok:
        # Одна и та же ошибка для обоих случаев: не подсказываем, какие логины есть.
        raise HTTPException(401, "неверное имя пользователя или пароль")
    return TokenResponse(access_token=create_token(user.id, user.username, config.jwt_secret))
