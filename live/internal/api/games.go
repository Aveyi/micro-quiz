package api

import (
	"errors"
	"log/slog"
	"net/http"
	"strconv"
	"time"

	"github.com/Aveyi/micro-quiz/live/internal/auth"
	"github.com/Aveyi/micro-quiz/live/internal/session"
)

// historyLimit — сколько последних игр отдаём в списке. Постраничный
// вывод для учебного проекта не нужен, но без предела ответ рос бы вечно.
const historyLimit = 100

type Games struct {
	Auth  *auth.Verifier
	Store session.Store
	Log   *slog.Logger
}

// Ответы — отдельные структуры с JSON-тегами, а не типы хранилища:
// формат API — это контракт, и он не должен меняться от того, что мы
// переименовали поле в Go или колонку в БД.

type gameSummary struct {
	ID          int64      `json:"id"`
	QuizID      int64      `json:"quiz_id"`
	QuizTitle   string     `json:"quiz_title"`
	Status      string     `json:"status"`
	PlayerCount int        `json:"player_count"`
	CreatedAt   time.Time  `json:"created_at"`
	StartedAt   *time.Time `json:"started_at"`  // null — игра не начиналась
	FinishedAt  *time.Time `json:"finished_at"` // null — ещё идёт
}

type playerResult struct {
	PlayerID int64  `json:"player_id"`
	Nickname string `json:"nickname"`
	Score    *int   `json:"score"` // null — игра не дошла до итогов
	Rank     *int   `json:"rank"`
	Left     bool   `json:"left"`
}

type questionStats struct {
	QuestionIndex int     `json:"question_index"`
	QuestionID    int64   `json:"question_id"`
	Total         int     `json:"total"`
	Answered      int     `json:"answered"`
	Correct       int     `json:"correct"`
	CorrectRatio  float64 `json:"correct_ratio"`
}

type gameDetails struct {
	gameSummary
	Players   []playerResult  `json:"players"`
	Questions []questionStats `json:"questions"`
}

func summaryJSON(s session.Session, playerCount int) gameSummary {
	return gameSummary{
		ID:          s.ID,
		QuizID:      s.QuizID,
		QuizTitle:   s.QuizTitle,
		Status:      string(s.Status),
		PlayerCount: playerCount,
		CreatedAt:   s.CreatedAt.UTC(),
		StartedAt:   utc(s.StartedAt),
		FinishedAt:  utc(s.FinishedAt),
	}
}

// utc приводит время к UTC: по соглашениям (раздел 9) время в API — UTC.
func utc(t *time.Time) *time.Time {
	if t == nil {
		return nil
	}
	u := t.UTC()
	return &u
}

// List — GET /live/api/games: мои игры, новые сверху.
func (h *Games) List(w http.ResponseWriter, r *http.Request) {
	host, err := h.Auth.FromRequest(r)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "нужен действительный токен ведущего")
		return
	}
	games, err := h.Store.ListGames(r.Context(), host.UserID, historyLimit)
	if err != nil {
		h.Log.Error("список игр", "host", host.UserID, "err", err)
		writeError(w, http.StatusInternalServerError, "внутренняя ошибка")
		return
	}
	out := make([]gameSummary, 0, len(games)) // [] а не null, если игр нет
	for _, g := range games {
		out = append(out, summaryJSON(g.Session, g.PlayerCount))
	}
	writeJSON(w, http.StatusOK, out)
}

// Get — GET /live/api/games/{id}: результаты одной моей игры.
func (h *Games) Get(w http.ResponseWriter, r *http.Request) {
	host, err := h.Auth.FromRequest(r)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "нужен действительный токен ведущего")
		return
	}
	id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil || id <= 0 {
		writeError(w, http.StatusNotFound, "игра не найдена")
		return
	}

	g, err := h.Store.GetGame(r.Context(), id)
	// Чужая игра — тоже 404, а не 403: иначе по ответам можно было бы
	// перебором узнать, какие id игр существуют.
	if errors.Is(err, session.ErrNotFound) || (err == nil && g.HostUserID != host.UserID) {
		writeError(w, http.StatusNotFound, "игра не найдена")
		return
	}
	if err != nil {
		h.Log.Error("результаты игры", "id", id, "err", err)
		writeError(w, http.StatusInternalServerError, "внутренняя ошибка")
		return
	}

	out := gameDetails{
		gameSummary: summaryJSON(g.Session, len(g.Players)),
		Players:     make([]playerResult, 0, len(g.Players)),
		Questions:   make([]questionStats, 0, len(g.Questions)),
	}
	for _, p := range g.Players {
		out.Players = append(out.Players, playerResult{
			PlayerID: p.PlayerID, Nickname: p.Nickname, Score: p.Score, Rank: p.Rank, Left: p.Left,
		})
	}
	for _, q := range g.Questions {
		ratio := 0.0
		if q.Total > 0 {
			ratio = float64(q.Correct) / float64(q.Total)
		}
		out.Questions = append(out.Questions, questionStats{
			QuestionIndex: q.QuestionIndex, QuestionID: q.QuestionID,
			Total: q.Total, Answered: q.Answered, Correct: q.Correct, CorrectRatio: ratio,
		})
	}
	writeJSON(w, http.StatusOK, out)
}
