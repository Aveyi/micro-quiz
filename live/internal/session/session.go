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
	// ErrNicknameTaken — ник уже есть в сессии (без учёта регистра).
	ErrNicknameTaken = errors.New("ник уже занят")
)

type Session struct {
	ID         int64
	RoomCode   string
	QuizID     int64
	QuizTitle  string // копия на момент игры: история не зависит от content
	HostUserID int64
	Status     Status
	CreatedAt  time.Time
	StartedAt  *time.Time // nil — игра не начиналась
	FinishedAt *time.Time // nil — ещё не закончилась
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
	// ExpireLobbies отменяет сессии, которые дольше olderThan висят в лобби,
	// и возвращает, сколько отменено. Нужна для комнат, которые создали, но
	// ведущий так и не открыл: в памяти live их нет, и таймер лобби их не видит.
	ExpireLobbies(ctx context.Context, olderThan time.Duration) (int64, error)

	// AddPlayer записывает вошедшего игрока и возвращает его id — это и
	// есть player_id в протоколе. Ник занят — ErrNicknameTaken.
	AddPlayer(ctx context.Context, sessionID int64, nickname string) (int64, error)
	// RemovePlayer удаляет игрока, ушедшего из лобби: он не играл, и его
	// ник должен освободиться для других.
	RemovePlayer(ctx context.Context, playerID int64) error
	// MarkLeft отмечает игрока, выбывшего во время игры. Запись остаётся:
	// его ответы и очки — часть истории.
	MarkLeft(ctx context.Context, playerID int64) error
	// SaveAnswers записывает ответы на один вопрос одной транзакцией.
	SaveAnswers(ctx context.Context, sessionID int64, answers []Answer) error
	// Finish записывает итоговые очки и места и ставит статус finished —
	// тоже одной транзакцией, чтобы не было «завершённой игры без итогов».
	Finish(ctx context.Context, sessionID int64, results []Result) error

	// ListGames — игры ведущего, новые сверху, не больше limit.
	ListGames(ctx context.Context, hostUserID int64, limit int) ([]GameSummary, error)
	// GetGame — результаты одной игры. Нет такой — ErrNotFound.
	// Владельца проверяет вызывающий: он знает, кто спрашивает.
	GetGame(ctx context.Context, id int64) (GameDetails, error)
}

// Answer — ответ игрока на вопрос (строка live.player_answers).
type Answer struct {
	PlayerID      int64
	QuestionIndex int
	QuestionID    int64
	OptionID      int64 // 0 — не успел ответить (в БД NULL)
	IsCorrect     bool
	ResponseMs    int // при OptionID == 0 не используется (в БД NULL)
	Points        int
}

// Result — итог игрока после последнего вопроса.
type Result struct {
	PlayerID int64
	Score    int
	Rank     int
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
