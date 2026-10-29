package api

import (
	"context"
	"errors"
	"fmt"
	"reflect"
	"testing"
	"time"

	"github.com/gorilla/websocket"

	"github.com/Aveyi/micro-quiz/live/internal/game"
	"github.com/Aveyi/micro-quiz/live/internal/session"
)

func send(t *testing.T, conn *websocket.Conn, msg string) {
	t.Helper()
	if err := conn.WriteMessage(websocket.TextMessage, []byte(msg)); err != nil {
		t.Fatal(err)
	}
}

func joinMsg(nick string) string {
	return fmt.Sprintf(`{"type": "join", "data": {"nickname": %q}}`, nick)
}

// expect читает сообщение и проверяет его type.
func expect(t *testing.T, conn *websocket.Conn, typ string) message {
	t.Helper()
	m := read(t, conn)
	if m.Type != typ {
		t.Fatalf("ожидали %s, получили %+v", typ, m)
	}
	return m
}

func expectError(t *testing.T, conn *websocket.Conn, code string) {
	t.Helper()
	if m := expect(t, conn, "error"); m.Data["code"] != code {
		t.Fatalf("ожидали ошибку %s, получили %v", code, m.Data)
	}
}

// expectClose ждёт close-фрейм с нужным кодом.
func expectClose(t *testing.T, conn *websocket.Conn, code int) {
	t.Helper()
	conn.SetReadDeadline(time.Now().Add(2 * time.Second))
	for {
		_, _, err := conn.ReadMessage()
		if err == nil {
			continue // пропускаем сообщения до закрытия
		}
		if !websocket.IsCloseError(err, code) {
			t.Fatalf("ожидали close %d, получили %v", code, err)
		}
		return
	}
}

// nicknames достаёт ники из data.players.
func nicknames(t *testing.T, data map[string]any) []string {
	t.Helper()
	raw, ok := data["players"].([]any)
	if !ok {
		t.Fatalf("players = %#v", data["players"])
	}
	names := make([]string, 0, len(raw))
	for _, p := range raw {
		names = append(names, p.(map[string]any)["nickname"].(string))
	}
	return names
}

func expectLobby(t *testing.T, conn *websocket.Conn, want ...string) {
	t.Helper()
	m := expect(t, conn, "lobby_update")
	if got := nicknames(t, m.Data); !reflect.DeepEqual(got, want) {
		t.Fatalf("в лобби %v, ожидали %v", got, want)
	}
}

// openRoom создаёт комнату и подключает ведущего.
func openRoom(t *testing.T, e wsEnv) (code string, host *websocket.Conn) {
	t.Helper()
	code = e.createRoom(t, 1)
	host = e.mustDial(t, code, tokenFor(t, "1"))
	expect(t, host, "joined")
	return code, host
}

func TestLobbyJoin(t *testing.T) {
	e := newWSEnv(t)
	code, host := openRoom(t, e)

	vasya := e.mustDial(t, code, "")
	send(t, vasya, joinMsg("  Вася  "))
	j := expect(t, vasya, "joined")
	if j.Data["role"] != "player" || j.Data["player_id"] != 1.0 || j.Data["room_code"] != code {
		t.Fatalf("joined = %v", j.Data)
	}
	if got := nicknames(t, j.Data); !reflect.DeepEqual(got, []string{"Вася"}) {
		t.Fatalf("players = %v (пробелы должны обрезаться)", got)
	}
	expectLobby(t, vasya, "Вася")
	expectLobby(t, host, "Вася")

	// Петя подключился, но ещё не вошёл: событий лобби он не видит.
	// Ваня входит, пока Петя молчит, — Пете ничего не приходит.
	petya := e.mustDial(t, code, "")
	vanya := e.mustDial(t, code, "")
	send(t, vanya, joinMsg("Ваня"))
	expect(t, vanya, "joined")
	expectLobby(t, vanya, "Вася", "Ваня")
	expectLobby(t, vasya, "Вася", "Ваня")
	expectLobby(t, host, "Вася", "Ваня")
	vanya.Close()
	expectLobby(t, vasya, "Вася")
	expectLobby(t, host, "Вася")

	send(t, petya, joinMsg("Петя"))
	// Первым Пете должен прийти joined, а не накопившиеся lobby_update.
	if j := expect(t, petya, "joined"); j.Data["player_id"] != 3.0 {
		t.Fatalf("player_id = %v", j.Data["player_id"])
	}
	for _, c := range []*websocket.Conn{host, vasya, petya} {
		expectLobby(t, c, "Вася", "Петя")
	}

	// Вася ушёл — остальные видят обновлённый список.
	vasya.Close()
	expectLobby(t, host, "Петя")
	expectLobby(t, petya, "Петя")
}

func TestLobbyJoinErrors(t *testing.T) {
	e := newWSEnv(t)
	code, host := openRoom(t, e)

	vasya := e.mustDial(t, code, "")
	send(t, vasya, joinMsg("Вася"))
	expect(t, vasya, "joined")
	expectLobby(t, vasya, "Вася")
	expectLobby(t, host, "Вася")

	// Ведущий не может войти как игрок.
	send(t, host, joinMsg("Ведущий"))
	expectError(t, host, "not_allowed")

	// Второй join от того же игрока.
	send(t, vasya, joinMsg("Вася2"))
	expectError(t, vasya, "invalid_state")

	// Ошибки ника оставляют соединение открытым: можно попробовать снова.
	p := e.mustDial(t, code, "")
	send(t, p, joinMsg("ВАСЯ"))
	expectError(t, p, "nickname_taken")
	send(t, p, joinMsg("   "))
	expectError(t, p, "invalid_nickname")
	send(t, p, joinMsg("очень-длинный-ник-больше-20"))
	expectError(t, p, "invalid_nickname")
	send(t, p, `{"type": "join", "data": {"nickname": 42}}`)
	expectError(t, p, "bad_message")
	send(t, p, joinMsg("Петя"))
	expect(t, p, "joined")
}

