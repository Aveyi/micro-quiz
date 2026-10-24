# Образ сервиса content. Сборка из папки content/:
#   docker build -t quiz-content .
#
# Один этап, без multi-stage: все зависимости ставятся готовыми колёсами
# (wheels), компилятор не нужен, и отдельному этапу сборки нечего отбрасывать.

# slim — Debian без лишних пакетов. Официальный образ мультиархитектурный:
# один и тот же Dockerfile собирается и на x86-64 (Windows), и на arm64 (Mac M3).
FROM python:3.14-slim

# PYTHONDONTWRITEBYTECODE — не писать .pyc: в контейнере они не переживут перезапуск.
# PYTHONUNBUFFERED — логи сразу в stdout, без буфера: docker logs видит их сразу,
# а при падении последние строки не теряются.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /srv

# Сначала только зависимости: этот слой пересобирается, лишь когда меняется
# requirements.txt, а правки кода берут его из кэша, и сборка идёт секунды.
COPY requirements.txt .
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

COPY app ./app

# Процесс работает не от root: если в сервисе найдётся уязвимость,
# у атакующего не будет прав root внутри контейнера.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
USER 10001

EXPOSE 8000

# curl и wget в slim нет, поэтому проверяем самим Python. Порт берётся
# из $PORT: если его переопределить, проверка пойдёт туда же, куда слушает сервис.
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ['PORT'] + '/health', timeout=2)"]

# Exec form (JSON-массив): python становится процессом с PID 1 и сам получает
# SIGTERM от docker stop. В shell form сигнал получил бы sh, а не сервис,
# и через 10 с Docker убил бы его без корректной остановки.
CMD ["python", "-m", "app"]
