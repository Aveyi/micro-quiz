-- Обратный порядок: сначала таблицы, которые ссылаются на другие.
-- Индексы удаляются вместе со своими таблицами.
DROP TABLE IF EXISTS content.answer_options;
DROP TABLE IF EXISTS content.questions;
DROP TABLE IF EXISTS content.quizzes;
DROP TABLE IF EXISTS content.users;
