package session

// Типы для истории игр: что ведущий видит после игры.

// GameSummary — строка списка «мои игры».
type GameSummary struct {
	Session
	PlayerCount int
}

// GameDetails — результаты одной игры.
type GameDetails struct {
	Session
	Players   []PlayerResult // по месту, без итогов — в порядке входа
	Questions []QuestionStats
}

type PlayerResult struct {
	PlayerID int64
	Nickname string
	Score    *int // nil — игра не дошла до итогов
	Rank     *int
	Left     bool
}

// QuestionStats — сколько игроков было на вопросе, сколько ответили и
// сколько верно. Текста вопроса здесь нет: он хранится в content, а live
// знает только его номер и id.
type QuestionStats struct {
	QuestionIndex int
	QuestionID    int64
	Total         int
	Answered      int
	Correct       int
}
