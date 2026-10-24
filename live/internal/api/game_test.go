package api

import (
	"context"
	"errors"
	"fmt"
	"testing"
	"time"

	"github.com/gorilla/websocket"

	"github.com/Aveyi/micro-quiz/live/internal/game"
	"github.com/Aveyi/micro-quiz/live/internal/session"
)

// gameTimeouts: «секунда» вопроса — 20 мс, вопрос на 20 с идёт 0,4 с.
var gameTimeouts = game.Timeouts{
	HostWait:       10 * time.Second,
	Lobby:          time.Hour,
	Join:           time.Hour,
	QuestionSecond: 20 * time.Millisecond,
}

const (
	start = `{"type": "start", "data": {}}`
	next  = `{"type": "next", "data": {}}`
)

func answerMsg(index int, option int64) string {
	return fmt.Sprintf(`{"type": "answer", "data": {"question_index": %d, "option_id": %d}}`, index, option)
}

// skipTo читает сообщения, пропуская lobby_update и answer_progress,
// пока не придёт нужный type.
func skipTo(t *testing.T, conn *websocket.Conn, typ string) message {
	t.Helper()
	for {
		m := read(t, conn)
		if m.Type == typ {
			return m
		}
		if m.Type != "lobby_update" && m.Type != "answer_progress" {
			t.Fatalf("ожидали %s, получили %+v", typ, m)
		}
	}
}

// skipError — как expectError, но пропускает lobby_update и answer_progress.
func skipError(t *testing.T, conn *websocket.Conn, code string) {
	t.Helper()
	if m := skipTo(t, conn, "error"); m.Data["code"] != code {
		t.Fatalf("ожидали ошибку %s, получили %v", code, m.Data)
	}
}

func joinPlayer(t *testing.T, e wsEnv, code, nick string) *websocket.Conn {
	t.Helper()
	p := e.mustDial(t, code, "")
	send(t, p, joinMsg(nick))
	skipTo(t, p, "joined")
	return p
}

// sub достаёт вложенный объект из data.
func sub(t *testing.T, data map[string]any, key string) map[string]any {
	t.Helper()
	v, ok := data[key].(map[string]any)
	if !ok {
		t.Fatalf("%s = %#v, ожидали объект", key, data[key])
	}
	return v
}

func entries(t *testing.T, data map[string]any) []map[string]any {
	t.Helper()
	raw, ok := data["leaderboard"].([]any)
	if !ok {
		t.Fatalf("leaderboard = %#v", data["leaderboard"])
	}
	out := make([]map[string]any, len(raw))
	for i, e := range raw {
		out[i] = e.(map[string]any)
	}
	return out
}

