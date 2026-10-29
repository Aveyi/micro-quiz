package session

import (
	"context"
	"log/slog"
	"time"
)

// ExpireLobbiesLoop раз в every отменяет лобби старше ttl, пока не отменят ctx.
// Первый проход — сразу при старте: за время, пока live был выключен,
// могли накопиться брошенные комнаты.
//
// Запускается в каждом инстансе live; согласовывать их не нужно, потому что
// ExpireLobbies идемпотентна.
func ExpireLobbiesLoop(ctx context.Context, st Store, ttl, every time.Duration, log *slog.Logger) {
	ticker := time.NewTicker(every)
	defer ticker.Stop()
	for {
		callCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
		n, err := st.ExpireLobbies(callCtx, ttl)
		cancel()
		switch {
		case err != nil && ctx.Err() == nil:
			log.Error("уборка брошенных лобби", "err", err)
		case n > 0:
			log.Info("отменены брошенные лобби", "count", n)
		}

		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}
