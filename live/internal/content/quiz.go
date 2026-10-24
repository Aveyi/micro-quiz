// Package content — клиент к внутреннему API сервиса content.
// Формат ответа — docs/quiz-design.md, раздел 5.2.
package content

import (
	"errors"
	"fmt"
)

// ErrInvalidQuiz — викторину нельзя провести: в ней нет вопросов
// или нарушены правила (раздел 2 дизайна).
var ErrInvalidQuiz = errors.New("викторину нельзя провести")

type Quiz struct {
	ID        int64      `json:"id"`
	OwnerID   int64      `json:"owner_id"`
	Title     string     `json:"title"`
	Questions []Question `json:"questions"`
}

type Question struct {
	ID           int64    `json:"id"`
	Position     int      `json:"position"`
	Text         string   `json:"text"`
	TimeLimitSec int      `json:"time_limit_sec"`
	Options      []Option `json:"options"`
}

type Option struct {
	ID        int64  `json:"id"`
	Position  int    `json:"position"`
	Text      string `json:"text"`
	IsCorrect bool   `json:"is_correct"`
}

// CorrectOptionID возвращает id правильного варианта.
// Вызывать только для вопроса из викторины, прошедшей Validate.
func (q Question) CorrectOptionID() int64 {
	for _, o := range q.Options {
		if o.IsCorrect {
			return o.ID
		}
	}
	return 0
}

// Validate проверяет то, на что опирается игра. content проверяет то же
// при сохранении, но live не должен падать или считать очки неверно,
// если к нему всё же пришли кривые данные: границу сервиса проверяем всегда.
func (q Quiz) Validate() error {
	if len(q.Questions) == 0 {
		return fmt.Errorf("%w: в викторине нет вопросов", ErrInvalidQuiz)
	}
	for i, qu := range q.Questions {
		if qu.TimeLimitSec < 5 || qu.TimeLimitSec > 120 {
			return fmt.Errorf("%w: вопрос %d: time_limit_sec %d вне 5–120", ErrInvalidQuiz, i, qu.TimeLimitSec)
		}
		if n := len(qu.Options); n < 2 || n > 4 {
			return fmt.Errorf("%w: вопрос %d: вариантов %d, нужно 2–4", ErrInvalidQuiz, i, n)
		}
		correct := 0
		seen := make(map[int64]bool, len(qu.Options))
		for _, o := range qu.Options {
			if seen[o.ID] {
				return fmt.Errorf("%w: вопрос %d: повторяется option_id %d", ErrInvalidQuiz, i, o.ID)
			}
			seen[o.ID] = true
			if o.IsCorrect {
				correct++
			}
		}
		if correct != 1 {
			return fmt.Errorf("%w: вопрос %d: правильных вариантов %d, нужен ровно один", ErrInvalidQuiz, i, correct)
		}
	}
	return nil
}
