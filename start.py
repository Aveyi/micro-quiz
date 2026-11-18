#!/usr/bin/env python3
"""Запуск всей системы одной командой: сервер, демо-викторины и приложение.

    python start.py              # Windows
    python3 start.py             # macOS и Linux

Что делает по шагам:
  1. проверяет Python, Docker и docker compose;
  2. создаёт deploy/.env из образца, если его ещё нет;
  3. поднимает сервер: docker compose up -d --build (первый раз несколько минут);
  4. ждёт, пока сервер ответит, и загружает три демо-викторины;
  5. готовит окружение приложения (desktop/.venv) и запускает его.

Ключи:
  --stop        остановить сервер (docker compose down)
  --no-docker   не трогать Docker: сервер уже запущен (например, у друга)
  --no-app      только сервер и викторины, без окна приложения

Файл намеренно написан на «старом» Python без новых возможностей языка,
чтобы он запускался и на системном Python macOS и сам объяснил, если версия мала.
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEPLOY = ROOT / "deploy"
CONTENT = ROOT / "content"
DESKTOP = ROOT / "desktop"

URL = "http://localhost:8000"  # адрес, который nginx открывает наружу
PROBE_URL = "http://127.0.0.1:8000/api/quizzes"  # любая ручка content: без токена отвечает 401
WAIT_SEC = 240  # сколько ждём, пока сервер поднимется
MIN_PYTHON = (3, 10)  # в коде приложения аннотации вида «X | None»


class StartError(Exception):
    """Шаг не удался; текст — для пользователя."""


def say(text: str = "") -> None:
    print(text, flush=True)


def step(title: str) -> None:
    say("")
    say("== " + title)


def run(command: list, cwd: Path) -> int:
    """Запускает команду, показывая её вывод, и возвращает код завершения."""
    say("$ " + " ".join(str(part) for part in command))
    return subprocess.call([str(part) for part in command], cwd=str(cwd))


def check_python() -> None:
    if sys.version_info < MIN_PYTHON:
        have = "%d.%d" % sys.version_info[:2]
        want = "%d.%d" % MIN_PYTHON
        raise StartError("Нужен Python %s или новее, а запущен %s. Установите свежий с python.org." % (want, have))


def check_docker() -> None:
    if shutil.which("docker") is None:
        raise StartError("Docker не найден. Установите Docker Desktop: https://www.docker.com/products/docker-desktop/")
    quiet = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if subprocess.call(["docker", "info"], **quiet) != 0:
        raise StartError("Docker не отвечает. Запустите Docker Desktop и дождитесь, пока он загрузится, потом повторите.")
    if subprocess.call(["docker", "compose", "version"], **quiet) != 0:
        raise StartError("Нет команды «docker compose». Обновите Docker Desktop до свежей версии.")


def ensure_env() -> None:
    """deploy/.env нужен docker compose, а в git он не хранится (там секреты)."""
    target = DEPLOY / ".env"
    if target.exists():
        say("deploy/.env уже есть, не трогаю.")
        return
    shutil.copyfile(str(DEPLOY / ".env.example"), str(target))
    say("Создан deploy/.env из образца. Пароли в нём учебные: подходят для показа,")
    say("а для настоящей работы замените их случайными (как — написано в самом файле).")


def start_server() -> None:
    if run(["docker", "compose", "up", "-d", "--build"], DEPLOY) != 0:
        raise StartError(
            "Не удалось поднять сервер. Частые причины: нет интернета (первый запуск скачивает образы),\n"
            "занят порт 8000 или не хватило памяти у Docker. Подробности — в выводе выше."
        )


def stop_server() -> None:
    if run(["docker", "compose", "down"], DEPLOY) != 0:
        raise StartError("Не удалось остановить сервер, подробности выше.")
    say("Сервер остановлен. Данные (викторины, игры) сохранены: при следующем запуске они будут на месте.")


def server_is_up() -> bool:
    try:
        urllib.request.urlopen(PROBE_URL, timeout=3)
        return True
    except urllib.error.HTTPError as e:
        return e.code == 401  # content ответил, что нужен токен, — значит, сервер живой
    except (urllib.error.URLError, OSError):
        return False


def wait_for_server() -> None:
    say("Жду, пока сервер ответит (до %d секунд)..." % WAIT_SEC)
    deadline = time.time() + WAIT_SEC
    while time.time() < deadline:
        if server_is_up():
            say("Сервер отвечает: " + URL)
            return
        time.sleep(2)
    raise StartError(
        "Сервер не ответил за %d секунд. Посмотрите, что с ним: «docker compose ps» и «docker compose logs»\n"
        "в папке deploy." % WAIT_SEC
    )


def seed_quizzes() -> None:
    # Скрипт загрузки пользуется только стандартной библиотекой: ставить ничего не нужно.
    if run([sys.executable, "-m", "app.seed", "--url", URL], CONTENT) != 0:
        raise StartError("Не удалось загрузить демо-викторины, подробности выше.")


def venv_python() -> Path:
    if os.name == "nt":
        return DESKTOP / ".venv" / "Scripts" / "python.exe"
    return DESKTOP / ".venv" / "bin" / "python"


def ensure_desktop_env() -> Path:
    python = venv_python()
    if not python.exists():
        say("Создаю окружение приложения (desktop/.venv)...")
        if run([sys.executable, "-m", "venv", ".venv"], DESKTOP) != 0:
            raise StartError("Не удалось создать окружение. На Linux может понадобиться пакет python3-venv.")
    quiet = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if subprocess.call([str(python), "-c", "import PySide6"], cwd=str(DESKTOP), **quiet) != 0:
        say("Ставлю зависимости приложения (PySide6), это нужно один раз...")
        if run([python, "-m", "pip", "install", "-r", "requirements.txt"], DESKTOP) != 0:
            raise StartError("Не удалось поставить зависимости приложения: нужен интернет.")
    return python


def lan_addresses() -> list:
    """Адреса этого компьютера в локальной сети, чтобы подсказать, куда подключаться с другого.

    Адресов может быть несколько (Wi-Fi, виртуальные сети Docker и VPN), поэтому
    показываем все подходящие, а домашние сети (192.168.x.x) ставим первыми.
    """
    found = []
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("10.255.255.255", 1))  # UDP: пакеты не уходят, нужен только выбор интерфейса
        found.append(sock.getsockname()[0])
        sock.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass

    def rank(address: str) -> int:
        if address.startswith("192.168."):
            return 0
        if address.startswith("10."):
            return 1
        return 2  # 172.x: чаще всего виртуальные сети Docker

    unique = sorted(set(a for a in found if not a.startswith("127.")), key=lambda a: (rank(a), a))
    return unique[:3]


def print_summary(with_app: bool) -> None:
    step("Всё готово")
    say("Вход ведущего:  demo  /  demo12345")
    say("Три викторины: «Мемы», «Космос» и «IT и программирование».")
    say("")
    addresses = lan_addresses() or ["<IP-адрес этого компьютера>"]
    say("Играть вдвоём на одном сервере: на втором компьютере в приложении откройте")
    say("«Приложение -> Настройки сервера…» и введите  " + "  или  ".join("http://%s:8000" % a for a in addresses))
    say("(оба компьютера в одной сети; если первый адрес не подошёл, попробуйте следующий).")
    say("")
    say("Остановить сервер:  python start.py --stop")
    if with_app:
        say("Запускаю приложение. Когда закроете окно, сервер продолжит работать.")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # русский текст в консоли Windows
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description="Запуск системы викторины одной командой.")
    parser.add_argument("--stop", action="store_true", help="остановить сервер")
    parser.add_argument("--no-docker", action="store_true", help="не трогать Docker: сервер уже запущен")
    parser.add_argument("--no-app", action="store_true", help="не открывать окно приложения")
    args = parser.parse_args()

    try:
        step("Проверяю, что всё нужное установлено")
        check_python()
        if not args.no_docker:
            check_docker()
            ensure_env()
        say("Python %d.%d, Docker: %s" % (sys.version_info[0], sys.version_info[1], "не нужен" if args.no_docker else "в порядке"))

        if args.stop:
            step("Останавливаю сервер")
            stop_server()
            return 0

        if not args.no_docker:
            step("Поднимаю сервер (первый раз это несколько минут)")
            start_server()
        step("Жду сервер")
        wait_for_server()
        step("Загружаю демо-викторины")
        seed_quizzes()

        python = None
        if not args.no_app:
            step("Готовлю приложение")
            python = ensure_desktop_env()
        print_summary(with_app=not args.no_app)
        if python is not None:
            return subprocess.call([str(python), "-m", "quiz_desktop"], cwd=str(DESKTOP))
        return 0
    except StartError as e:
        say("")
        say("ОШИБКА: " + str(e))
        return 1
    except KeyboardInterrupt:
        say("")
        say("Прервано.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
