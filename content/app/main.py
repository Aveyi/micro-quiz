"""Сервис content: аккаунты ведущих, викторины, вопросы."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import Config
from app.db import make_engine, make_session_factory
from app.errors import install_error_handlers


def create_app(config: Config) -> FastAPI:
    """Фабрика вместо глобального app: тесты собирают приложение со своим конфигом."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        # При остановке закрываем соединения пула, чтобы PostgreSQL
        # не держал их до таймаута.
        app.state.engine.dispose()

    app = FastAPI(title="quiz content", lifespan=lifespan)
    app.state.engine = make_engine(config.database_url)
    app.state.session_factory = make_session_factory(app.state.engine)
    install_error_handlers(app)

    @app.get("/health")
    def health() -> dict[str, str]:
        """Для Docker (HEALTHCHECK) и nginx: отвечает, что процесс жив."""
        return {"status": "ok"}

    return app
