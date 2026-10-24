-- Схема content: аккаунты ведущих, викторины, вопросы, варианты ответов.
-- Саму схему и пользователя content_user создаёт deploy/postgres/init.sh.
-- Описание таблиц — docs/quiz-design.md, раздел 7.2.

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
