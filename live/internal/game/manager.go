package game

import (
	"context"
	"errors"
	"log/slog"
	"sync"
	"time"

	"github.com/gorilla/websocket"

	"github.com/Aveyi/micro-quiz/live/internal/content"
	"github.com/Aveyi/micro-quiz/live/internal/session"
)

var (
	// ErrHostConnected — комната уже открыта, то есть ведущий уже подключён:
	// комната живёт в памяти, только пока подключён её ведущий.
	ErrHostConnected = errors.New("ведущий уже подключён")
	// ErrShuttingDown — сервер останавливается и новых комнат не открывает.
	ErrShuttingDown = errors.New("сервер останавливается")
)

// Timeouts — сроки жизни комнаты. Вынесены в настройки, чтобы тесты
// могли проверить их за миллисекунды, а не ждать 30 минут.
type Timeouts struct {
	// HostWait — сколько комната ждёт ведущего после открытия. Страховка:
	// если Upgrade у ведущего не удался, комната не висит в памяти.
	HostWait time.Duration
	// Lobby — сколько лобби может ждать start (правила игры, раздел 2).
	Lobby time.Duration
	// Join — сколько игрок может быть подключён, не прислав join.
	Join time.Duration
}

var DefaultTimeouts = Timeouts{
	HostWait: 10 * time.Second,
	Lobby:    30 * time.Minute,
	Join:     30 * time.Second,
}

type QuizSource interface {
	GetQuiz(ctx context.Context, id int64) (content.Quiz, error)
}

// Manager — комнаты, открытые на этом инстансе, по коду.
// map трогают горутины разных HTTP-запросов, поэтому нужен мьютекс.
type Manager struct {
	quizzes  QuizSource
	store    session.Store
	log      *slog.Logger
	timeouts Timeouts

	mu      sync.Mutex
	rooms   map[string]*Room
	closing bool
	// conns считает живые соединения, чтобы Shutdown дождался,
	// пока все они попрощаются close-фреймом.
	conns sync.WaitGroup
}

func NewManager(quizzes QuizSource, store session.Store, log *slog.Logger, t Timeouts) *Manager {
	return &Manager{quizzes: quizzes, store: store, log: log, timeouts: t, rooms: make(map[string]*Room)}
}

// OpenForHost открывает комнату сессии на этом инстансе: загружает
// викторину и запускает горутину комнаты.
func (m *Manager) OpenForHost(ctx context.Context, sess session.Session) (*Room, error) {
	if m.Get(sess.RoomCode) != nil {
		return nil, ErrHostConnected
	}

	// Викторину загружаем без мьютекса: запрос к content может идти
	// секунды, и всё это время другие комнаты не могли бы открыться.
	quiz, err := m.quizzes.GetQuiz(ctx, sess.QuizID)
	if err != nil {
		return nil, err
	}

	m.mu.Lock()
	defer m.mu.Unlock()
	if m.closing {
		return nil, ErrShuttingDown
	}
	// Проверяем ещё раз: пока шёл запрос, мог успеть второй ведущий.
	if _, ok := m.rooms[sess.RoomCode]; ok {
		return nil, ErrHostConnected
	}
	r := newRoom(sess, quiz, m.store, m.log, m.timeouts)
	r.onClose = func() { m.remove(sess.RoomCode, r) }
	m.rooms[sess.RoomCode] = r
	go r.run()
	return r, nil
}

// Get возвращает открытую комнату или nil.
func (m *Manager) Get(code string) *Room {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.rooms[code]
}

// Serve обслуживает соединение после Upgrade, пока оно не закроется.
func (m *Manager) Serve(room *Room, conn *websocket.Conn, role Role) {
	m.mu.Lock()
	if m.closing {
		m.mu.Unlock()
		closeNow(conn, "server shutdown")
		return
	}
	// Add под тем же мьютексом, что и проверка closing: так Shutdown
	// не начнёт ждать (Wait), пока кто-то ещё может сделать Add.
	m.conns.Add(1)
	m.mu.Unlock()
	defer m.conns.Done()

	serve(room, conn, role)
}

// Shutdown закрывает все комнаты (room_closed server_shutdown, код 1001)
// и ждёт, пока соединения закроются, но не дольше ctx.
//
// http.Server.Shutdown здесь не помогает: после Upgrade соединение уже не
// HTTP-запрос, сервер о нём не знает и ждать его не будет.
func (m *Manager) Shutdown(ctx context.Context) error {
	m.mu.Lock()
	m.closing = true
	rooms := make([]*Room, 0, len(m.rooms))
	for _, r := range m.rooms {
		rooms = append(rooms, r)
	}
	m.mu.Unlock()

	m.log.Info("закрываем комнаты", "rooms", len(rooms))
	for _, r := range rooms {
		r.shutdown()
	}

	// WaitGroup не умеет ждать с таймаутом, поэтому ждём в горутине.
	done := make(chan struct{})
	go func() {
		m.conns.Wait()
		close(done)
	}()
	select {
	case <-done:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

func (m *Manager) remove(code string, r *Room) {
	m.mu.Lock()
	defer m.mu.Unlock()
	// Удаляем, только если под этим кодом всё ещё именно эта комната.
	if m.rooms[code] == r {
		delete(m.rooms, code)
	}
}