func TestGameFull(t *testing.T) {
	e := newWSEnvWith(t, gameTimeouts)
	code, host := openRoom(t, e)
	vasya := joinPlayer(t, e, code, "Вася")
	petya := joinPlayer(t, e, code, "Петя")

	send(t, host, start)

	// Вопрос 1: правильного ответа в сообщении нет.
	q := skipTo(t, host, "question")
	if q.Data["question_index"] != 0.0 || q.Data["question_count"] != 2.0 || q.Data["text"] != "Столица Австралии?" {
		t.Fatalf("question = %v", q.Data)
	}
	for _, o := range q.Data["options"].([]any) {
		if _, leak := o.(map[string]any)["is_correct"]; leak {
			t.Fatal("в question утёк правильный ответ")
		}
	}
	skipTo(t, vasya, "question")
	skipTo(t, petya, "question")

	// Вася отвечает верно, Петя — нет.
	send(t, vasya, answerMsg(0, 18))
	expect(t, vasya, "answer_accepted")
	if p := expect(t, host, "answer_progress"); p.Data["answered"] != 1.0 || p.Data["total"] != 2.0 {
		t.Fatalf("answer_progress = %v", p.Data)
	}
	send(t, petya, answerMsg(0, 17))
	expect(t, petya, "answer_accepted")
	expect(t, host, "answer_progress")

	// Ответили все — результат сразу, не дожидаясь таймера.
	r := expect(t, host, "question_result")
	if r.Data["correct_option_id"] != 18.0 {
		t.Fatalf("correct_option_id = %v", r.Data["correct_option_id"])
	}
	if counts := sub(t, r.Data, "option_counts"); counts["17"] != 1.0 || counts["18"] != 1.0 {
		t.Fatalf("option_counts = %v", counts)
	}
	if _, has := r.Data["you"]; has {
		t.Fatal("у ведущего не должно быть you")
	}
	board := entries(t, r.Data)
	if len(board) != 2 || board[0]["nickname"] != "Вася" || board[0]["rank"] != 1.0 || board[1]["score"] != 0.0 {
		t.Fatalf("leaderboard = %v", board)
	}
	vasyaScore := board[0]["score"].(float64)
	if vasyaScore < 900 || vasyaScore > 1000 {
		t.Fatalf("Вася ответил сразу, а получил %v", vasyaScore)
	}

	rv := expect(t, vasya, "question_result")
	if _, has := rv.Data["option_counts"]; has {
		t.Fatal("у игрока не должно быть option_counts")
	}
	if you := sub(t, rv.Data, "you"); you["correct"] != true || you["points"] != vasyaScore || you["score"] != vasyaScore || you["rank"] != 1.0 {
		t.Fatalf("you Васи = %v", you)
	}
	if you := sub(t, expect(t, petya, "question_result").Data, "you"); you["correct"] != false || you["points"] != 0.0 || you["rank"] != 2.0 {
		t.Fatalf("you Пети = %v", you)
	}

	// Вопрос 2: никто не отвечает, вопрос заканчивается по таймеру.
	send(t, host, next)
	began := time.Now()
	for _, c := range []*websocket.Conn{host, vasya, petya} {
		if m := expect(t, c, "question"); m.Data["question_index"] != 1.0 {
			t.Fatalf("question_index = %v", m.Data["question_index"])
		}
	}
	expect(t, host, "question_result")
	if waited := time.Since(began); waited < 300*time.Millisecond {
		t.Fatalf("результат через %v, а таймер 400 мс", waited)
	}
	if you := sub(t, expect(t, petya, "question_result").Data, "you"); you["points"] != 0.0 {
		t.Fatalf("без ответа — 0 очков, а у Пети %v", you)
	}
	expect(t, vasya, "question_result")

	// Итоги.
	send(t, host, next)
	over := expect(t, host, "game_over")
	if len(entries(t, over.Data)) != 2 {
		t.Fatalf("в итогах должны быть все игроки: %v", over.Data)
	}
	if you := sub(t, expect(t, vasya, "game_over").Data, "you"); you["rank"] != 1.0 || you["score"] != vasyaScore {
		t.Fatalf("итог Васи = %v", you)
	}
	if you := sub(t, expect(t, petya, "game_over").Data, "you"); you["rank"] != 2.0 {
		t.Fatalf("итог Пети = %v", you)
	}
	for _, c := range []*websocket.Conn{host, vasya, petya} {
		expectClose(t, c, websocket.CloseNormalClosure)
	}
	eventually(t, "сессия завершена и комната убрана", func() bool {
		_, err := e.store.GetActive(context.Background(), code)
		return errors.Is(err, session.ErrNotFound) && e.rooms.Get(code) == nil
	})
}

func TestGameErrors(t *testing.T) {
	e := newWSEnvWith(t, gameTimeouts)
	code, host := openRoom(t, e)

	send(t, host, start)
	skipError(t, host, "invalid_state") // нет игроков
	send(t, host, next)
	skipError(t, host, "invalid_state") // ещё лобби

	vasya := joinPlayer(t, e, code, "Вася")
	petya := joinPlayer(t, e, code, "Петя")
	silent := e.mustDial(t, code, "") // подключился, но не вошёл

	send(t, vasya, start)
	skipError(t, vasya, "not_allowed")
	send(t, vasya, next)
	skipError(t, vasya, "not_allowed")
	send(t, vasya, answerMsg(0, 18))
	skipError(t, vasya, "invalid_state") // вопроса ещё нет

	send(t, host, start)
	// Не успевший войти отключается.
	skipError(t, silent, "game_already_started")
	expectClose(t, silent, websocket.CloseNormalClosure)

	skipTo(t, host, "question")
	skipTo(t, vasya, "question")
	skipTo(t, petya, "question")

	send(t, host, answerMsg(0, 18))
	skipError(t, host, "not_allowed")
	send(t, host, next)
	skipError(t, host, "invalid_state") // вопрос ещё идёт
	send(t, host, start)
	skipError(t, host, "invalid_state")

	send(t, vasya, answerMsg(0, 999))
	skipError(t, vasya, "bad_message") // нет такого варианта
	send(t, vasya, `{"type": "answer", "data": {"option_id": 18}}`)
	skipError(t, vasya, "bad_message") // нет question_index

	// Ответ на «другой» вопрос молча отбрасывается: следующим придёт
	// подтверждение уже правильного ответа.
	send(t, vasya, answerMsg(5, 18))
	send(t, vasya, answerMsg(0, 18))
	expect(t, vasya, "answer_accepted")
	send(t, vasya, answerMsg(0, 17))
	skipError(t, vasya, "already_answered")

	// Новый игрок во время игры подключиться может, а войти — нет.
	late := e.mustDial(t, code, "")
	send(t, late, joinMsg("Опоздавший"))
	skipError(t, late, "game_already_started")
	expectClose(t, late, websocket.CloseNormalClosure)
}

