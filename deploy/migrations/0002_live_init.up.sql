-- Схема live: игровые сессии, игроки, ответы.
-- Саму схему и пользователя live_user создаёт deploy/postgres/init.sh.
-- Описание таблиц — docs/quiz-design.md, раздел 7.3.
--
-- Внешних ключей на таблицы content нет специально (database per service):
-- quiz_id и host_user_id — просто числа, а название викторины копируется.

CREATE TABLE live.game_sessions (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_code    CHAR(6) NOT NULL,
    quiz_id      BIGINT NOT NULL,
    quiz_title   TEXT NOT NULL,
    host_user_id BIGINT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'lobby'
                 CHECK (status IN ('lobby', 'running', 'finished', 'cancelled')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at   TIMESTAMPTZ,
    finished_at  TIMESTAMPTZ
);

-- Код уникален среди активных комнат; после завершения его можно переиспользовать.
CREATE UNIQUE INDEX active_room_code
    ON live.game_sessions (room_code) WHERE status IN ('lobby', 'running');

-- История «мои игры» выбирается по ведущему, новые сверху.
CREATE INDEX game_sessions_host ON live.game_sessions (host_user_id, created_at DESC);

CREATE TABLE live.session_players (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id  BIGINT NOT NULL REFERENCES live.game_sessions(id) ON DELETE CASCADE,
    nickname    TEXT NOT NULL,
    joined_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    left_at     TIMESTAMPTZ,
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
    question_id    BIGINT NOT NULL,
    option_id      BIGINT,
    is_correct     BOOLEAN NOT NULL,
    response_ms    INT,
    points         INT NOT NULL,
    UNIQUE (player_id, question_index)
);
