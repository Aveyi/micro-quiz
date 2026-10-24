"""Единый формат ошибок: {"error": "текст"} (docs/quiz-design.md, раздел 9).

FastAPI по умолчанию отвечает {"detail": ...}, а на ошибки проверки
возвращает список объектов. Здесь эти ответы приводятся к общему формату,
чтобы десктопу и live не приходилось разбирать два вида ошибок.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger(__name__)


def error_response(status_code: int, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status_code, headers=headers)


def install_error_handlers(app: FastAPI) -> None:
    # Обработчик для HTTPException из Starlette ловит и HTTPException FastAPI
    # (это подкласс), и ошибки самого роутера: 404 на неизвестный путь, 405.
    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return error_response(exc.status_code, str(exc.detail), exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(422, _validation_message(exc))

    # Неожиданные исключения: клиенту не показываем подробности (там могут
    # быть SQL и пути к файлам), а в лог пишем полностью.
    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        log.exception("необработанная ошибка: %s %s", request.method, request.url.path)
        return error_response(500, "внутренняя ошибка сервера")


def _validation_message(exc: RequestValidationError) -> str:
    """Склеивает ошибки Pydantic в одну строку:
    'questions.0.options: List should have at least 2 items; title: Field required'."""
    parts = []
    for err in exc.errors():
        if err["type"] == "json_invalid":
            return "тело запроса не является корректным JSON"
        # Первый элемент loc — откуда поле (body, query, path); клиенту он не нужен.
        loc = ".".join(str(p) for p in err["loc"][1:])
        parts.append(f"{loc}: {err['msg']}" if loc else err["msg"])
    return "; ".join(parts)
