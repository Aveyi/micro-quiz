"""Общие зависимости FastAPI для ручек."""

import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import Config
from app.db import get_session
from app.security import InvalidToken, TokenUser, decode_token

# auto_error=False: отсутствие токена обрабатываем сами, чтобы ответ был
# в нашем формате. HTTPBearer здесь ещё и добавляет кнопку Authorize в /docs.
_bearer = HTTPBearer(auto_error=False)

# По стандарту HTTP при 401 сервер говорит, какую схему авторизации ждёт.
_WWW_AUTHENTICATE = {"WWW-Authenticate": "Bearer"}


def get_config(request: Request) -> Config:
    return request.app.state.config


def current_user(
    config: Annotated[Config, Depends(get_config)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> TokenUser:
    """Ведущий из заголовка Authorization: Bearer <JWT>, иначе 401.

    В БД не ходим: подписи токена достаточно, в этом смысл JWT.
    """
    if credentials is None:
        raise HTTPException(401, "нужна авторизация", headers=_WWW_AUTHENTICATE)
    try:
        return decode_token(credentials.credentials, config.jwt_secret)
    except InvalidToken:
        raise HTTPException(401, "токен невалиден или просрочен", headers=_WWW_AUTHENTICATE) from None


def require_internal_token(
    config: Annotated[Config, Depends(get_config)],
    x_internal_token: Annotated[str, Header()] = "",
) -> None:
    """Пропускает только запросы от live с общим INTERNAL_TOKEN, иначе 401."""
    # compare_digest сравнивает за постоянное время: обычное == выходит
    # на первом несовпавшем символе, и по времени ответа можно подбирать токен.
    if not hmac.compare_digest(x_internal_token.encode(), config.internal_token.encode()):
        raise HTTPException(401, "неверный X-Internal-Token")


SessionDep = Annotated[Session, Depends(get_session)]
ConfigDep = Annotated[Config, Depends(get_config)]
CurrentUser = Annotated[TokenUser, Depends(current_user)]