func TestGamePlayerLeaves(t *testing.T) {
	e := newWSEnvWith(t, gameTimeouts)
	code, host := openRoom(t, e)
	vasya := joinPlayer(t, e, code, "Вася")
	petya := joinPlayer(t, e, code, "Петя")

	send(t, host, start)
	skipTo(t, host, "question")
	skipTo(t, vasya, "question")
	skipTo(t, petya, "question")

	send(t, vasya, answerMsg(0, 18))
	expect(t, vasya, "answer_accepted")
	expect(t, host, "answer_progress") // 1 из 2

	// Петя выбывает. Все оставшиеся уже ответили — результат сразу.
	petya.Close()
	left := skipTo(t, host, "player_left")
	if left.Data["nickname"] != "Петя" {
		t.Fatalf("player_left = %v", left.Data)
	}
	if p := expect(t, host, "answer_progress"); p.Data["answered"] != 1.0 || p.Data["total"] != 1.0 {
		t.Fatalf("после выбывания answer_progress = %v", p.Data)
	}
	r := expect(t, host, "question_result")
	if board := entries(t, r.Data); len(board) != 1 || board[0]["nickname"] != "Вася" {
		t.Fatalf("в таблице только оставшиеся: %v", board)
	}
	skipTo(t, vasya, "player_left")
	expect(t, vasya, "question_result")

	// Доигрываем: Вася отвечает и на второй вопрос.
	send(t, host, next)
	skipTo(t, host, "question")
	skipTo(t, vasya, "question")
	send(t, vasya, answerMsg(1, 19))
	expect(t, vasya, "answer_accepted")
	skipTo(t, host, "question_result")
	expect(t, vasya, "question_result")
	send(t, host, next)

	// В итогах есть и выбывший — с пометкой left, его место считается со всеми.
	for _, c := range []*websocket.Conn{host, vasya} {
		board := entries(t, skipTo(t, c, "game_over").Data)
		if len(board) != 2 {
			t.Fatalf("в итогах должны быть все, кто играл: %v", board)
		}
		if board[0]["nickname"] != "Вася" || board[0]["rank"] != 1.0 {
			t.Fatalf("первое место: %v", board[0])
		}
		if _, has := board[0]["left"]; has {
			t.Fatalf("у оставшегося не должно быть left: %v", board[0])
		}
		if board[1]["nickname"] != "Петя" || board[1]["rank"] != 2.0 || board[1]["left"] != true || board[1]["score"] != 0.0 {
			t.Fatalf("выбывший: %v", board[1])
		}
	}
}

func TestGameHostLeaves(t *testing.T) {
	e := newWSEnvWith(t, gameTimeouts)
	code, host := openRoom(t, e)
	vasya := joinPlayer(t, e, code, "Вася")
	send(t, host, start)
	skipTo(t, vasya, "question")

	// Ведущий ушёл во время игры — комната отменяется.
	host.Close()
	if m := skipTo(t, vasya, "room_closed"); m.Data["reason"] != "host_left" {
		t.Fatalf("room_closed = %v", m.Data)
	}
	expectClose(t, vasya, websocket.CloseNormalClosure)
}
