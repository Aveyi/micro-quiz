package game

import (
	"reflect"
	"testing"
	"time"
)

func TestPoints(t *testing.T) {
	limit := 20 * time.Second
	tests := []struct {
		elapsed time.Duration
		want    int
	}{
		{0, 1000},                      // мгновенно
		{limit, 500},                   // в последний момент
		{limit / 2, 750},               // посередине
		{5 * time.Second, 875},         // 1000 × (1 − 5/40)
		{-time.Second, 1000},           // защита от отрицательного времени
		{2 * limit, 500},               // позже лимита — не меньше 500
		{1234 * time.Millisecond, 969}, // round(969.15)
	}
	for _, tt := range tests {
		if got := points(tt.elapsed, limit); got != tt.want {
			t.Errorf("points(%v) = %d, ожидали %d", tt.elapsed, got, tt.want)
		}
	}
}

func TestRanking(t *testing.T) {
	// playerID — порядок входа.
	a := &Client{playerID: 1, nickname: "А", score: 900}
	b := &Client{playerID: 2, nickname: "Б", score: 1500}
	c := &Client{playerID: 3, nickname: "В", score: 900}
	d := &Client{playerID: 4, nickname: "Г", score: 0}
	players := []*Client{a, b, c, d}

	rs := ranking(players)
	var got []string
	var ranks []int
	for _, r := range rs {
		got = append(got, r.client.nickname)
		ranks = append(ranks, r.rank)
	}
	// Равные очки — одно место, следующее место пропускается («1, 2, 2, 4»);
	// при равенстве выше тот, кто вошёл раньше.
	if !reflect.DeepEqual(got, []string{"Б", "А", "В", "Г"}) || !reflect.DeepEqual(ranks, []int{1, 2, 2, 4}) {
		t.Fatalf("порядок %v, места %v", got, ranks)
	}
	if players[0] != a {
		t.Fatal("ranking изменил исходный срез")
	}

	if top := leaderboard(rs, 2); len(top) != 2 || top[1].Nickname != "А" || top[1].Rank != 2 {
		t.Fatalf("leaderboard(2) = %+v", top)
	}
	if all := leaderboard(rs, 10); len(all) != 4 {
		t.Fatalf("leaderboard(10) = %d записей, ожидали 4", len(all))
	}
}
