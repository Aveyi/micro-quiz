// Package session — игровые сессии: запись о комнате, которая живёт дольше,
// чем соединения. Таблица live.game_sessions, docs/quiz-design.md, раздел 7.3.
package session

import (
	"context"
	"crypto/rand"
	"errors"
	"fmt"
	"math/big"
	"time"
)

type Status string

const (
	StatusLobby     Status = "lobby"
	StatusRunning   Status = "running"
	StatusFinished  Status = "finished"
	StatusCancelled Status = "cancelled"
)

// Active — комнату ещё можно найти по коду (уникальность кода действует
// только среди активных комнат).
func (s Status) Active() bool {
	return s == StatusLobby || s == StatusRunning
}

var (
	ErrNotFound = errors.New("сессия не найдена")
	// ErrCodeTaken — код уже занят активной комнатой; нужно взять другой.
	ErrCodeTaken = errors.New("код комнаты занят")
)

type Session struct {
	ID         int64
	RoomCode   string
	QuizID     int64
	QuizTitle  string // копия на момент игры: история не зависит от content
	HostUserID int64
	Status     Status
	CreatedAt  time.Time
}

// Store — где хранятся сессии. Сейчас в памяти, на шаге с БД появится
// реализация на PostgreSQL с тем же интерфейсом, и остальной код не изменится.
//
// Почему не просто map в памяти: POST /live/api/rooms nginx отправит на любой
// инстанс live, а WebSocket этой комнаты — на тот, что выберет hash по коду.
// Инстансы должны видеть одни и те же сессии, то есть хранилище общее (БД).
type Store interface {
	// Create сохраняет новую сессию в статусе lobby и возвращает её с ID.
	// Если код занят активной комнатой — ErrCodeTaken.
	Create(ctx context.Context, s Session) (Session, error)
	// GetActive ищет активную сессию по коду. Нет такой — ErrNotFound.
	GetActive(ctx context.Context, code string) (Session, error)
	SetStatus(ctx context.Context, id int64, status Status) error
}

// NewCode возвращает случайный код из 6 цифр, например "048213".
// Берём crypto/rand: код — единственная «авторизация» игрока,
// он не должен угадываться по предыдущим кодам.
func NewCode() string {
	n, err := rand.Int(rand.Reader, big.NewInt(1_000_000))
	if err != nil {
		// crypto/rand не возвращает ошибок на поддерживаемых ОС.
		panic(fmt.Sprintf("crypto/rand: %v", err))
	}
	return fmt.Sprintf("%06d", n.Int64())
}
