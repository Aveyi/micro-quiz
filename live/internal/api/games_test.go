package api

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Aveyi/micro-quiz/live/internal/auth"
	"github.com/Aveyi/micro-quiz/live/internal/session"
)

// historyServer — ручки истории поверх хранилища с одной доигранной игрой
// ведущего 1 и одной игрой ведущего 2.
func historyServer(t *testing.T) (srv *httptest.Server, played, foreign int64) {
	t.Helper()
	ctx := context.Background()
	st := session.NewMemoryStore()

	g, _ := st.Create(ctx, session.Session{RoomCode: "100001", QuizID: 3, QuizTitle: "Столицы мира", HostUserID: 1})
	a, _ := st.AddPlayer(ctx, g.ID, "Вася")
	b, _ := st.AddPlayer(ctx, g.ID, "Петя")
	st.SetStatus(ctx, g.ID, session.StatusRunning)
	st.SaveAnswers(ctx, g.ID, []session.Answer{
		{PlayerID: a, QuestionIndex: 0, QuestionID: 41, OptionID: 18, IsCorrect: true, ResponseMs: 900, Points: 980},
		{PlayerID: b, QuestionIndex: 0, QuestionID: 41},
	})
	st.Finish(ctx, g.ID, []session.Result{{PlayerID: a, Score: 980, Rank: 1}, {PlayerID: b, Score: 0, Rank: 2}})
	other, _ := st.Create(ctx, session.Session{RoomCode: "100002", QuizID: 5, QuizTitle: "Чужая", HostUserID: 2})

	h := &Games{Auth: auth.NewVerifier(secret), Store: st, Log: slog.New(slog.NewTextHandler(io.Discard, nil))}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /live/api/games", h.List)
	mux.HandleFunc("GET /live/api/games/{id}", h.Get)
	srv = httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	return srv, g.ID, other.ID
}

func get(t *testing.T, url, token string, out any) int {
	t.Helper()
	req, _ := http.NewRequest("GET", url, nil)
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if err := json.NewDecoder(resp.Body).Decode(out); err != nil {
		t.Fatalf("ответ не JSON: %v", err)
	}
	return resp.StatusCode
}

func TestGamesList(t *testing.T) {
	srv, played, _ := historyServer(t)

	var games []map[string]any
	if code := get(t, srv.URL+"/live/api/games", tokenFor(t, "1"), &games); code != 200 {
		t.Fatalf("код %d", code)
	}
	if len(games) != 1 {
		t.Fatalf("ожидали только свою игру, получили %v", games)
	}
	g := games[0]
	if g["id"] != float64(played) || g["quiz_title"] != "Столицы мира" || g["status"] != "finished" || g["player_count"] != 2.0 {
		t.Fatalf("игра %v", g)
	}
	for _, k := range []string{"created_at", "started_at", "finished_at"} {
		if _, ok := g[k].(string); !ok {
			t.Fatalf("%s = %#v, ожидали время строкой", k, g[k])
		}
	}

	// У ведущего без игр — пустой массив, а не null.
	var none []map[string]any
	get(t, srv.URL+"/live/api/games", tokenFor(t, "42"), &none)
	if none == nil || len(none) != 0 {
		t.Fatalf("ожидали [], получили %#v", none)
	}

	var e map[string]string
	if code := get(t, srv.URL+"/live/api/games", "", &e); code != 401 || e["error"] == "" {
		t.Fatalf("без токена: %d %v", code, e)
	}
}

func TestGamesGet(t *testing.T) {
	srv, played, foreign := historyServer(t)
	url := func(id any) string { return srv.URL + "/live/api/games/" + toString(id) }

	var g map[string]any
	if code := get(t, url(played), tokenFor(t, "1"), &g); code != 200 {
		t.Fatalf("код %d", code)
	}
	if g["quiz_title"] != "Столицы мира" || g["player_count"] != 2.0 {
		t.Fatalf("игра %v", g)
	}
	players := g["players"].([]any)
	first := players[0].(map[string]any)
	if len(players) != 2 || first["nickname"] != "Вася" || first["rank"] != 1.0 || first["score"] != 980.0 || first["left"] != false {
		t.Fatalf("игроки %v", players)
	}
	q := g["questions"].([]any)[0].(map[string]any)
	if q["question_index"] != 0.0 || q["total"] != 2.0 || q["answered"] != 1.0 || q["correct"] != 1.0 || q["correct_ratio"] != 0.5 {
		t.Fatalf("вопрос %v", q)
	}

	// Чужая, несуществующая и «не число» — одинаково 404.
	for _, id := range []any{foreign, 999999, "abc", 0} {
		var e map[string]string
		if code := get(t, url(id), tokenFor(t, "1"), &e); code != 404 || e["error"] == "" {
			t.Fatalf("id %v: %d %v", id, code, e)
		}
	}
	var e map[string]string
	if code := get(t, url(played), "", &e); code != 401 {
		t.Fatalf("без токена: %d", code)
	}
}

func toString(v any) string {
	b, _ := json.Marshal(v)
	if s, ok := v.(string); ok {
		return s
	}
	return string(b)
}
