package session

import (
	"context"
	"errors"
	"sync"
	"testing"
)

// testStore — проверки, одинаковые для любой реализации Store. Их гоняем
// и на памяти, и на PostgreSQL: так видно, что реализации взаимозаменяемы.
func testStore(t *testing.T, newStore func(t *testing.T) Store) {
	ctx := context.Background()

	t.Run("создание и поиск", func(t *testing.T) {
		st := newStore(t)
		s, err := st.Create(ctx, Session{RoomCode: "482913", QuizID: 3, QuizTitle: "Столицы мира", HostUserID: 1})
		if err != nil {
			t.Fatal(err)
		}
		if s.ID == 0 || s.Status != StatusLobby || s.CreatedAt.IsZero() {
			t.Fatalf("сессия %+v", s)
		}
		got, err := st.GetActive(ctx, "482913")
		if err != nil {
			t.Fatal(err)
		}
		if got.ID != s.ID || got.QuizID != 3 || got.QuizTitle != "Столицы мира" || got.HostUserID != 1 || got.Status != StatusLobby {
			t.Fatalf("нашли %+v, создавали %+v", got, s)
		}
		if _, err := st.GetActive(ctx, "000000"); !errors.Is(err, ErrNotFound) {
			t.Fatalf("несуществующий код: %v", err)
		}
	})

	t.Run("код занят, пока комната активна", func(t *testing.T) {
		st := newStore(t)
		s, _ := st.Create(ctx, Session{RoomCode: "111111", QuizID: 3, QuizTitle: "x", HostUserID: 1})
		if _, err := st.Create(ctx, Session{RoomCode: "111111", QuizID: 3, QuizTitle: "x", HostUserID: 1}); !errors.Is(err, ErrCodeTaken) {
			t.Fatalf("в лобби: ожидали ErrCodeTaken, получили %v", err)
		}
		st.SetStatus(ctx, s.ID, StatusRunning)
		if _, err := st.Create(ctx, Session{RoomCode: "111111", QuizID: 3, QuizTitle: "x", HostUserID: 1}); !errors.Is(err, ErrCodeTaken) {
			t.Fatalf("в игре: ожидали ErrCodeTaken, получили %v", err)
		}
		if got, _ := st.GetActive(ctx, "111111"); got.Status != StatusRunning {
			t.Fatalf("статус %q", got.Status)
		}

		// Игра закончилась — код свободен, а старая сессия по коду не ищется.
		if err := st.SetStatus(ctx, s.ID, StatusFinished); err != nil {
			t.Fatal(err)
		}
		if _, err := st.GetActive(ctx, "111111"); !errors.Is(err, ErrNotFound) {
			t.Fatalf("завершённая нашлась: %v", err)
		}
		s2, err := st.Create(ctx, Session{RoomCode: "111111", QuizID: 4, QuizTitle: "y", HostUserID: 2})
		if err != nil || s2.ID == s.ID {
			t.Fatalf("повторное использование кода: %+v, %v", s2, err)
		}
	})

	t.Run("неизвестная сессия", func(t *testing.T) {
		if err := newStore(t).SetStatus(ctx, 999999, StatusFinished); !errors.Is(err, ErrNotFound) {
			t.Fatalf("ожидали ErrNotFound, получили %v", err)
		}
	})

	t.Run("игроки: ник уникален без учёта регистра", func(t *testing.T) {
		st := newStore(t)
		s, _ := st.Create(ctx, Session{RoomCode: "222222", QuizID: 3, QuizTitle: "x", HostUserID: 1})
		other, _ := st.Create(ctx, Session{RoomCode: "333333", QuizID: 3, QuizTitle: "x", HostUserID: 1})

		vasya, err := st.AddPlayer(ctx, s.ID, "Вася")
		if err != nil || vasya == 0 {
			t.Fatalf("AddPlayer: %d, %v", vasya, err)
		}
		// Кириллица в другом регистре: проверяет и локаль БД (lower() для UTF-8).
		if _, err := st.AddPlayer(ctx, s.ID, "ВАСЯ"); !errors.Is(err, ErrNicknameTaken) {
			t.Fatalf("ВАСЯ: ожидали ErrNicknameTaken, получили %v", err)
		}
		// В другой сессии тот же ник свободен.
		if _, err := st.AddPlayer(ctx, other.ID, "Вася"); err != nil {
			t.Fatalf("другая сессия: %v", err)
		}

		// Вышел из лобби — ник освободился.
		if err := st.RemovePlayer(ctx, vasya); err != nil {
			t.Fatal(err)
		}
		vasya2, err := st.AddPlayer(ctx, s.ID, "вася")
		if err != nil || vasya2 == vasya {
			t.Fatalf("после выхода из лобби: %d, %v", vasya2, err)
		}

		// Выбыл во время игры — ник остаётся занятым: запись нужна истории.
		if err := st.MarkLeft(ctx, vasya2); err != nil {
			t.Fatal(err)
		}
		if _, err := st.AddPlayer(ctx, s.ID, "Вася"); !errors.Is(err, ErrNicknameTaken) {
			t.Fatalf("после выбывания: ожидали ErrNicknameTaken, получили %v", err)
		}
	})

	t.Run("ответы и итоги", func(t *testing.T) {
		st := newStore(t)
		s, _ := st.Create(ctx, Session{RoomCode: "444444", QuizID: 3, QuizTitle: "x", HostUserID: 1})
		a, _ := st.AddPlayer(ctx, s.ID, "А")
		b, _ := st.AddPlayer(ctx, s.ID, "Б")
		st.SetStatus(ctx, s.ID, StatusRunning)

		q0 := []Answer{
			{PlayerID: a, QuestionIndex: 0, QuestionID: 41, OptionID: 18, IsCorrect: true, ResponseMs: 1200, Points: 970},
			{PlayerID: b, QuestionIndex: 0, QuestionID: 41}, // не ответил
		}
		if err := st.SaveAnswers(ctx, s.ID, q0); err != nil {
			t.Fatal(err)
		}
		if err := st.SaveAnswers(ctx, s.ID, nil); err != nil {
			t.Fatalf("пустой пакет: %v", err)
		}

		// Повтор ответа на тот же вопрос — ошибка, и весь пакет не пишется:
		// новый ответ Б на вопрос 1 тоже не должен сохраниться.
		bad := []Answer{
			{PlayerID: b, QuestionIndex: 1, QuestionID: 42, OptionID: 19, IsCorrect: true, ResponseMs: 500, Points: 990},
			{PlayerID: a, QuestionIndex: 0, QuestionID: 41, OptionID: 17},
		}
		if err := st.SaveAnswers(ctx, s.ID, bad); err == nil {
			t.Fatal("повторный ответ на вопрос 0 должен быть ошибкой")
		}
		retry := []Answer{{PlayerID: b, QuestionIndex: 1, QuestionID: 42, OptionID: 19, IsCorrect: true, ResponseMs: 500, Points: 990}}
		if err := st.SaveAnswers(ctx, s.ID, retry); err != nil {
			t.Fatalf("ответ Б на вопрос 1 после отката: %v", err)
		}

		if err := st.Finish(ctx, s.ID, []Result{{PlayerID: b, Score: 990, Rank: 1}, {PlayerID: a, Score: 970, Rank: 2}}); err != nil {
			t.Fatal(err)
		}
		if _, err := st.GetActive(ctx, "444444"); !errors.Is(err, ErrNotFound) {
			t.Fatalf("после Finish сессия не должна быть активной: %v", err)
		}
	})

	t.Run("история игр", func(t *testing.T) {
		st := newStore(t)
		// У ведущего 1: пустое отменённое лобби и доигранная игра; у ведущего 2 — своя.
		empty, _ := st.Create(ctx, Session{RoomCode: "100001", QuizID: 3, QuizTitle: "Пустая", HostUserID: 1})
		st.SetStatus(ctx, empty.ID, StatusCancelled)
		played, _ := st.Create(ctx, Session{RoomCode: "100002", QuizID: 4, QuizTitle: "Столицы", HostUserID: 1})
		st.Create(ctx, Session{RoomCode: "100003", QuizID: 5, QuizTitle: "Чужая", HostUserID: 2})

		a, _ := st.AddPlayer(ctx, played.ID, "А")
		b, _ := st.AddPlayer(ctx, played.ID, "Б")
		c, _ := st.AddPlayer(ctx, played.ID, "В")
		st.SetStatus(ctx, played.ID, StatusRunning)
		st.SaveAnswers(ctx, played.ID, []Answer{
			{PlayerID: a, QuestionIndex: 0, QuestionID: 41, OptionID: 18, IsCorrect: true, ResponseMs: 900, Points: 980},
			{PlayerID: b, QuestionIndex: 0, QuestionID: 41, OptionID: 17, ResponseMs: 1500},
			{PlayerID: c, QuestionIndex: 0, QuestionID: 41}, // не ответил
		})
		st.MarkLeft(ctx, c)
		st.SaveAnswers(ctx, played.ID, []Answer{
			{PlayerID: a, QuestionIndex: 1, QuestionID: 42, OptionID: 19, IsCorrect: true, ResponseMs: 700, Points: 990},
			{PlayerID: b, QuestionIndex: 1, QuestionID: 42, OptionID: 19, IsCorrect: true, ResponseMs: 800, Points: 985},
		})
		st.Finish(ctx, played.ID, []Result{{PlayerID: a, Score: 1970, Rank: 1}, {PlayerID: b, Score: 985, Rank: 2}, {PlayerID: c, Score: 0, Rank: 3}})

		games, err := st.ListGames(ctx, 1, 10)
		if err != nil {
			t.Fatal(err)
		}
		if len(games) != 2 || games[0].ID != played.ID || games[1].ID != empty.ID {
			t.Fatalf("ожидали [доигранная, пустая] новые сверху, получили %+v", games)
		}
		if games[0].PlayerCount != 3 || games[1].PlayerCount != 0 {
			t.Fatalf("player_count: %d и %d", games[0].PlayerCount, games[1].PlayerCount)
		}
		if g := games[0]; g.Status != StatusFinished || g.StartedAt == nil || g.FinishedAt == nil || g.QuizTitle != "Столицы" {
			t.Fatalf("доигранная: %+v", g)
		}
		if g := games[1]; g.Status != StatusCancelled || g.StartedAt != nil || g.FinishedAt == nil {
			t.Fatalf("отменённое лобби: %+v", g)
		}
		if one, _ := st.ListGames(ctx, 1, 1); len(one) != 1 || one[0].ID != played.ID {
			t.Fatalf("limit 1: %+v", one)
		}
		if none, err := st.ListGames(ctx, 42, 10); err != nil || len(none) != 0 {
			t.Fatalf("у ведущего без игр: %+v, %v", none, err)
		}

		g, err := st.GetGame(ctx, played.ID)
		if err != nil {
			t.Fatal(err)
		}
		if g.HostUserID != 1 || len(g.Players) != 3 {
			t.Fatalf("игра %+v", g)
		}
		for i, want := range []struct {
			nick        string
			score, rank int
			left        bool
		}{{"А", 1970, 1, false}, {"Б", 985, 2, false}, {"В", 0, 3, true}} {
			p := g.Players[i]
			if p.Nickname != want.nick || p.Score == nil || *p.Score != want.score || *p.Rank != want.rank || p.Left != want.left {
				t.Fatalf("игрок %d: %+v, ожидали %+v", i, p, want)
			}
		}
		wantQ := []QuestionStats{
			{QuestionIndex: 0, QuestionID: 41, Total: 3, Answered: 2, Correct: 1},
			{QuestionIndex: 1, QuestionID: 42, Total: 2, Answered: 2, Correct: 2},
		}
		if len(g.Questions) != 2 || g.Questions[0] != wantQ[0] || g.Questions[1] != wantQ[1] {
			t.Fatalf("вопросы %+v, ожидали %+v", g.Questions, wantQ)
		}

		// Незаконченная игра: игроки есть, итогов нет.
		lobby, _ := st.Create(ctx, Session{RoomCode: "100004", QuizID: 3, QuizTitle: "x", HostUserID: 1})
		st.AddPlayer(ctx, lobby.ID, "Г")
		if g, _ := st.GetGame(ctx, lobby.ID); len(g.Players) != 1 || g.Players[0].Rank != nil || len(g.Questions) != 0 {
			t.Fatalf("лобби: %+v", g)
		}
		if _, err := st.GetGame(ctx, 999999); !errors.Is(err, ErrNotFound) {
			t.Fatalf("нет игры: %v", err)
		}
	})

	t.Run("гонка за один код", func(t *testing.T) {
		// Десять «инстансов» одновременно пытаются создать комнату с одним
		// кодом. Ровно один должен успеть, остальные — получить ErrCodeTaken.
		st := newStore(t)
		var wg sync.WaitGroup
		var mu sync.Mutex
		ok, taken := 0, 0
		for range 10 {
			wg.Go(func() {
				_, err := st.Create(ctx, Session{RoomCode: "777777", QuizID: 3, QuizTitle: "x", HostUserID: 1})
				mu.Lock()
				defer mu.Unlock()
				switch {
				case err == nil:
					ok++
				case errors.Is(err, ErrCodeTaken):
					taken++
				default:
					t.Errorf("неожиданная ошибка: %v", err)
				}
			})
		}
		wg.Wait()
		if ok != 1 || taken != 9 {
			t.Fatalf("успешно %d, занято %d; ожидали 1 и 9", ok, taken)
		}
	})
}

func TestMemoryStore(t *testing.T) {
	testStore(t, func(*testing.T) Store { return NewMemoryStore() })
}