func TestLobbyRoomFull(t *testing.T) {
	e := newWSEnv(t)
	code, host := openRoom(t, e)
	drain(host)

	for i := range 50 {
		p := e.mustDial(t, code, "")
		send(t, p, joinMsg(fmt.Sprintf("игрок %d", i)))
		expect(t, p, "joined")
		// Каждый вход рассылает lobby_update всем, а настоящий клиент
		// читает сразу. Если не читать, очередь переполнится и сервер
		// отключит такого игрока как медленного.
		drain(p)
	}

	extra := e.mustDial(t, code, "")
	send(t, extra, joinMsg("лишний"))
	expectError(t, extra, "room_full")
	expectClose(t, extra, websocket.CloseNormalClosure)
}

// drain читает и выбрасывает всё, что приходит в соединение.
func drain(conn *websocket.Conn) {
	go func() {
		for {
			if _, _, err := conn.ReadMessage(); err != nil {
				return
			}
		}
	}()
}

func TestLobbyJoinTimeout(t *testing.T) {
	e := newWSEnvWith(t, game.Timeouts{HostWait: 10 * time.Second, Lobby: time.Hour, Join: 100 * time.Millisecond})
	code, host := openRoom(t, e)

	silent := e.mustDial(t, code, "")
	joined := e.mustDial(t, code, "")
	send(t, joined, joinMsg("Вася"))
	expect(t, joined, "joined")
	expectLobby(t, joined, "Вася")
	expectLobby(t, host, "Вася")

	// Молчун отключается, а вошедший игрок — нет.
	expectClose(t, silent, websocket.ClosePolicyViolation)
	send(t, joined, joinMsg("ещё раз"))
	expectError(t, joined, "invalid_state")
}

func TestLobbyTimeout(t *testing.T) {
	e := newWSEnvWith(t, game.Timeouts{HostWait: 10 * time.Second, Lobby: 200 * time.Millisecond, Join: time.Hour})
	code, host := openRoom(t, e)
	p := e.mustDial(t, code, "")
	send(t, p, joinMsg("Вася"))
	expect(t, p, "joined")
	expectLobby(t, p, "Вася")
	expectLobby(t, host, "Вася")

	for _, c := range []*websocket.Conn{host, p} {
		if m := expect(t, c, "room_closed"); m.Data["reason"] != "lobby_timeout" {
			t.Fatalf("reason = %v", m.Data["reason"])
		}
		expectClose(t, c, websocket.CloseNormalClosure)
	}
	eventually(t, "сессия отменена", func() bool {
		_, err := e.store.GetActive(context.Background(), code)
		return errors.Is(err, session.ErrNotFound)
	})
}

func TestShutdown(t *testing.T) {
	e := newWSEnv(t)
	code, host := openRoom(t, e)
	p := e.mustDial(t, code, "")
	send(t, p, joinMsg("Вася"))
	expect(t, p, "joined")
	expectLobby(t, p, "Вася")
	expectLobby(t, host, "Вася")

	// Shutdown ждёт, пока клиенты закроют соединения, поэтому читаем
	// параллельно — как настоящие клиенты.
	errCh := make(chan error, 1)
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		errCh <- e.rooms.Shutdown(ctx)
	}()

	for _, c := range []*websocket.Conn{host, p} {
		if m := expect(t, c, "room_closed"); m.Data["reason"] != "server_shutdown" {
			t.Fatalf("reason = %v", m.Data["reason"])
		}
		expectClose(t, c, websocket.CloseGoingAway)
	}
	if err := <-errCh; err != nil {
		t.Fatalf("Shutdown: %v", err)
	}
}

func TestLobbyTimeoutCountsFromCreation(t *testing.T) {
	// Срок лобби — от создания комнаты, а не от подключения ведущего:
	// иначе комната могла бы жить дольше, чем её запись в БД (её уберёт
	// session.ExpireLobbiesLoop).
	e := newWSEnvWith(t, game.Timeouts{HostWait: 10 * time.Second, Lobby: 400 * time.Millisecond, Join: time.Hour})
	code := e.createRoom(t, 1)
	time.Sleep(300 * time.Millisecond) // ведущий открыл комнату не сразу

	opened := time.Now()
	host := e.mustDial(t, code, tokenFor(t, "1"))
	expect(t, host, "joined") // ведущий успел войти, срок ещё не вышел
	if m := expect(t, host, "room_closed"); m.Data["reason"] != "lobby_timeout" {
		t.Fatalf("room_closed = %v", m.Data)
	}
	// Осталось ~100 мс из 400, а не все 400 с момента открытия.
	if waited := time.Since(opened); waited > 250*time.Millisecond {
		t.Fatalf("лобби закрылось через %v после открытия, ожидали ~100 мс", waited)
	}
}
