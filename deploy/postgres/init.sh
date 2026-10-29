#!/bin/sh
# Схемы и пользователи PostgreSQL для сервисов (docs/quiz-design.md, раздел 7.1).
#
# Образ postgres выполняет скрипты из /docker-entrypoint-initdb.d только при
# ПЕРВОМ запуске, когда том с данными пуст. Поправили скрипт — изменения
# применятся только после `docker compose down -v` (это удаляет данные).
#
# Таблицы здесь не создаются: это делают миграции (контейнер migrate).
#
# Файл должен быть исполняемым (в git он хранится с правом 755): образ
# запускает его отдельным процессом. Docker Desktop на macOS для подключённых
# файлов отвечает «исполняемый», даже если права нет, и запуск тогда падает
# с «bad interpreter: Permission denied».
#
# Без `set -eu` специально: если образ решит, что файл не исполняемый, он
# подключит его в свою оболочку, и флаги остались бы в ней. Ошибки ловим
# проверками ниже и ON_ERROR_STOP в psql.

# Пароли приходят из окружения контейнера (их передаёт compose из .env).
# Без них — понятная ошибка, а не пользователь с пустым паролем.
: "${LIVE_PASSWORD:?LIVE_PASSWORD не задан}"
: "${CONTENT_PASSWORD:?CONTENT_PASSWORD не задан}"

# Пароли передаём в psql переменными (-v), а не вставляем в текст SQL:
# psql сам экранирует :'имя', и кавычка в пароле не сломает запрос.
# 'SQL' в кавычках — оболочка не трогает текст ниже, $ и кавычки идут как есть.
psql -v ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -v db="$POSTGRES_DB" \
    -v owner="$POSTGRES_USER" \
    -v live_password="$LIVE_PASSWORD" \
    -v content_password="$CONTENT_PASSWORD" \
    <<'SQL'
-- У каждого сервиса свой пользователь: database per service.
CREATE ROLE live_user LOGIN PASSWORD :'live_password';
CREATE ROLE content_user LOGIN PASSWORD :'content_password';

-- Подключаться к базе могут только наши сервисы (и суперпользователь).
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db" TO live_user, content_user;

-- Схемы принадлежат суперпользователю: под ним работают миграции.
CREATE SCHEMA live;
CREATE SCHEMA content;

-- Каждый видит только свою схему. В чужую — «permission denied for schema».
GRANT USAGE ON SCHEMA live TO live_user;
GRANT USAGE ON SCHEMA content TO content_user;

-- Главная тонкость. Таблицы создаст migrate под суперпользователем, значит,
-- их владельцем будет он, и USAGE на схему мало: сервис увидит таблицу, но
-- получит «permission denied for table». Таблиц ещё нет, поэтому выдаём права
-- ПО УМОЛЧАНИЮ: на все таблицы, которые owner создаст в схеме потом.
-- Создавать и удалять таблицы сервисы не могут — это работа миграций.
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA live
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO live_user;
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA content
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO content_user;
SQL
