package api

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gorilla/websocket"

	"github.com/Aveyi/micro-quiz/live/internal/auth"
	"github.com/Aveyi/micro-quiz/live/internal/content"
	"github.com/Aveyi/micro-quiz/live/internal/game"
	"github.com/Aveyi/micro-quiz/live/internal/session"
)

var wsQuizzes = fakeQuizzes{quizzes: map[int64]content.Quiz{
	3: {ID: 3, OwnerID: 1, Title: "Столицы мира", Questions: make([]content.Question, 2)},
}}

// wsEnv — настоящий HTTP-сервер с ручкой /live/ws; тесты подключаются
// к нему настоящим WebSocket-клиентом.
type wsEnv struct {
	url   string
	store *session.MemoryStore
	rooms *game.Manager
}

func newWSEnv(t *testing.T) wsEnv {
	t.Helper()
	return newWSEnvWith(t, game.DefaultTimeouts)
}

func newWSEnvWith(t *testing.T, timeouts game.Timeouts) wsEnv {
	t.Helper()
	log := slog.New(slog.NewTextHandler(io.Discard, nil))
	store := session.NewMemoryStore()
	rooms := game.NewManager(wsQuizzes, store, log, timeouts)
	h := &WS{Auth: auth.NewVerifier(secret), Store: store, Rooms: rooms, Log: log}

	srv := httptest.NewServer(http.HandlerFunc(h.Connect))
	t.Cleanup(srv.Close)
	return wsEnv{url: "ws" + strings.TrimPrefix(srv.URL, "http"), store: store, rooms: rooms}
}

// createRoom создаёт сессию так же, как POST /live/api/rooms.
func (e wsEnv) createRoom(t *testing.T, hostID int64) string {
	t.Helper()
	s, err := e.store.Create(context.Background(), session.Session{
		RoomCode: session.NewCode(), QuizID: 3, QuizTitle: "Столицы мира", HostUserID: hostID,
	})
	if err != nil {
		t.Fatal(err)
	}
	return s.RoomCode
}

// dial подключается к комнате; token пустой — подключение игрока.
func (e wsEnv) dial(code, token string) (*websocket.Conn, *http.Response, error) {
	header := http.Header{}
	if token != "" {
		header.Set("Authorization", "Bearer "+token)
	}
	return websocket.DefaultDialer.Dial(e.url+"/live/ws?room="+code, header)
}

func (e wsEnv) mustDial(t *testing.T, code, token string) *websocket.Conn {
	t.Helper()
	conn, resp, err := e.dial(code, token)
	if err != nil {
		status := 0
		if resp != nil {
			status = resp.StatusCode
		}
		t.Fatalf("подключение: %v (HTTP %d)", err, status)
	}
	t.Cleanup(func() { conn.Close() })
	return conn
}

type message struct {
	Type string         `json:"type"`
	Data map[string]any `json:"data"`
}

func read(t *testing.T, conn *websocket.Conn) message {
	t.Helper()
	conn.SetReadDeadline(time.Now().Add(2 * time.Second))
	var m message
	if err := conn.ReadJSON(&m); err != nil {
		t.Fatalf("чтение: %v", err)
	}
	return m
}

func TestWSHandshakeErrors(t *testing.T) {
	e := newWSEnv(t)
	code := e.createRoom(t, 1)
	host1, host2 := tokenFor(t, "1"), tokenFor(t, "2")

	tests := []struct {
		name  string
		code  string
		token string
		want  int
	}{
		{"нет room", "", "", 400},
		{"нет такой комнаты", "000000", "", 404},
		{"плохой токен", code, "garbage", 401},
		{"чужой ведущий", code, host2, 403},
		{"игрок раньше ведущего", code, "", 404},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, resp, err := e.dial(tt.code, tt.token)
			if !errors.Is(err, websocket.ErrBadHandshake) || resp == nil {
				t.Fatalf("ожидали отказ до Upgrade, получили %v", err)
			}
			if resp.StatusCode != tt.want {
				t.Fatalf("HTTP %d, ожидали %d", resp.StatusCode, tt.want)
			}
		})
	}

	// После всех отказов ведущий по-прежнему может подключиться.
	if m := read(t, e.mustDial(t, code, host1)); m.Type != "joined" {
		t.Fatalf("ожидали joined, получили %+v", m)
	}
}

