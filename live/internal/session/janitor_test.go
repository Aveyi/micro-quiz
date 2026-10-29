package session

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"testing"
	"time"
)

func TestExpireLobbiesLoop(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	st := NewMemoryStore()
	st.Create(ctx, Session{RoomCode: "300001", QuizID: 3, QuizTitle: "x", HostUserID: 1})

	done := make(chan struct{})
	go func() {
		ExpireLobbiesLoop(ctx, st, 50*time.Millisecond, 10*time.Millisecond, slog.New(slog.NewTextHandler(io.Discard, nil)))
		close(done)
	}()

	deadline := time.Now().Add(2 * time.Second)
	for {
		if _, err := st.GetActive(ctx, "300001"); errors.Is(err, ErrNotFound) {
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("уборка не отменила брошенное лобби")
		}
		time.Sleep(5 * time.Millisecond)
	}

	cancel()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("цикл уборки не остановился после отмены контекста")
	}
}
