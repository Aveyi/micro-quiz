// Сервис live: комнаты и проведение игры викторины.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"github.com/Aveyi/micro-quiz/live/internal/api"
	"github.com/Aveyi/micro-quiz/live/internal/auth"
	"github.com/Aveyi/micro-quiz/live/internal/config"
	"github.com/Aveyi/micro-quiz/live/internal/content"
	"github.com/Aveyi/micro-quiz/live/internal/game"
	"github.com/Aveyi/micro-quiz/live/internal/session"
)

// shutdownTimeout — сколько ждём завершения активных запросов при остановке.
// Docker по умолчанию ждёт 10 с после SIGTERM и потом шлёт SIGKILL,
// поэтому укладываемся раньше.
const shutdownTimeout = 8 * time.Second

func main() {
	log := slog.New(slog.NewJSONHandler(os.Stdout, nil))

	if err := run(log); err != nil {
		log.Error("сервис остановлен с ошибкой", "err", err)
		os.Exit(1)
	}
}

// run вынесен из main, чтобы возвращать ошибку, а не вызывать os.Exit
// посреди кода: тогда отложенные (defer) действия успевают выполниться.
func run(log *slog.Logger) error {
	cfg, err := config.Load()
	if err != nil {
		return err
	}

	// ctx отменится, когда придёт SIGINT (Ctrl+C) или SIGTERM (docker stop).
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	verifier := auth.NewVerifier(cfg.JWTSecret)
	quizzes := content.NewClient(cfg.ContentURL, cfg.InternalToken)
	store := session.NewMemoryStore()

	rooms := &api.Rooms{
		Auth:    verifier,
		Quizzes: quizzes,
		Store:   store,
		Log:     log,
		NewCode: session.NewCode,
	}
	games := game.NewManager(quizzes, store, log, game.DefaultTimeouts)
	ws := &api.WS{
		Auth:  verifier,
		Store: store,
		Rooms: games,
		Log:   log,
	}

	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", handleHealth)
	mux.HandleFunc("POST /live/api/rooms", rooms.Create)
	mux.HandleFunc("GET /live/ws", ws.Connect)

	srv := &http.Server{
		Addr:    ":" + strconv.Itoa(cfg.Port),
		Handler: mux,
		// Без таймаута на заголовки медленный клиент может держать
		// соединение бесконечно (атака Slowloris).
		ReadHeaderTimeout: 5 * time.Second,
		IdleTimeout:       60 * time.Second,
	}

	// ListenAndServe блокирует, поэтому запускаем его в горутине,
	// а главная горутина ждёт сигнала или ошибки сервера.
	errCh := make(chan error, 1)
	go func() {
		log.Info("сервис запущен", "port", cfg.Port)
		errCh <- srv.ListenAndServe()
	}()

	select {
	case err := <-errCh:
		// Сервер не смог стартовать, например порт занят.
		return err
	case <-ctx.Done():
		log.Info("получен сигнал остановки")
	}

	// Shutdown перестаёт принимать новые соединения и ждёт,
	// пока доработают текущие запросы, но не дольше shutdownTimeout.
	shutdownCtx, cancel := context.WithTimeout(context.Background(), shutdownTimeout)
	defer cancel()
	if err := srv.Shutdown(shutdownCtx); err != nil {
		return err
	}
	// Сначала HTTP-сервер перестал принимать подключения, потом закрываем
	// комнаты: иначе в закрытую комнату успел бы зайти новый игрок.
	if err := games.Shutdown(shutdownCtx); err != nil {
		return fmt.Errorf("закрытие комнат: %w", err)
	}
	// После Shutdown ListenAndServe возвращает http.ErrServerClosed — это норма.
	if err := <-errCh; !errors.Is(err, http.ErrServerClosed) {
		return err
	}
	log.Info("сервис остановлен")
	return nil
}

// handleHealth нужен Docker (HEALTHCHECK) и nginx: отвечает, что процесс жив.
func handleHealth(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}