func TestWSHostJoined(t *testing.T) {
	e := newWSEnv(t)
	code := e.createRoom(t, 1)

	m := read(t, e.mustDial(t, code, tokenFor(t, "1")))
	if m.Type != "joined" {
		t.Fatalf("ожидали joined, получили %+v", m)
	}
	d := m.Data
	if d["role"] != "host" || d["room_code"] != code || d["quiz_title"] != "Столицы мира" || d["question_count"] != 2.0 {
		t.Fatalf("data = %v", d)
	}
	if _, has := d["player_id"]; has {
		t.Fatal("у ведущего не должно быть player_id")
	}
	if players, ok := d["players"].([]any); !ok || len(players) != 0 {
		t.Fatalf("players = %#v, ожидали пустой массив", d["players"])
	}

	// Второй ведущий в ту же комнату не пускается.
	_, resp, err := e.dial(code, tokenFor(t, "1"))
	if err == nil || resp.StatusCode != http.StatusConflict {
		t.Fatalf("второй ведущий: %v, ожидали HTTP 409", err)
	}
}

func TestWSBadMessage(t *testing.T) {
	e := newWSEnv(t)
	code := e.createRoom(t, 1)
	read(t, e.mustDial(t, code, tokenFor(t, "1"))) // joined ведущего
	player := e.mustDial(t, code, "")

	for _, bad := range []string{`hello`, `{"data": {}}`, `[1, 2]`} {
		player.WriteMessage(websocket.TextMessage, []byte(bad))
		if m := read(t, player); m.Type != "error" || m.Data["code"] != "bad_message" {
			t.Fatalf("на %q ожидали bad_message, получили %+v", bad, m)
		}
	}

	// Неизвестный type игнорируется: следующим придёт ответ уже на мусор.
	player.WriteMessage(websocket.TextMessage, []byte(`{"type": "from_the_future", "data": {}}`))
	player.WriteMessage(websocket.TextMessage, []byte(`garbage`))
	if m := read(t, player); m.Data["code"] != "bad_message" {
		t.Fatalf("ожидали bad_message, получили %+v", m)
	}
}

func TestWSHostLeaves(t *testing.T) {
	e := newWSEnv(t)
	code := e.createRoom(t, 1)
	host := e.mustDial(t, code, tokenFor(t, "1"))
	read(t, host)
	player := e.mustDial(t, code, "")

	host.Close()

	m := read(t, player)
	if m.Type != "room_closed" || m.Data["reason"] != "host_left" {
		t.Fatalf("ожидали room_closed host_left, получили %+v", m)
	}
	// После room_closed сервер закрывает соединение кодом 1000.
	player.SetReadDeadline(time.Now().Add(2 * time.Second))
	_, _, err := player.ReadMessage()
	if !websocket.IsCloseError(err, websocket.CloseNormalClosure) {
		t.Fatalf("ожидали close 1000, получили %v", err)
	}

	// Сессия отменена: вернуться в комнату нельзя никому. Close-фрейм
	// игрок мог получить чуть раньше, чем комната обновила сессию, — ждём.
	eventually(t, "сессия отменена и комната убрана из памяти", func() bool {
		_, err := e.store.GetActive(context.Background(), code)
		return errors.Is(err, session.ErrNotFound) && e.rooms.Get(code) == nil
	})
	if _, resp, _ := e.dial(code, tokenFor(t, "1")); resp == nil || resp.StatusCode != http.StatusNotFound {
		t.Fatal("ведущий смог вернуться в отменённую комнату")
	}
}

func TestWSMessageTooBig(t *testing.T) {
	e := newWSEnv(t)
	code := e.createRoom(t, 1)
	host := e.mustDial(t, code, tokenFor(t, "1"))
	read(t, host)

	// Больше maxMessageSize (4 КБ): сервер рвёт соединение, а для ведущего
	// это ещё и закрытие комнаты.
	host.WriteMessage(websocket.TextMessage, []byte(strings.Repeat("a", 5000)))
	host.SetReadDeadline(time.Now().Add(2 * time.Second))
	if _, _, err := host.ReadMessage(); err == nil {
		t.Fatal("ожидали разрыв соединения")
	}
	eventually(t, "комната закрылась после разрыва соединения ведущего", func() bool {
		return e.rooms.Get(code) == nil
	})
}

// eventually ждёт до секунды, пока cond станет true. Нужен там, где
// результат появляется в другой горутине чуть позже.
func eventually(t *testing.T, what string, cond func() bool) {
	t.Helper()
	deadline := time.Now().Add(time.Second)
	for !cond() {
		if time.Now().After(deadline) {
			t.Fatal("не дождались: " + what)
		}
		time.Sleep(10 * time.Millisecond)
	}
}
