# Онлайн-викторина: проектные решения

> Общий документ команды. Описывает договорённости, от которых зависят оба сервиса и десктопное приложение. Если что-то меняется, сначала правим этот файл, потом код.
>
> Версия от 2026-10-23. Заменяет `scoreboard-context.md` (тема «турнир» больше не актуальна).

## Содержание

1. [Состав системы](#1-состав-системы)
2. [Правила игры](#2-правила-игры)
3. [Сценарий игры от начала до конца](#3-сценарий-игры-от-начала-до-конца)
4. [Протокол WebSocket](#4-протокол-websocket)
5. [REST API](#5-rest-api)
6. [Авторизация](#6-авторизация)
7. [База данных](#7-база-данных)
8. [Инфраструктура](#8-инфраструктура)
9. [Соглашения](#9-соглашения)
10. [Кто что делает](#10-кто-что-делает)

---

## 1. Состав системы

```
                 Десктопное приложение (Python, PySide6)
                    │                         │
         REST /api/...            REST /live/api/...  +  WebSocket /live/ws
                    ▼                         ▼
              ┌──────────────── nginx ─────────────────┐
              │  /api/*       → content (round robin)  │
              │  /live/api/*  → live    (round robin)  │
              │  /live/ws     → live    (hash по коду  │
              │                          комнаты)      │
              └───────┬─────────────────────┬──────────┘
                      ▼                     ▼
          content (Python, FastAPI)   live (Go)  ×N инстансов
                      │   ▲                 │
                      │   └── /internal ────┘   (вопросы с ответами, по внутренней сети)
                      ▼                     ▼
              ┌────────── PostgreSQL ──────────┐
              │ схема content  │  схема live   │
              └────────────────┴───────────────┘
```

| Сервис | Язык | Отвечает за |
|---|---|---|
| **content** | Python, FastAPI | аккаунты ведущих, викторины, вопросы, варианты ответов |
| **live** | Go | комнаты, проведение игры, таймеры, очки, таблица лидеров, история и результаты игр |
| **desktop** | Python, PySide6 | интерфейс ведущего и игрока |

**Почему микросервисы.** У сервисов разная природа нагрузки. `content` обслуживает редкие короткие запросы (создать викторину, войти). `live` во время игр держит много постоянных соединений и пиковую нагрузку в момент вопроса, поэтому масштабируется отдельно (несколько инстансов за nginx). Падение `live` не затрагивает викторины и аккаунты. Языки выбраны под задачу: Python для CRUD, Go для тысяч одновременных соединений.

---

## 2. Правила игры

| Правило | Решение |
|---|---|
| Ведущий | нужен аккаунт в `content` |
| Игроки | входят **по коду комнаты и нику**, без регистрации |
| Код комнаты | 6 цифр, например `482913` |
| Ник | 1–20 символов, пробелы по краям обрезаются, уникален в комнате без учёта регистра |
| Игроков в комнате | до 50 |
| Тип вопросов | **один правильный вариант** из 2–4 |
| Таймер | **свой у каждого вопроса**, 5–120 с, по умолчанию 20 с |
| Ответ | один раз, изменить нельзя |
| Очки | правильный ответ: от 500 до 1000 с **бонусом за скорость** (формула ниже); неправильный или нет ответа: 0 |
| Вход в идущую игру | **нельзя**, только пока комната в лобби |
| Обрыв связи у игрока | игрок **выбывает**, вернуться нельзя; его очки остаются в истории |
| Обрыв связи у ведущего | игра **отменяется**, всем игрокам приходит `room_closed` |
| Лобби без старта | закрывается через 30 минут |

### Формула очков

Время ответа измеряет **сервер**: от отправки вопроса до получения ответа. Часам клиентов не доверяем.

```
points = round(1000 × (1 − response_ms / (2 × time_limit_ms)))
```

- ответил мгновенно — 1000;
- ответил в последний момент — 500;
- неправильно или не успел — 0.

### Когда заканчивается вопрос

Когда истёк таймер **или** ответили все оставшиеся в игре игроки, смотря что раньше.

---

## 3. Сценарий игры от начала до конца

1. Ведущий входит в приложение: `POST /api/auth/login` → JWT.
2. Ведущий выбирает викторину и создаёт комнату: `POST /live/api/rooms` с `quiz_id`. Сервис `live`:
   - проверяет JWT;
   - запрашивает викторину у `content` по внутреннему API и убеждается, что она существует, принадлежит ведущему и в ней есть хотя бы один вопрос;
   - генерирует уникальный код и сохраняет сессию в БД со статусом `lobby`;
   - возвращает код комнаты.
3. Ведущий подключается: `/live/ws?room=482913` с заголовком `Authorization: Bearer <JWT>`. Инстанс, на который nginx направил комнату, создаёт её в памяти и загружает вопросы.
4. Игроки подключаются: `/live/ws?room=482913` (без токена) и первым сообщением отправляют `join` с ником. Все в комнате получают обновлённый список игроков.
5. Ведущий отправляет `start`. Новые игроки больше не могут войти.
6. Цикл по вопросам:
   - всем приходит `question` (без правильного ответа);
   - игроки отправляют `answer`;
   - ведущий видит, сколько игроков уже ответили (`answer_progress`);
   - вопрос заканчивается, всем приходит `question_result`: правильный ответ, таблица лидеров, а каждому игроку его личный результат;
   - ведущий отправляет `next`.
7. После последнего вопроса всем приходит `game_over` с итоговой таблицей. Результаты сохраняются в БД, сессия получает статус `finished`.
8. Историю своих игр ведущий смотрит через `GET /live/api/games`.

---

## 4. Протокол WebSocket

### 4.1 Подключение

```
GET /live/ws?room=<код>
Authorization: Bearer <JWT>      ← только для ведущего
```

- **Код комнаты в адресе**, потому что по нему nginx выбирает инстанс (раздел 8.2).
- **Токен в заголовке**, а не в адресе: адреса попадают в логи nginx и сервисов, а токен — секрет. Десктопный клиент (в отличие от браузера) умеет задавать заголовки при подключении.
- Роль определяется так: есть токен и его владелец совпадает с создателем комнаты — **ведущий**; нет токена — **игрок**.

Ошибки на этапе подключения возвращаются обычным HTTP-ответом до переключения протокола:
| Код | Когда |
|---|---|
| 400 | нет параметра `room` |
| 401 | токен передан, но невалиден или просрочен |
| 403 | токен валиден, но комната создана другим пользователем |
| 404 | комнаты с таким кодом нет или она уже завершена |

### 4.2 Конверт

Все сообщения в обе стороны — JSON такого вида:

```json
{"type": "имя_сообщения", "data": { ... }}
```

Поле `data` есть всегда, даже пустое (`{}`). Неизвестные `type` получатель игнорирует: так протокол можно расширять, не ломая старых клиентов.

### 4.3 Сообщения клиент → сервер

| type | Кто | data | Когда |
|---|---|---|---|
| `join` | игрок | `{"nickname": "Вася"}` | первое сообщение после подключения |
| `start` | ведущий | `{}` | в лобби, если есть хотя бы один игрок |
| `answer` | игрок | `{"question_index": 0, "option_id": 17}` | пока идёт вопрос |
| `next` | ведущий | `{}` | после `question_result` |

`question_index` в `answer` защищает от ситуации, когда ответ на прошлый вопрос пришёл, когда уже идёт следующий: такой ответ сервер отбрасывает.

### 4.4 Сообщения сервер → клиент

**`joined`** — только что подключившемуся (ведущему сразу, игроку после `join`):
```json
{"type": "joined", "data": {
  "role": "player",
  "player_id": 5,
  "room_code": "482913",
  "quiz_title": "Столицы мира",
  "question_count": 10,
  "players": [{"player_id": 5, "nickname": "Вася"}]
}}
```
У ведущего `"role": "host"` и нет `player_id`.

**`lobby_update`** — всем, когда в лобби кто-то вошёл или вышел:
```json
{"type": "lobby_update", "data": {"players": [{"player_id": 5, "nickname": "Вася"}, {"player_id": 6, "nickname": "Петя"}]}}
```

**`question`** — всем:
```json
{"type": "question", "data": {
  "question_index": 0,
  "question_count": 10,
  "text": "Столица Австралии?",
  "options": [{"option_id": 17, "text": "Сидней"}, {"option_id": 18, "text": "Канберра"}],
  "time_limit_sec": 20
}}
```
Правильного ответа здесь **нет**. Клиент отсчитывает таймер сам от момента получения; решающий таймер — на сервере.

**`answer_accepted`** — игроку, чей ответ принят:
```json
{"type": "answer_accepted", "data": {"question_index": 0}}
```

**`answer_progress`** — только ведущему, после каждого ответа:
```json
{"type": "answer_progress", "data": {"answered": 7, "total": 12}}
```

**`question_result`** — всем, когда вопрос закончился. Общая часть одинакова, поле `you` есть только у игроков, `option_counts` только у ведущего:
```json
{"type": "question_result", "data": {
  "question_index": 0,
  "correct_option_id": 18,
  "leaderboard": [{"rank": 1, "player_id": 6, "nickname": "Петя", "score": 1840}],
  "you": {"correct": true, "points": 912, "score": 1640, "rank": 2},
  "option_counts": {"17": 4, "18": 8}
}}
```
`leaderboard` — первые 10 мест. Своё место игрок видит в `you`, даже если не попал в десятку.

**`player_left`** — всем, когда игрок выбыл во время игры:
```json
{"type": "player_left", "data": {"player_id": 6, "nickname": "Петя"}}
```

**`game_over`** — всем после последнего вопроса:
```json
{"type": "game_over", "data": {
  "leaderboard": [{"rank": 1, "player_id": 6, "nickname": "Петя", "score": 8420}],
  "you": {"score": 7900, "rank": 2}
}}
```
Здесь `leaderboard` — все игроки. После `game_over` сервер закрывает соединение (код 1000).

**`room_closed`** — всем, если игра прервана:
```json
{"type": "room_closed", "data": {"reason": "host_left"}}
```
`reason`: `host_left`, `lobby_timeout`, `server_shutdown`. Затем сервер закрывает соединение.

**`error`** — на неверное действие клиента:
```json
{"type": "error", "data": {"code": "nickname_taken", "message": "Ник уже занят"}}
```

| code | Когда | Соединение |
|---|---|---|
| `nickname_taken` | ник уже есть в комнате | остаётся, можно отправить `join` ещё раз |
| `invalid_nickname` | пустой или длиннее 20 символов | остаётся |
| `room_full` | 50 игроков | закрывается |
| `game_already_started` | `join` после `start` | закрывается |
| `not_allowed` | игрок прислал `start`/`next` или ведущий прислал `answer` | остаётся |
| `invalid_state` | действие не в свою фазу (например, `next` во время вопроса) | остаётся |
| `already_answered` | второй ответ на тот же вопрос | остаётся |
| `bad_message` | не JSON или неизвестная структура | остаётся |

### 4.5 Состояния комнаты

```
lobby ──start──► question ──таймер / все ответили──► result ──next──► question ...
                                                       └──next после последнего──► finished
любое состояние ──ведущий отключился / таймаут лобби──► cancelled
```

---

## 5. REST API

Ответы в JSON. Ошибки в формате `{"error": "текст"}`. Защищённые ручки требуют заголовок `Authorization: Bearer <JWT>`.

### 5.1 Сервис content (`/api`)

| Метод и путь | Доступ | Что делает |
|---|---|---|
| `POST /api/auth/register` | все | регистрация: `{"username", "password"}` → `201` |
| `POST /api/auth/login` | все | вход: `{"username", "password"}` → `{"access_token": "...", "token_type": "bearer"}` |
| `GET /api/quizzes` | ведущий | мои викторины (без вопросов): `id`, `title`, `question_count`, `updated_at` |
| `POST /api/quizzes` | ведущий | создать викторину вместе с вопросами |
| `GET /api/quizzes/{id}` | владелец | викторина целиком, с отметкой правильных ответов (для редактора) |
| `PUT /api/quizzes/{id}` | владелец | заменить викторину целиком, включая вопросы (так проще, чем править по одному) |
| `DELETE /api/quizzes/{id}` | владелец | удалить |
| `GET /health` | все | проверка для Docker и nginx |

Тело `POST`/`PUT /api/quizzes`:
```json
{
  "title": "Столицы мира",
  "description": "Разминка",
  "questions": [
    {
      "text": "Столица Австралии?",
      "time_limit_sec": 20,
      "options": [
        {"text": "Сидней", "is_correct": false},
        {"text": "Канберра", "is_correct": true}
      ]
    }
  ]
}
```
Проверки: 1–50 вопросов, 2–4 варианта, **ровно один** `is_correct: true`, `time_limit_sec` от 5 до 120.

### 5.2 Внутренний API content (`/internal`)

Только для сервиса `live`. **nginx эту ветку наружу не пропускает**, обращение идёт напрямую по внутренней сети Docker (`http://content:8000`). Дополнительно требуется заголовок `X-Internal-Token: <INTERNAL_TOKEN>`.

| Метод и путь | Что отдаёт |
|---|---|
| `GET /internal/quizzes/{id}` | викторина с вопросами, вариантами и правильными ответами, плюс `owner_id` |

```json
{
  "id": 3,
  "owner_id": 1,
  "title": "Столицы мира",
  "questions": [
    {
      "id": 41,
      "position": 0,
      "text": "Столица Австралии?",
      "time_limit_sec": 20,
      "options": [
        {"id": 17, "position": 0, "text": "Сидней", "is_correct": false},
        {"id": 18, "position": 1, "text": "Канберра", "is_correct": true}
      ]
    }
  ]
}
```
Вопросы и варианты отсортированы по `position`.

Зачем отдельный внутренний API: если бы правильные ответы отдавались через публичную ручку, любой игрок мог бы запросить их во время игры.

### 5.3 Сервис live (`/live/api`)

| Метод и путь | Доступ | Что делает |
|---|---|---|
| `POST /live/api/rooms` | ведущий | `{"quiz_id": 3}` → `201 {"room_code": "482913"}` |
| `GET /live/api/games` | ведущий | история моих игр: `id`, `quiz_title`, `status`, `player_count`, `started_at`, `finished_at` |
| `GET /live/api/games/{id}` | ведущий-владелец | результаты игры: игроки с местами и очками, по каждому вопросу доля правильных ответов |
| `GET /health` | все | проверка для Docker и nginx |

---

## 6. Авторизация

- `content` при входе выдаёт **JWT**, подписанный алгоритмом **HS256** общим секретом `JWT_SECRET`.
- Содержимое токена:
  ```json
  {"sub": "1", "username": "teacher", "iss": "quiz-content", "exp": 1761300000}
  ```
  `sub` — id пользователя строкой (так требует стандарт JWT), срок жизни **12 часов**.
- `live` проверяет подпись тем же `JWT_SECRET`, а ещё `iss` и `exp`. Обращаться к `content` для проверки токена не нужно: в этом смысл JWT.
- Пароли `content` хранит только в виде хэша (`bcrypt` или `argon2`).
- Межсервисные запросы (`live` → `content /internal`) защищены отдельным секретом `INTERNAL_TOKEN` в заголовке `X-Internal-Token`.
- Игроки токенов не имеют: их «авторизация» — знание кода комнаты.

---

## 7. База данных

### 7.1 Принцип: одна БД, у каждого сервиса своя схема

Один сервер PostgreSQL (требование «централизованная БД»), внутри **две схемы**:
- `content` — пишет и читает только сервис `content`;
- `live` — пишет и читает только сервис `live`.

У каждого сервиса **свой пользователь PostgreSQL** с правами только на свою схему. В чужие таблицы сервис физически не может залезть, а данные другого сервиса получает только через его API. Это паттерн *database per service*: сервисы не связаны через структуру таблиц, и каждый может менять свою схему, не ломая другого.

Отсюда же: в схеме `live` нет внешних ключей на таблицы `content`. `quiz_id` и `host_user_id` хранятся просто числами, а название викторины копируется в сессию (`quiz_title`), чтобы история показывалась, даже если викторину потом удалили.

### 7.2 Схема `content`

```sql
CREATE TABLE content.users (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE CHECK (length(username) BETWEEN 3 AND 32),
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE content.quizzes (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_id    BIGINT NOT NULL REFERENCES content.users(id) ON DELETE CASCADE,
    title       TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 100),
    description TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Список «мои викторины» выбирается по owner_id.
CREATE INDEX quizzes_owner_id ON content.quizzes (owner_id);

CREATE TABLE content.questions (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    quiz_id        BIGINT NOT NULL REFERENCES content.quizzes(id) ON DELETE CASCADE,
    position       INT NOT NULL,
    text           TEXT NOT NULL CHECK (length(text) BETWEEN 1 AND 300),
    time_limit_sec INT NOT NULL DEFAULT 20 CHECK (time_limit_sec BETWEEN 5 AND 120),
    UNIQUE (quiz_id, position)
);

CREATE TABLE content.answer_options (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    question_id BIGINT NOT NULL REFERENCES content.questions(id) ON DELETE CASCADE,
    position    INT NOT NULL,
    text        TEXT NOT NULL CHECK (length(text) BETWEEN 1 AND 100),
    is_correct  BOOLEAN NOT NULL DEFAULT false,
    UNIQUE (question_id, position)
);

-- Не больше одного правильного варианта на вопрос.
-- «Хотя бы один» проверяет сервис при сохранении.
CREATE UNIQUE INDEX one_correct_option
    ON content.answer_options (question_id) WHERE is_correct;
```

### 7.3 Схема `live`

```sql
CREATE TABLE live.game_sessions (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_code    CHAR(6) NOT NULL,
    quiz_id      BIGINT NOT NULL,          -- id из content, без внешнего ключа
    quiz_title   TEXT NOT NULL,            -- копия на момент игры
    host_user_id BIGINT NOT NULL,          -- id из content, без внешнего ключа
    status       TEXT NOT NULL DEFAULT 'lobby'
                 CHECK (status IN ('lobby', 'running', 'finished', 'cancelled')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at   TIMESTAMPTZ,
    finished_at  TIMESTAMPTZ
);

-- Код уникален среди активных комнат; после завершения его можно переиспользовать.
CREATE UNIQUE INDEX active_room_code
    ON live.game_sessions (room_code) WHERE status IN ('lobby', 'running');

CREATE TABLE live.session_players (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id  BIGINT NOT NULL REFERENCES live.game_sessions(id) ON DELETE CASCADE,
    nickname    TEXT NOT NULL,
    joined_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    left_at     TIMESTAMPTZ,               -- выбыл во время игры
    final_score INT,
    final_rank  INT
);

CREATE UNIQUE INDEX unique_nickname_in_session
    ON live.session_players (session_id, lower(nickname));

CREATE TABLE live.player_answers (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id     BIGINT NOT NULL REFERENCES live.game_sessions(id) ON DELETE CASCADE,
    player_id      BIGINT NOT NULL REFERENCES live.session_players(id) ON DELETE CASCADE,
    question_index INT NOT NULL,
    question_id    BIGINT NOT NULL,        -- id из content
    option_id      BIGINT,                 -- NULL — не успел ответить
    is_correct     BOOLEAN NOT NULL,
    response_ms    INT,
    points         INT NOT NULL,
    UNIQUE (player_id, question_index)
);
```

Ответы игроков `live` записывает **одной транзакцией в конце каждого вопроса**, а не по одному: в момент вопроса это десятки одновременных ответов, и пакетная запись снижает нагрузку на БД.

### 7.4 Миграции

- Один инструмент на всех: **golang-migrate**, запускается отдельным контейнером в `docker-compose` до старта сервисов.
- Файлы лежат в `deploy/migrations/`, имена с номером: `0001_content_init.up.sql`, `0002_live_init.up.sql` (и парные `.down.sql`).
- Каждый пишет миграции **только для своей схемы**. Новые изменения добавляются новым файлом, старые файлы не правятся.
- Схемы и пользователей PostgreSQL создаёт скрипт `deploy/postgres/init.sh` при первом запуске контейнера БД (пароли из переменных окружения).

---

## 8. Инфраструктура

### 8.1 Репозиторий

```
micro/
├── content/          ← сервис content (друг)
├── live/             ← сервис live (сюда переезжает нынешний scoreboard/)
├── desktop/          ← приложение PySide6
├── deploy/
│   ├── docker-compose.yml
│   ├── nginx/nginx.conf
│   ├── postgres/init.sh
│   └── migrations/
├── docs/
├── .gitattributes
└── .gitignore
```

### 8.2 nginx

- Наружу открыт **только nginx**. Приложению нужен один адрес, например `http://localhost:8000`.
- `/api/` → `content`, обычная балансировка по кругу (round robin).
- `/live/api/` → `live`, по кругу. Эти ручки не хранят состояние, им всё равно, какой инстанс ответит.
- `/live/ws` → `live` с **`hash $arg_room consistent`**: все подключения с одним кодом комнаты попадают **на один и тот же инстанс**.
- `/internal/` наружу **не проксируется**.

Почему нужен hash. Комната хранится в памяти того инстанса, где её открыл ведущий. Если игрок попадёт на другой инстанс, комнаты там не будет. Хэш от кода комнаты гарантирует, что ведущий и все игроки одной комнаты окажутся на одном инстансе, а разные комнаты распределятся по разным инстансам. `consistent` означает, что при добавлении или удалении инстанса переедет только небольшая часть комнат, а не все.

Цена решения: если инстанс упал, его комнаты прерываются. По правилам игры это допустимо: игроки просто выбывают.

Для WebSocket в nginx также нужны `proxy_http_version 1.1`, заголовки `Upgrade` и `Connection` и `proxy_read_timeout` больше интервала ping (54 с).

### 8.3 Переменные окружения

| Переменная | content | live | Пример |
|---|---|---|---|
| `PORT` | ✓ | ✓ | `8000` / `8080` |
| `DATABASE_URL` | ✓ | ✓ | `postgres://live_user:...@postgres:5432/quiz` (у каждого свой пользователь) |
| `JWT_SECRET` | ✓ | ✓ | одинаковый у обоих |
| `INTERNAL_TOKEN` | ✓ | ✓ | одинаковый у обоих |
| `CONTENT_URL` | | ✓ | `http://content:8000` |

Секреты хранятся в файле `deploy/.env`, который **не коммитится**. В репозитории лежит `deploy/.env.example` с образцом.

### 8.4 Порты внутри Docker-сети

| Сервис | Порт | Наружу |
|---|---|---|
| nginx | 80 | `8000` на хосте |
| content | 8000 | нет |
| live | 8080 | нет |
| postgres | 5432 | нет (для отладки можно временно открыть) |

---

## 9. Соглашения

- JSON: имена полей в `snake_case`.
- Время: UTC, формат RFC 3339 (`2026-10-23T12:00:00Z`).
- Ошибки REST: `{"error": "текст"}` и подходящий код (400, 401, 403, 404, 409, 422).
- id в JSON — числа.
- Концы строк: `LF` во всём репозитории (`.gitattributes`: `* text=auto eol=lf`), потому что друг на Windows, а сервисы работают в Linux-контейнерах.
- Git: оба участника коммитят и пушат сразу в `main`, без отдельных веток и pull request. Перед пушем забираем чужие изменения через `git pull --rebase`, чтобы история оставалась прямой и без лишних merge-коммитов.

---

## 10. Кто что делает

| Часть | Владелец |
|---|---|
| Сервис `content`, его Dockerfile, миграции схемы `content` | друг |
| Сервис `live`, его Dockerfile, миграции схемы `live` | я |
| `docker-compose`, nginx, `init.sh`, `.gitattributes`, CI | я |
| Каркас десктопного приложения (окно, навигация, настройки адреса сервера), экраны входа, викторин, редактора, истории | друг |
| Экраны игры в приложении: лобби ведущего, вход игрока, вопрос с таймером, результаты | я |
| Сборка `.exe` | друг (Windows) |
| Отчёт | каждый про свой сервис, общие разделы вместе, оформление по ГОСТ в конце один человек |
