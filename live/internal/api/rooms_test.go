package api

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"regexp"
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"

	"github.com/Aveyi/micro-quiz/live/internal/auth"
	"github.com/Aveyi/micro-quiz/live/internal/content"
	"github.com/Aveyi/micro-quiz/live/internal/session"
)

var secret = []byte("test-secret-test-secret-test-sec")

// fakeQuizzes — подделка content: викторины по id или заданная ошибка.
type fakeQuizzes struct {
	quizzes map[int64]content.Quiz
	err     error
}

func (f fakeQuizzes) GetQuiz(_ context.Context, id int64) (content.Quiz, error) {
	if f.err != nil {
		return content.Quiz{}, f.err
	}
	q, ok := f.quizzes[id]
	if !ok {
		return content.Quiz{}, content.ErrQuizNotFound
	}
	return q, nil
}

func tokenFor(t *testing.T, userID string) string {
	t.Helper()
	s, err := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"sub": userID, "username": "teacher", "iss": "quiz-content",
		"exp": time.Now().Add(time.Hour).Unix(),
	}).SignedString(secret)
	if err != nil {
		t.Fatal(err)
	}
	return s
}

func newRooms(quizzes QuizSource) (*Rooms, *session.MemoryStore) {
	store := session.NewMemoryStore()
	return &Rooms{
		Auth:    auth.NewVerifier(secret),
		Quizzes: quizzes,
		Store:   store,
		Log:     slog.New(slog.NewTextHandler(io.Discard, nil)),
		NewCode: session.NewCode,
	}, store
}

var defaultQuizzes = fakeQuizzes{quizzes: map[int64]content.Quiz{
	3: {ID: 3, OwnerID: 1, Title: "Столицы мира"},
	4: {ID: 4, OwnerID: 2, Title: "Чужая"},
}}

// post отправляет POST /live/api/rooms и возвращает код ответа и тело.
func post(t *testing.T, h *Rooms, token, body string) (int, map[string]string) {
	t.Helper()
	r := httptest.NewRequest("POST", "/live/api/rooms", strings.NewReader(body))
	if token != "" {
		r.Header.Set("Authorization", "Bearer "+token)
	}
	w := httptest.NewRecorder()
	h.Create(w, r)

	var resp map[string]string
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("ответ не JSON: %q", w.Body.String())
	}
	return w.Code, resp
}

func TestCreateRoom(t *testing.T) {
	h, store := newRooms(defaultQuizzes)

	code, resp := post(t, h, tokenFor(t, "1"), `{"quiz_id": 3}`)
	if code != http.StatusCreated {
		t.Fatalf("код %d, тело %v", code, resp)
	}
	if !regexp.MustCompile(`^\d{6}$`).MatchString(resp["room_code"]) {
		t.Fatalf("room_code = %q, ожидали 6 цифр", resp["room_code"])
	}

	s, err := store.GetActive(context.Background(), resp["room_code"])
	if err != nil {
		t.Fatal(err)
	}
	if s.QuizID != 3 || s.QuizTitle != "Столицы мира" || s.HostUserID != 1 || s.Status != session.StatusLobby {
		t.Fatalf("сессия %+v", s)
	}
}

func TestCreateRoomErrors(t *testing.T) {
	tests := []struct {
		name    string
		quizzes QuizSource
		token   string
		body    string
		want    int
	}{
		{"нет токена", defaultQuizzes, "", `{"quiz_id": 3}`, 401},
		{"плохой токен", defaultQuizzes, "garbage", `{"quiz_id": 3}`, 401},
		{"не JSON", defaultQuizzes, "1", `quiz_id=3`, 400},
		{"quiz_id не число", defaultQuizzes, "1", `{"quiz_id": "3"}`, 400},
		{"нет quiz_id", defaultQuizzes, "1", `{}`, 422},
		{"quiz_id отрицательный", defaultQuizzes, "1", `{"quiz_id": -1}`, 422},
		{"нет викторины", defaultQuizzes, "1", `{"quiz_id": 99}`, 404},
		{"чужая викторина", defaultQuizzes, "1", `{"quiz_id": 4}`, 403},
		{"пустая викторина", fakeQuizzes{err: content.ErrInvalidQuiz}, "1", `{"quiz_id": 3}`, 422},
		{"content лежит", fakeQuizzes{err: errors.New("connection refused")}, "1", `{"quiz_id": 3}`, 502},
		{"огромное тело", defaultQuizzes, "1", `{"quiz_id": 3, "x": "` + strings.Repeat("a", 2000) + `"}`, 400},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			h, _ := newRooms(tt.quizzes)
			token := tt.token
			if token == "1" {
				token = tokenFor(t, "1")
			}
			code, resp := post(t, h, token, tt.body)
			if code != tt.want {
				t.Fatalf("код %d, ожидали %d (тело %v)", code, tt.want, resp)
			}
			if resp["error"] == "" {
				t.Fatalf("нет поля error: %v", resp)
			}
		})
	}
}

func TestCreateRoomRetriesTakenCode(t *testing.T) {
	h, store := newRooms(defaultQuizzes)

	// Комната с кодом 111111 уже есть; генератор сначала выдаёт его же.
	if _, err := store.Create(context.Background(), session.Session{RoomCode: "111111"}); err != nil {
		t.Fatal(err)
	}
	codes := []string{"111111", "222222"}
	h.NewCode = func() string { c := codes[0]; codes = codes[1:]; return c }

	code, resp := post(t, h, tokenFor(t, "1"), `{"quiz_id": 3}`)
	if code != http.StatusCreated || resp["room_code"] != "222222" {
		t.Fatalf("код %d, тело %v; ожидали 201 и 222222", code, resp)
	}
}

func TestCreateRoomGivesUpAfterAttempts(t *testing.T) {
	h, store := newRooms(defaultQuizzes)
	store.Create(context.Background(), session.Session{RoomCode: "111111"})
	h.NewCode = func() string { return "111111" } // всегда занятый

	if code, _ := post(t, h, tokenFor(t, "1"), `{"quiz_id": 3}`); code != http.StatusServiceUnavailable {
		t.Fatalf("код %d, ожидали 503", code)
	}
}
