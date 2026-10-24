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
