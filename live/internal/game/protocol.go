// Package game — комнаты и проведение игры поверх WebSocket.
// Протокол — docs/quiz-design.md, раздел 4.
package game

import (
	"encoding/json"
	"fmt"
)

// envelope — входящее сообщение {"type": ..., "data": {...}}. data оставляем
// сырым: как его разбирать, зависит от type.
type envelope struct {
	Type string          `json:"type"`
	Data json.RawMessage `json:"data"`
}

// encode собирает исходящее сообщение. Сериализуем один раз и рассылаем
// одни и те же байты всем, а не кодируем JSON для каждого клиента.
func encode(typ string, data any) []byte {
	if data == nil {
		data = struct{}{} // по протоколу data есть всегда, хотя бы {}
	}
	b, err := json.Marshal(struct {
		Type string `json:"type"`
		Data any    `json:"data"`
	}{typ, data})
	if err != nil {
		// Сюда попадают только наши собственные структуры: ошибка — баг в коде.
		panic(fmt.Sprintf("encode %s: %v", typ, err))
	}
	return b
}

type playerInfo struct {
	PlayerID int64  `json:"player_id"`
	Nickname string `json:"nickname"`
}

type joinedData struct {
	Role          Role         `json:"role"`
	PlayerID      int64        `json:"player_id,omitempty"` // у ведущего нет
	RoomCode      string       `json:"room_code"`
	QuizTitle     string       `json:"quiz_title"`
	QuestionCount int          `json:"question_count"`
	Players       []playerInfo `json:"players"`
}

type roomClosedData struct {
	Reason string `json:"reason"`
}

type errorData struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

func errorMsg(code, message string) []byte {
	return encode("error", errorData{Code: code, Message: message})
}

// Сообщения игры (шаг 5).

type answerData struct {
	// Указатель, чтобы отличить «нет поля» от вопроса номер 0.
	QuestionIndex *int  `json:"question_index"`
	OptionID      int64 `json:"option_id"`
}

type optionData struct {
	OptionID int64  `json:"option_id"`
	Text     string `json:"text"`
}

// questionData — без правильного ответа: он уходит только в question_result.
type questionData struct {
	QuestionIndex int          `json:"question_index"`
	QuestionCount int          `json:"question_count"`
	Text          string       `json:"text"`
	Options       []optionData `json:"options"`
	TimeLimitSec  int          `json:"time_limit_sec"`
}

type answerAcceptedData struct {
	QuestionIndex int `json:"question_index"`
}

type answerProgressData struct {
	Answered int `json:"answered"`
	Total    int `json:"total"`
}

type leaderEntry struct {
	Rank     int    `json:"rank"`
	PlayerID int64  `json:"player_id"`
	Nickname string `json:"nickname"`
	Score    int    `json:"score"`
	// Left — игрок выбыл во время игры. Бывает только в game_over;
	// у оставшихся поля нет (omitempty убирает false).
	Left bool `json:"left,omitempty"`
}

type questionYou struct {
	Correct bool `json:"correct"`
	Points  int  `json:"points"`
	Score   int  `json:"score"`
	Rank    int  `json:"rank"`
}

// questionResultData: You есть только у игроков, OptionCounts — только у
// ведущего. omitempty у указателя и map убирает поле, если оно nil.
type questionResultData struct {
	QuestionIndex   int            `json:"question_index"`
	CorrectOptionID int64          `json:"correct_option_id"`
	Leaderboard     []leaderEntry  `json:"leaderboard"`
	You             *questionYou   `json:"you,omitempty"`
	OptionCounts    map[string]int `json:"option_counts,omitempty"`
}

type playerLeftData struct {
	PlayerID int64  `json:"player_id"`
	Nickname string `json:"nickname"`
}

type gameOverYou struct {
	Score int `json:"score"`
	Rank  int `json:"rank"`
}

type gameOverData struct {
	Leaderboard []leaderEntry `json:"leaderboard"`
	You         *gameOverYou  `json:"you,omitempty"`
}
