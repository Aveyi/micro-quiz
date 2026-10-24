"""Пароли и JWT ведущих (docs/quiz-design.md, раздел 6).

Токен проверяет и live (live/internal/auth), поэтому формат и проверки
здесь и там должны совпадать.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

ISSUER = "quiz-content"
ALGORITHM = "HS256"
TOKEN_TTL = timedelta(hours=12)
# Допустимое расхождение часов при проверке exp — как в live.
LEEWAY = timedelta(seconds=30)

# bcrypt учитывает только первые 72 байта пароля, а bcrypt 5 на более
# длинный пароль бросает ошибку. Поэтому длину ограничиваем явно.
MAX_PASSWORD_BYTES = 72


class InvalidToken(Exception):
    """Токену нельзя верить: подпись, срок или поля не те."""


@dataclass(frozen=True)
class TokenUser:
    id: int
    username: str


def hash_password(password: str) -> str:
    # gensalt() — случайная соль для каждого пароля: одинаковые пароли
    # дают разные хэши, и заранее посчитанные таблицы не помогут.
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    raw = password.encode()
    if len(raw) > MAX_PASSWORD_BYTES:
        return False
    return bcrypt.checkpw(raw, password_hash.encode())


# Хэш случайного пароля. Если пользователя нет, проверяем пароль по нему:
# так ответ занимает столько же времени, сколько при неверном пароле,
# и по времени ответа нельзя узнать, существует ли логин.
DUMMY_HASH = hash_password("dummy-password-for-timing")


def create_token(user_id: int, username: str, secret: str, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    payload = {
        # По стандарту JWT sub — строка.
        "sub": str(user_id),
        "username": username,
        "iss": ISSUER,
        "iat": now,
        "exp": now + TOKEN_TTL,
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_token(token: str, secret: str) -> TokenUser:
    try:
        payload = jwt.decode(
            token,
            secret,
            # Принимаем только HS256: иначе можно прислать токен с "alg": "none".
            algorithms=[ALGORITHM],
            issuer=ISSUER,
            # Без exp токен был бы вечным, без sub непонятно, чей он.
            options={"require": ["exp", "iss", "sub"]},
            leeway=LEEWAY,
        )
    except jwt.InvalidTokenError as e:
        raise InvalidToken(str(e)) from None

    sub, username = payload["sub"], payload.get("username")
    # isascii(): isdigit() пропускает и символы вроде «²», на которых int() упадёт.
    if not (isinstance(sub, str) and sub.isascii() and sub.isdigit() and int(sub) > 0) or not isinstance(username, str):
        raise InvalidToken(f"неверные sub {sub!r} или username {username!r}")
    return TokenUser(id=int(sub), username=username)
