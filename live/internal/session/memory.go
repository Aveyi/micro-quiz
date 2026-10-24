package session

import (
	"context"
	"sync"
	"time"
)

// MemoryStore — хранилище в памяти процесса. Годится, пока инстанс live
// один; с несколькими инстансами его заменит PostgreSQL.
type MemoryStore struct {
	mu       sync.Mutex
	nextID   int64
	sessions map[int64]Session
}

func NewMemoryStore() *MemoryStore {
	return &MemoryStore{sessions: make(map[int64]Session)}
}

func (m *MemoryStore) Create(_ context.Context, s Session) (Session, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	// То же правило, что у индекса active_room_code в БД.
	for _, other := range m.sessions {
		if other.RoomCode == s.RoomCode && other.Status.Active() {
			return Session{}, ErrCodeTaken
		}
	}
	m.nextID++
	s.ID = m.nextID
	s.Status = StatusLobby
	s.CreatedAt = time.Now().UTC()
	m.sessions[s.ID] = s
	return s, nil
}

func (m *MemoryStore) GetActive(_ context.Context, code string) (Session, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	for _, s := range m.sessions {
		if s.RoomCode == code && s.Status.Active() {
			return s, nil
		}
	}
	return Session{}, ErrNotFound
}

func (m *MemoryStore) SetStatus(_ context.Context, id int64, status Status) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	s, ok := m.sessions[id]
	if !ok {
		return ErrNotFound
	}
	s.Status = status
	m.sessions[id] = s
	return nil
}
