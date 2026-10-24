# content

Сервис аккаунтов ведущих и викторин (Python, FastAPI). Контракты описаны в [`docs/quiz-design.md`](../docs/quiz-design.md).

## Структура

| Файл | Что внутри |
|---|---|
| `app/__main__.py` | точка входа `python -m app`: конфиг, затем uvicorn |
| `app/main.py` | `create_app`: сборка приложения, `/health` |
| `app/config.py` | переменные окружения `PORT`, `DATABASE_URL`, `JWT_SECRET` |
| `app/db.py` | движок SQLAlchemy и сессия на запрос |
| `app/models.py` | таблицы схемы `content` для ORM |
| `app/security.py` | хэши паролей (bcrypt), выпуск и проверка JWT |
| `app/deps.py` | зависимости ручек: сессия БД, конфиг, текущий ведущий из токена |
| `app/routers/auth.py` | `/api/auth/register`, `/api/auth/login` |
| `app/errors.py` | единый формат ошибок `{"error": "..."}` |
| `../deploy/migrations/0001_content_init.*.sql` | таблицы схемы `content` |

## Запуск локально (Windows)

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest
```

Без БД тесты, которым она нужна, пропускаются (`s` в выводе pytest). Чтобы прогнать все, укажи тестовую БД. Схему `content` в ней тесты пересоздают сами, поэтому **не указывай БД с нужными данными**:

```bash
TEST_DATABASE_URL=postgres://postgres:pw@localhost:5432/quiz .venv/Scripts/python -m pytest
```

Сервису нужен PostgreSQL со схемой `content`, к которой применена миграция. Пока нет `docker-compose`, БД можно поднять вручную:

```bash
docker run -d --name quiz-pg -p 5432:5432 -e POSTGRES_PASSWORD=pw -e POSTGRES_DB=quiz postgres:17-alpine
docker exec quiz-pg psql -U postgres -d quiz -c "CREATE SCHEMA content;"
docker run --rm -v "$(pwd -W)/../deploy/migrations:/migrations" migrate/migrate:v4.18.3 -path=/migrations -database "postgres://postgres:pw@host.docker.internal:5432/quiz?sslmode=disable" up
```

Затем сервис:

```bash
DATABASE_URL=postgres://postgres:pw@localhost:5432/quiz JWT_SECRET=local-dev-secret-at-least-32-bytes .venv/Scripts/python -m app
```
