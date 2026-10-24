package session

import (
	"context"
	"errors"
	"regexp"
	"testing"
)

func TestMemoryStoreCodeReuse(t *testing.T) {
	ctx := context.Background()
	m := NewMemoryStore()

	s, err := m.Create(ctx, Session{RoomCode: "482913", QuizID: 3})
	if err != nil {
		t.Fatal(err)
	}
	if s.ID != 1 || s.Status != StatusLobby || s.CreatedAt.IsZero() {
		t.Fatalf("сессия %+v", s)
	}

	// Пока комната активна, код занят.
	if _, err := m.Create(ctx, Session{RoomCode: "482913"}); !errors.Is(err, ErrCodeTaken) {
		t.Fatalf("ожидали ErrCodeTaken, получили %v", err)
	}

	// Игра закончилась — код свободен, а старая сессия по коду не ищется.
	if err := m.SetStatus(ctx, s.ID, StatusFinished); err != nil {
		t.Fatal(err)
	}
	if _, err := m.GetActive(ctx, "482913"); !errors.Is(err, ErrNotFound) {
		t.Fatalf("ожидали ErrNotFound, получили %v", err)
	}
	s2, err := m.Create(ctx, Session{RoomCode: "482913"})
	if err != nil || s2.ID != 2 {
		t.Fatalf("повторное использование кода: %+v, %v", s2, err)
	}
}

func TestNewCode(t *testing.T) {
	re := regexp.MustCompile(`^\d{6}$`)
	seen := map[string]bool{}
	for range 1000 {
		c := NewCode()
		if !re.MatchString(c) {
			t.Fatalf("код %q не из 6 цифр", c)
		}
		seen[c] = true
	}
	// Из 10^6 вариантов 1000 случайных почти наверняка разные.
	if len(seen) < 990 {
		t.Fatalf("всего %d разных кодов из 1000 — генератор не случайный?", len(seen))
	}
}
