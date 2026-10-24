package session

import (
	"context"
	"os"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// Тесты на настоящей PostgreSQL. Без TEST_DATABASE_URL они пропускаются,
// поэтому go test работает и без БД. Схему live тесты ПЕРЕСОЗДАЮТ:
// не указывайте БД с нужными данными. Та же договорённость, что у content.
//
//	TEST_DATABASE_URL=postgres://postgres:pw@localhost:5432/quiz go test ./...

const migration = "../../../deploy/migrations/0002_live_init.up.sql"

// testDB пересоздаёт схему live по настоящей миграции и возвращает пул.
func testDB(t *testing.T) *pgxpool.Pool {
	t.Helper()
	url := os.Getenv("TEST_DATABASE_URL")
	if url == "" {
		t.Skip("TEST_DATABASE_URL не задан — тесты на PostgreSQL пропущены")
	}
	ctx := context.Background()
	db, err := pgxpool.New(ctx, url)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(db.Close)

	sql, err := os.ReadFile(migration)
	if err != nil {
		t.Fatal(err)
	}
	// Exec без параметров разрешает несколько команд в одной строке.
	if _, err := db.Exec(ctx, "DROP SCHEMA IF EXISTS live CASCADE; CREATE SCHEMA live;"); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(ctx, string(sql)); err != nil {
		t.Fatalf("миграция: %v", err)
	}
	return db
}

func TestPostgresStore(t *testing.T) {
	testStore(t, func(t *testing.T) Store { return NewPostgresStore(testDB(t)) })
}

func TestPostgresStoreTimestamps(t *testing.T) {
	db := testDB(t)
	st := NewPostgresStore(db)
	ctx := context.Background()

	s, err := st.Create(ctx, Session{RoomCode: "123456", QuizID: 3, QuizTitle: "x", HostUserID: 1})
	if err != nil {
		t.Fatal(err)
	}
	times := func() (started, finished *time.Time) {
		t.Helper()
		if err := db.QueryRow(ctx, `SELECT started_at, finished_at FROM live.game_sessions WHERE id = $1`, s.ID).
			Scan(&started, &finished); err != nil {
			t.Fatal(err)
		}
		return
	}

	if started, finished := times(); started != nil || finished != nil {
		t.Fatal("в лобби started_at и finished_at должны быть пустыми")
	}
	st.SetStatus(ctx, s.ID, StatusRunning)
	started, finished := times()
	if started == nil || finished != nil {
		t.Fatal("после start должен появиться только started_at")
	}
	st.SetStatus(ctx, s.ID, StatusFinished)
	started2, finished := times()
	if finished == nil || !started2.Equal(*started) {
		t.Fatal("после конца игры: finished_at появился, started_at не изменился")
	}
}

// TestPostgresRows проверяет, что именно легло в таблицы: NULL у
// неответившего, итоги, left_at, статус и время конца.
func TestPostgresRows(t *testing.T) {
	db := testDB(t)
	st := NewPostgresStore(db)
	ctx := context.Background()

	s, _ := st.Create(ctx, Session{RoomCode: "555555", QuizID: 3, QuizTitle: "x", HostUserID: 1})
	a, _ := st.AddPlayer(ctx, s.ID, "А")
	b, _ := st.AddPlayer(ctx, s.ID, "Б")
	st.SetStatus(ctx, s.ID, StatusRunning)
	st.SaveAnswers(ctx, s.ID, []Answer{
		{PlayerID: a, QuestionIndex: 0, QuestionID: 41, OptionID: 18, IsCorrect: true, ResponseMs: 1200, Points: 970},
		{PlayerID: b, QuestionIndex: 0, QuestionID: 41},
	})
	st.MarkLeft(ctx, b)
	if err := st.Finish(ctx, s.ID, []Result{{PlayerID: a, Score: 970, Rank: 1}, {PlayerID: b, Score: 0, Rank: 2}}); err != nil {
		t.Fatal(err)
	}

	var option *int64
	var ms *int
	var correct bool
	if err := db.QueryRow(ctx, `SELECT option_id, response_ms, is_correct FROM live.player_answers WHERE player_id = $1`, b).
		Scan(&option, &ms, &correct); err != nil {
		t.Fatal(err)
	}
	if option != nil || ms != nil || correct {
		t.Fatalf("у неответившего ожидали NULL, NULL, false; получили %v, %v, %v", option, ms, correct)
	}
	if err := db.QueryRow(ctx, `SELECT option_id, response_ms FROM live.player_answers WHERE player_id = $1`, a).
		Scan(&option, &ms); err != nil || *option != 18 || *ms != 1200 {
		t.Fatalf("ответ А: %v, %v, %v", option, ms, err)
	}

	var score, rank int
	var left bool
	if err := db.QueryRow(ctx, `SELECT final_score, final_rank, left_at IS NOT NULL FROM live.session_players WHERE id = $1`, b).
		Scan(&score, &rank, &left); err != nil || score != 0 || rank != 2 || !left {
		t.Fatalf("итог Б: score=%d rank=%d left=%v err=%v", score, rank, left, err)
	}

	var status string
	var finished bool
	db.QueryRow(ctx, `SELECT status, finished_at IS NOT NULL FROM live.game_sessions WHERE id = $1`, s.ID).Scan(&status, &finished)
	if status != "finished" || !finished {
		t.Fatalf("сессия: status=%s finished_at=%v", status, finished)
	}
}
