-- Обратный порядок: сначала таблицы, которые ссылаются на другие.
-- Индексы удаляются вместе со своими таблицами.
DROP TABLE IF EXISTS live.player_answers;
DROP TABLE IF EXISTS live.session_players;
DROP TABLE IF EXISTS live.game_sessions;
