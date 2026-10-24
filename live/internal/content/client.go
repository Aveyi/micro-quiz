package content

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"time"
)

// ErrQuizNotFound — content ответил 404: викторины с таким id нет.
var ErrQuizNotFound = errors.New("викторина не найдена")

// requestTimeout — сколько ждём content. Без таймаута зависший content
// держал бы запрос ведущего «создать комнату» бесконечно.
const requestTimeout = 5 * time.Second

// maxBody — предел размера ответа: 50 вопросов по 4 варианта весят
// десятки килобайт, а 1 МБ защищает от бесконечного ответа.
const maxBody = 1 << 20

type Client struct {
	baseURL string
	token   string
	http    *http.Client
}

func NewClient(baseURL, internalToken string) *Client {
	return &Client{
		baseURL: baseURL,
		token:   internalToken,
		http:    &http.Client{Timeout: requestTimeout},
	}
}

// GetQuiz загружает викторину с правильными ответами и проверяет её.
func (c *Client) GetQuiz(ctx context.Context, id int64) (Quiz, error) {
	url := c.baseURL + "/internal/quizzes/" + strconv.FormatInt(id, 10)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return Quiz{}, err
	}
	req.Header.Set("X-Internal-Token", c.token)
	req.Header.Set("Accept", "application/json")

	resp, err := c.http.Do(req)
	if err != nil {
		return Quiz{}, fmt.Errorf("запрос к content: %w", err)
	}
	// Тело нужно закрывать всегда, иначе соединение не вернётся в пул.
	defer resp.Body.Close()

	switch resp.StatusCode {
	case http.StatusOK:
	case http.StatusNotFound:
		return Quiz{}, ErrQuizNotFound
	default:
		// Другие коды (401 — не совпал INTERNAL_TOKEN, 5xx — content сломан)
		// — это не вина ведущего, а проблема настройки или сервиса.
		return Quiz{}, fmt.Errorf("content ответил %d", resp.StatusCode)
	}

	var q Quiz
	if err := json.NewDecoder(io.LimitReader(resp.Body, maxBody)).Decode(&q); err != nil {
		return Quiz{}, fmt.Errorf("разбор ответа content: %w", err)
	}
	if q.ID != id {
		return Quiz{}, fmt.Errorf("content вернул викторину %d вместо %d", q.ID, id)
	}
	if err := q.Validate(); err != nil {
		return Quiz{}, err
	}
	return q, nil
}
