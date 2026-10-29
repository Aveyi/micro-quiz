package session

import (
	"cmp"
	"context"
	"fmt"
	"slices"
	"strings"
	"sync"
	"time"
)

// MemoryStore — хранилище в памяти процесса. Годится, пока инстанс live
// один; с несколькими инстансами его заменит PostgreSQL.
type MemoryStore struct {
	mu       sync.Mutex
	nextID   int64
	sessions map[int64]Session
	// Отдельный счётчик, как у отдельной таблицы в БД: у каждой своя IDENTITY.
	nextPlayerID int64
	players      map[int64]*memPlayer
	answers      []memAnswer
}

type memPlayer struct {
	id, sessionID int64
	nickname      string
	left          bool
	result        *Result
}

type memAnswer struct {
	sessionID int64
	Answer
}

func NewMemoryStore() *MemoryStore {
	return &MemoryStore{sessions: make(map[int64]Session), players: make(map[int64]*memPlayer)}
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
	now := time.Now().UTC()
	switch status {
	case StatusRunning:
		s.StartedAt = &now
	case StatusFinished, StatusCancelled:
		s.FinishedAt = &now
	}
	m.sessions[id] = s
	return nil
}

func (m *MemoryStore) ExpireLobbies(_ context.Context, olderThan time.Duration) (int64, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	now := time.Now().UTC()
	var n int64
	for id, s := range m.sessions {
		if s.Status == StatusLobby && s.CreatedAt.Before(now.Add(-olderThan)) {
			s.Status = StatusCancelled
			s.FinishedAt = &now
			m.sessions[id] = s
			n++
		}
	}
	return n, nil
}

func (m *MemoryStore) AddPlayer(_ context.Context, sessionID int64, nickname string) (int64, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	// То же правило, что у индекса unique_nickname_in_session (lower(nickname)).
	for _, p := range m.players {
		if p.sessionID == sessionID && strings.ToLower(p.nickname) == strings.ToLower(nickname) {
			return 0, ErrNicknameTaken
		}
	}
	m.nextPlayerID++
	m.players[m.nextPlayerID] = &memPlayer{id: m.nextPlayerID, sessionID: sessionID, nickname: nickname}
	return m.nextPlayerID, nil
}

func (m *MemoryStore) RemovePlayer(_ context.Context, playerID int64) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	delete(m.players, playerID)
	return nil
}

func (m *MemoryStore) MarkLeft(_ context.Context, playerID int64) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if p, ok := m.players[playerID]; ok {
		p.left = true
	}
	return nil
}

func (m *MemoryStore) SaveAnswers(_ context.Context, sessionID int64, answers []Answer) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	// Всё или ничего, как в транзакции: сначала проверяем, потом пишем.
	// То же правило, что UNIQUE (player_id, question_index) в БД.
	for _, a := range answers {
		for _, old := range m.answers {
			if old.PlayerID == a.PlayerID && old.QuestionIndex == a.QuestionIndex {
				return fmt.Errorf("ответ игрока %d на вопрос %d уже записан", a.PlayerID, a.QuestionIndex)
			}
		}
	}
	for _, a := range answers {
		m.answers = append(m.answers, memAnswer{sessionID: sessionID, Answer: a})
	}
	return nil
}

func (m *MemoryStore) Finish(_ context.Context, sessionID int64, results []Result) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	s, ok := m.sessions[sessionID]
	if !ok {
		return ErrNotFound
	}
	for _, r := range results {
		if p, ok := m.players[r.PlayerID]; ok {
			p.result = &r
		}
	}
	s.Status = StatusFinished
	now := time.Now().UTC()
	s.FinishedAt = &now
	m.sessions[sessionID] = s
	return nil
}

func (m *MemoryStore) ListGames(_ context.Context, hostUserID int64, limit int) ([]GameSummary, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	games := []GameSummary{}
	for _, s := range m.sessions {
		if s.HostUserID != hostUserID {
			continue
		}
		g := GameSummary{Session: s}
		for _, p := range m.players {
			if p.sessionID == s.ID {
				g.PlayerCount++
			}
		}
		games = append(games, g)
	}
	// Новые сверху; при равном времени — больший id.
	slices.SortFunc(games, func(a, b GameSummary) int {
		if c := b.CreatedAt.Compare(a.CreatedAt); c != 0 {
			return c
		}
		return cmp.Compare(b.ID, a.ID)
	})
	return games[:min(len(games), limit)], nil
}

func (m *MemoryStore) GetGame(_ context.Context, id int64) (GameDetails, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	s, ok := m.sessions[id]
	if !ok {
		return GameDetails{}, ErrNotFound
	}
	g := GameDetails{Session: s, Players: []PlayerResult{}, Questions: []QuestionStats{}}

	for _, p := range m.players {
		if p.sessionID != id {
			continue
		}
		pr := PlayerResult{PlayerID: p.id, Nickname: p.nickname, Left: p.left}
		if p.result != nil {
			// Копии, а не указатели внутрь хранилища: вызывающий не должен
			// иметь возможность менять наши данные.
			score, rank := p.result.Score, p.result.Rank
			pr.Score, pr.Rank = &score, &rank
		}
		g.Players = append(g.Players, pr)
	}
	// Как ORDER BY final_rank NULLS LAST, id.
	slices.SortFunc(g.Players, func(a, b PlayerResult) int {
		switch {
		case a.Rank != nil && b.Rank != nil && *a.Rank != *b.Rank:
			return cmp.Compare(*a.Rank, *b.Rank)
		case a.Rank != nil && b.Rank == nil:
			return -1
		case a.Rank == nil && b.Rank != nil:
			return 1
		}
		return cmp.Compare(a.PlayerID, b.PlayerID)
	})

	byIndex := map[int]*QuestionStats{}
	for _, a := range m.answers {
		if a.sessionID != id {
			continue
		}
		q, ok := byIndex[a.QuestionIndex]
		if !ok {
			q = &QuestionStats{QuestionIndex: a.QuestionIndex, QuestionID: a.QuestionID}
			byIndex[a.QuestionIndex] = q
		}
		q.Total++
		if a.OptionID != 0 {
			q.Answered++
		}
		if a.IsCorrect {
			q.Correct++
		}
	}
	for _, q := range byIndex {
		g.Questions = append(g.Questions, *q)
	}
	slices.SortFunc(g.Questions, func(a, b QuestionStats) int { return cmp.Compare(a.QuestionIndex, b.QuestionIndex) })
	return g, nil
}
