package content

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

const token = "test-internal-token"

func validQuiz() Quiz {
	return Quiz{
		ID: 3, OwnerID: 1, Title: "Столицы мира",
		Questions: []Question{{
			ID: 41, Position: 0, Text: "Столица Австралии?", TimeLimitSec: 20,
			Options: []Option{
				{ID: 17, Position: 0, Text: "Сидней"},
				{ID: 18, Position: 1, Text: "Канберра", IsCorrect: true},
			},
		}},
	}
}

// fakeContent поднимает HTTP-сервер, который ведёт себя как content:
// handler решает, что ответить.
func fakeContent(t *testing.T, handler http.HandlerFunc) *Client {
	t.Helper()
	srv := httptest.NewServer(handler)
	t.Cleanup(srv.Close)
	return NewClient(srv.URL, token)
}

func respondJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(v)
}

func TestGetQuizOK(t *testing.T) {
	c := fakeContent(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/internal/quizzes/3" {
			t.Errorf("путь %q", r.URL.Path)
		}
		if got := r.Header.Get("X-Internal-Token"); got != token {
			t.Errorf("X-Internal-Token = %q", got)
		}
		respondJSON(w, validQuiz())
	})

	q, err := c.GetQuiz(context.Background(), 3)
	if err != nil {
		t.Fatal(err)
	}
	if q.Title != "Столицы мира" || q.OwnerID != 1 || len(q.Questions) != 1 {
		t.Fatalf("q = %+v", q)
	}
	if got := q.Questions[0].CorrectOptionID(); got != 18 {
		t.Fatalf("CorrectOptionID = %d, ожидали 18", got)
	}
}

func TestGetQuizErrors(t *testing.T) {
	tests := []struct {
		name    string
		handler http.HandlerFunc
		want    error // nil — любая ошибка, но не из списка ниже
	}{
		{"404", func(w http.ResponseWriter, r *http.Request) {
			http.Error(w, `{"error":"not found"}`, http.StatusNotFound)
		}, ErrQuizNotFound},
		{"401 неверный токен", func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusUnauthorized)
		}, nil},
		{"500", func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusInternalServerError)
		}, nil},
		{"не JSON", func(w http.ResponseWriter, r *http.Request) {
			w.Write([]byte("<html>oops</html>"))
		}, nil},
		{"чужой id", func(w http.ResponseWriter, r *http.Request) {
			q := validQuiz()
			q.ID = 4
			respondJSON(w, q)
		}, nil},
		{"кривая викторина", func(w http.ResponseWriter, r *http.Request) {
			q := validQuiz()
			q.Questions = nil
			respondJSON(w, q)
		}, ErrInvalidQuiz},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := fakeContent(t, tt.handler).GetQuiz(context.Background(), 3)
			if err == nil {
				t.Fatal("ожидали ошибку")
			}
			if tt.want != nil && !errors.Is(err, tt.want) {
				t.Fatalf("ожидали %v, получили %v", tt.want, err)
			}
			// 401 и 500 не должны выглядеть для ведущего как «викторины нет».
			if tt.want == nil && errors.Is(err, ErrQuizNotFound) {
				t.Fatalf("%v не должно быть ErrQuizNotFound", err)
			}
		})
	}
}

func TestGetQuizContextTimeout(t *testing.T) {
	c := fakeContent(t, func(w http.ResponseWriter, r *http.Request) {
		<-r.Context().Done() // content «завис»
	})
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()

	start := time.Now()
	_, err := c.GetQuiz(ctx, 3)
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("ожидали DeadlineExceeded, получили %v", err)
	}
	if time.Since(start) > time.Second {
		t.Fatal("клиент не прервал запрос по контексту")
	}
}

func TestValidate(t *testing.T) {
	tests := []struct {
		name  string
		spoil func(q *Quiz)
	}{
		{"нет вопросов", func(q *Quiz) { q.Questions = nil }},
		{"таймер 3 с", func(q *Quiz) { q.Questions[0].TimeLimitSec = 3 }},
		{"таймер 121 с", func(q *Quiz) { q.Questions[0].TimeLimitSec = 121 }},
		{"один вариант", func(q *Quiz) { q.Questions[0].Options = q.Questions[0].Options[:1] }},
		{"пять вариантов", func(q *Quiz) {
			o := q.Questions[0].Options
			q.Questions[0].Options = append(o, Option{ID: 19}, Option{ID: 20}, Option{ID: 21})
		}},
		{"нет правильного", func(q *Quiz) { q.Questions[0].Options[1].IsCorrect = false }},
		{"два правильных", func(q *Quiz) { q.Questions[0].Options[0].IsCorrect = true }},
		{"повтор option_id", func(q *Quiz) { q.Questions[0].Options[1].ID = 17 }},
	}

	if err := validQuiz().Validate(); err != nil {
		t.Fatalf("правильная викторина не прошла: %v", err)
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			q := validQuiz()
			tt.spoil(&q)
			if err := q.Validate(); !errors.Is(err, ErrInvalidQuiz) {
				t.Fatalf("ожидали ErrInvalidQuiz, получили %v", err)
			}
		})
	}
}
