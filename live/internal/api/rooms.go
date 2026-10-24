package api

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"

	"github.com/Aveyi/micro-quiz/live/internal/auth"
	"github.com/Aveyi/micro-quiz/live/internal/content"
	"github.com/Aveyi/micro-quiz/live/internal/session"
)

// codeAttempts — сколько раз пробуем новый код, если он занят. При 10^6
// кодах и десятках активных комнат совпадение почти невозможно, но
// бесконечный цикл ставить нельзя.
const codeAttempts = 10

// QuizSource — откуда брать викторины. В работе это *content.Client,
// в тестах — подделка, чтобы не поднимать HTTP-сервер.
type QuizSource interface {
	GetQuiz(ctx context.Context, id int64) (content.Quiz, error)
}

type Rooms struct {
	Auth    *auth.Verifier
	Quizzes QuizSource
	Store   session.Store
	Log     *slog.Logger
	// NewCode генерирует код комнаты; в тестах подменяется, чтобы
	// проверить повтор при занятом коде.
	NewCode func() string
}

type createRoomRequest struct {
	QuizID int64 `json:"quiz_id"`
}

type createRoomResponse struct {
	RoomCode string `json:"room_code"`
}

// Create — POST /live/api/rooms: ведущий открывает комнату для своей викторины.
func (h *Rooms) Create(w http.ResponseWriter, r *http.Request) {
	host, err := h.Auth.FromRequest(r)
	if err != nil {
		// И «нет токена», и «плохой токен» здесь 401: ручка только для ведущего.
		writeError(w, http.StatusUnauthorized, "нужен действительный токен ведущего")
		return
	}

	// Ограничиваем тело: настоящий запрос — десяток байт.
	r.Body = http.MaxBytesReader(w, r.Body, 1024)
	var req createRoomRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "тело должно быть JSON вида {\"quiz_id\": 3}")
		return
	}
	if req.QuizID <= 0 {
		writeError(w, http.StatusUnprocessableEntity, "quiz_id должен быть положительным числом")
		return
	}

	quiz, err := h.Quizzes.GetQuiz(r.Context(), req.QuizID)
	switch {
	case errors.Is(err, content.ErrQuizNotFound):
		writeError(w, http.StatusNotFound, "викторина не найдена")
		return
	case errors.Is(err, content.ErrInvalidQuiz):
		// Текст ошибки объясняет причину («в викторине нет вопросов»).
		writeError(w, http.StatusUnprocessableEntity, err.Error())
		return
	case err != nil:
		// content недоступен или ответил странно. Ведущий не виноват:
		// 502 Bad Gateway — «сервер, к которому я обратился, подвёл».
		h.Log.Error("загрузка викторины", "quiz_id", req.QuizID, "err", err)
		writeError(w, http.StatusBadGateway, "сервис викторин недоступен")
		return
	}
	if quiz.OwnerID != host.UserID {
		writeError(w, http.StatusForbidden, "викторина принадлежит другому пользователю")
		return
	}

	for range codeAttempts {
		s, err := h.Store.Create(r.Context(), session.Session{
			RoomCode:   h.NewCode(),
			QuizID:     quiz.ID,
			QuizTitle:  quiz.Title,
			HostUserID: host.UserID,
		})
		if errors.Is(err, session.ErrCodeTaken) {
			continue
		}
		if err != nil {
			h.Log.Error("создание сессии", "err", err)
			writeError(w, http.StatusInternalServerError, "не удалось создать комнату")
			return
		}
		h.Log.Info("комната создана", "room", s.RoomCode, "session_id", s.ID, "quiz_id", quiz.ID, "host", host.UserID)
		writeJSON(w, http.StatusCreated, createRoomResponse{RoomCode: s.RoomCode})
		return
	}
	h.Log.Error("не нашли свободный код комнаты", "attempts", codeAttempts)
	writeError(w, http.StatusServiceUnavailable, "не удалось подобрать код комнаты, повторите")
}
