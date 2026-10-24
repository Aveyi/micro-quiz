// content-stub — заглушка сервиса content для разработки и тестов live,
// пока настоящий content не готов. Отдаёт GET /internal/quizzes/{id}
// из файла quizzes.json ровно в формате docs/quiz-design.md, раздел 5.2.
//
// Запуск: INTERNAL_TOKEN=... PORT=8000 go run ./cmd/content-stub
package main

import (
	"crypto/subtle"
	_ "embed"
	"encoding/json"
	"log/slog"
	"net/http"
	"os"
)

// Файл вшивается в бинарник при сборке, поэтому заглушка не зависит
// от текущей папки при запуске.
//
//go:embed quizzes.json
var quizzesJSON []byte

func main() {
	log := slog.New(slog.NewTextHandler(os.Stdout, nil))

	token := os.Getenv("INTERNAL_TOKEN")
	if token == "" {
		log.Error("INTERNAL_TOKEN не задан")
		os.Exit(1)
	}
	port := os.Getenv("PORT")
	if port == "" {
		port = "8000"
	}

	quizzes, err := loadQuizzes()
	if err != nil {
		log.Error("quizzes.json", "err", err)
		os.Exit(1)
	}

	mux := http.NewServeMux()
	mux.HandleFunc("GET /internal/quizzes/{id}", func(w http.ResponseWriter, r *http.Request) {
		// Сравнение за постоянное время: обычное == выходит на первом
		// несовпавшем байте, и по времени ответа можно подбирать токен.
		if subtle.ConstantTimeCompare([]byte(r.Header.Get("X-Internal-Token")), []byte(token)) != 1 {
			writeError(w, http.StatusUnauthorized, "неверный X-Internal-Token")
			return
		}
		q, ok := quizzes[r.PathValue("id")]
		if !ok {
			writeError(w, http.StatusNotFound, "викторина не найдена")
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.Write(q)
	})

	log.Info("content-stub запущен", "port", port, "quizzes", len(quizzes))
	if err := http.ListenAndServe(":"+port, logRequests(log, mux)); err != nil {
		log.Error("сервер", "err", err)
		os.Exit(1)
	}
}

// loadQuizzes раскладывает викторины по id. Каждая хранится как есть
// (json.RawMessage), чтобы заглушка отдавала ровно то, что лежит в файле.
func loadQuizzes() (map[string]json.RawMessage, error) {
	var list []json.RawMessage
	if err := json.Unmarshal(quizzesJSON, &list); err != nil {
		return nil, err
	}
	byID := make(map[string]json.RawMessage, len(list))
	for _, raw := range list {
		var head struct {
			ID json.Number `json:"id"`
		}
		if err := json.Unmarshal(raw, &head); err != nil {
			return nil, err
		}
		byID[head.ID.String()] = raw
	}
	return byID, nil
}

func writeError(w http.ResponseWriter, status int, msg string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(map[string]string{"error": msg})
}

// logRequests пишет в лог каждый запрос — видно, когда live обращается к content.
func logRequests(log *slog.Logger, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		log.Info("запрос", "method", r.Method, "path", r.URL.Path)
		next.ServeHTTP(w, r)
	})
}
