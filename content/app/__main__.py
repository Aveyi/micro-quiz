"""Точка входа: python -m app.

Uvicorn запускаем из кода, а не командой `uvicorn app.main:app`,
чтобы порт брался из проверенного конфига, а ошибки настроек
выводились до старта сервера.
"""

import logging
import sys

import uvicorn

from app import config
from app.main import create_app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        cfg = config.load()
    except config.ConfigError as e:
        logging.error("ошибка конфигурации: %s", e)
        sys.exit(1)

    # SIGTERM от docker stop uvicorn обрабатывает сам: перестаёт принимать
    # соединения, дожидается текущих запросов и вызывает завершение lifespan.
    uvicorn.run(create_app(cfg), host="0.0.0.0", port=cfg.port)


if __name__ == "__main__":
    main()
