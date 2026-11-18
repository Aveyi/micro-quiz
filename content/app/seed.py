"""Загрузка демонстрационных викторин в работающий сервис content.

Викторины лежат в seed_quizzes.json. Скрипт ходит в обычный публичный API
(регистрация, вход, POST /api/quizzes), поэтому все проверки сервиса работают
и для них, а владельцем викторин становится демо-ведущий.

    python -m app.seed --url http://localhost:8000

Повторный запуск безопасен: викторины, которые у демо-ведущего уже есть
(по названию), пропускаются.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

DATA_FILE = Path(__file__).with_name("seed_quizzes.json")
DEFAULT_URL = "http://localhost:8000"
# Демо-аккаунт нужен только чтобы показать приложение; настоящих секретов
# в нём нет. Для боевого сервера задайте свои значения через --username/--password.
DEFAULT_USERNAME = "demo"
DEFAULT_PASSWORD = "demo12345"
TIMEOUT_SEC = 10

# Вызов API: (метод, путь, тело, токен) → (код ответа, разобранный JSON).
# Вынесен в параметр, чтобы тесты могли подставить TestClient вместо сети.
Call = Callable[[str, str, dict | None, str | None], tuple[int, object]]


class SeedError(Exception):
    """Загрузка не удалась по понятной причине (текст — для пользователя)."""


def load_quizzes() -> list[dict]:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def http_call(base_url: str) -> Call:
    """Вызов API по сети через стандартную библиотеку: зависимости не нужны."""

    def call(method: str, path: str, body: dict | None = None, token: str | None = None) -> tuple[int, object]:
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body, ensure_ascii=False).encode()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(base_url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response:
                raw = response.read()
                return response.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            # Ошибки сервиса приходят как {"error": "..."}; их показываем как есть.
            try:
                return e.code, json.loads(e.read())
            except ValueError:
                return e.code, None
        except urllib.error.URLError as e:
            raise SeedError(f"Сервер {base_url} недоступен: {e.reason}") from None

    return call


def _error_text(payload: object, status: int) -> str:
    if isinstance(payload, dict) and isinstance(payload.get("error"), str):
        return f"{payload['error']} (код {status})"
    return f"ошибка сервера (код {status})"


def seed(call: Call, quizzes: list[dict], username: str, password: str, log: Callable[[str], None] = print) -> int:
    """Создаёт демо-ведущего и недостающие викторины. Возвращает, сколько создано."""
    credentials = {"username": username, "password": password}

    status, payload = call("POST", "/api/auth/register", credentials, None)
    if status == 201:
        log(f"Создан демо-ведущий «{username}»")
    elif status != 409:  # 409 — такой ведущий уже есть, это нормально
        raise SeedError(f"Не удалось зарегистрировать ведущего: {_error_text(payload, status)}")

    status, payload = call("POST", "/api/auth/login", credentials, None)
    if status != 200 or not isinstance(payload, dict):
        raise SeedError(f"Не удалось войти как «{username}»: {_error_text(payload, status)}")
    token = payload["access_token"]

    status, payload = call("GET", "/api/quizzes", None, token)
    if status != 200 or not isinstance(payload, list):
        raise SeedError(f"Не удалось получить список викторин: {_error_text(payload, status)}")
    existing = {q["title"] for q in payload}

    created = 0
    for quiz in quizzes:
        if quiz["title"] in existing:
            log(f"Уже есть: «{quiz['title']}»")
            continue
        status, payload = call("POST", "/api/quizzes", quiz, token)
        if status != 201:
            raise SeedError(f"Не удалось создать «{quiz['title']}»: {_error_text(payload, status)}")
        log(f"Создана: «{quiz['title']}» ({len(quiz['questions'])} вопросов)")
        created += 1
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description="Загрузить демонстрационные викторины в сервис content.")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"адрес сервиса (по умолчанию {DEFAULT_URL})")
    parser.add_argument("--username", default=DEFAULT_USERNAME, help="имя демо-ведущего")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="пароль демо-ведущего")
    args = parser.parse_args()

    try:
        created = seed(http_call(args.url.rstrip("/")), load_quizzes(), args.username, args.password)
    except SeedError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 1
    print(f"Готово: создано викторин — {created}. Войдите как «{args.username}».")
    return 0


if __name__ == "__main__":
    sys.exit(main())
