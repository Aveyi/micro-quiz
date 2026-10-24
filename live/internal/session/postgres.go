package session

import (
	"context"
	"errors"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

// PostgresStore хранит сессии в таблице live.game_sessions. Её видят все
// инстансы live: комнату создали на одном, а ведущий подключился к другому.
type PostgresStore struct {
	db *pgxpool.Pool
}

func NewPostgresStore(db *pgxpool.Pool) *PostgresStore {
	return &PostgresStore{db: db}
}

// uniqueViolation — код ошибки PostgreSQL «нарушена уникальность».
const uniqueViolation = "23505"

func (p *PostgresStore) Create(ctx context.Context, s Session) (Session, error) {
	// Значения подставляются параметрами $1, $2…, а не склейкой строк:
	// драйвер передаёт их отдельно от текста запроса, и SQL-инъекция
	// невозможна в принципе.
	err := p.db.QueryRow(ctx, `
		INSERT INTO live.game_sessions (room_code, quiz_id, quiz_title, host_user_id)
		VALUES ($1, $2, $3, $4)
		RETURNING id, status, created_at`,
		s.RoomCode, s.QuizID, s.QuizTitle, s.HostUserID,
	).Scan(&s.ID, &s.Status, &s.CreatedAt)

	// Занятость кода проверяет сама БД индексом active_room_code. Проверять
	// заранее SELECT-ом нельзя: между SELECT и INSERT другой инстанс успел
	// бы занять тот же код (гонка check-then-act).
	var pgErr *pgconn.PgError
	if errors.As(err, &pgErr) && pgErr.Code == uniqueViolation && pgErr.ConstraintName == "active_room_code" {
		return Session{}, ErrCodeTaken
	}
	if err != nil {
		return Session{}, err
	}
	s.CreatedAt = s.CreatedAt.UTC()
	return s, nil
}

func (p *PostgresStore) GetActive(ctx context.Context, code string) (Session, error) {
	var s Session
	err := p.db.QueryRow(ctx, `
		SELECT id, room_code, quiz_id, quiz_title, host_user_id, status, created_at, started_at, finished_at
		FROM live.game_sessions
		WHERE room_code = $1 AND status IN ('lobby', 'running')`,
		code,
	).Scan(&s.ID, &s.RoomCode, &s.QuizID, &s.QuizTitle, &s.HostUserID, &s.Status, &s.CreatedAt, &s.StartedAt, &s.FinishedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return Session{}, ErrNotFound
	}
	if err != nil {
		return Session{}, err
	}
	s.CreatedAt = s.CreatedAt.UTC()
	return s, nil
}

// SetStatus меняет статус и заодно ставит время начала или конца игры.
func (p *PostgresStore) SetStatus(ctx context.Context, id int64, status Status) error {
	tag, err := p.db.Exec(ctx, `
		UPDATE live.game_sessions
		SET status      = $2,
		    started_at  = CASE WHEN $2 = 'running' THEN now() ELSE started_at END,
		    finished_at = CASE WHEN $2 IN ('finished', 'cancelled') THEN now() ELSE finished_at END
		WHERE id = $1`,
		id, string(status),
	)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (p *PostgresStore) AddPlayer(ctx context.Context, sessionID int64, nickname string) (int64, error) {
	var id int64
	err := p.db.QueryRow(ctx, `
		INSERT INTO live.session_players (session_id, nickname)
		VALUES ($1, $2)
		RETURNING id`,
		sessionID, nickname,
	).Scan(&id)
	var pgErr *pgconn.PgError
	if errors.As(err, &pgErr) && pgErr.Code == uniqueViolation && pgErr.ConstraintName == "unique_nickname_in_session" {
		return 0, ErrNicknameTaken
	}
	return id, err
}

func (p *PostgresStore) RemovePlayer(ctx context.Context, playerID int64) error {
	_, err := p.db.Exec(ctx, `DELETE FROM live.session_players WHERE id = $1`, playerID)
	return err
}

func (p *PostgresStore) MarkLeft(ctx context.Context, playerID int64) error {
	_, err := p.db.Exec(ctx, `
		UPDATE live.session_players SET left_at = now()
		WHERE id = $1 AND left_at IS NULL`,
		playerID)
	return err
}

// SaveAnswers пишет все ответы на вопрос одной транзакцией и одним
// обращением к БД: pgx.Batch отправляет все INSERT разом, а не по одному
// с ожиданием ответа на каждый. Это и есть «пакетная запись в конце
// вопроса» из дизайна — в пиковый момент БД получает один запрос, а не 50.
func (p *PostgresStore) SaveAnswers(ctx context.Context, sessionID int64, answers []Answer) error {
	if len(answers) == 0 {
		return nil
	}
	// BeginFunc сам делает COMMIT, если функция вернула nil, и ROLLBACK,
	// если ошибку: забыть откатить транзакцию невозможно.
	return pgx.BeginFunc(ctx, p.db, func(tx pgx.Tx) error {
		batch := &pgx.Batch{}
		for _, a := range answers {
			var option, ms any // nil превращается в NULL
			if a.OptionID != 0 {
				option, ms = a.OptionID, a.ResponseMs
			}
			batch.Queue(`
				INSERT INTO live.player_answers
				    (session_id, player_id, question_index, question_id, option_id, is_correct, response_ms, points)
				VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
				sessionID, a.PlayerID, a.QuestionIndex, a.QuestionID, option, a.IsCorrect, ms, a.Points)
		}
		// Close дочитывает ответы на все запросы и возвращает первую ошибку.
		return tx.SendBatch(ctx, batch).Close()
	})
}

func (p *PostgresStore) Finish(ctx context.Context, sessionID int64, results []Result) error {
	return pgx.BeginFunc(ctx, p.db, func(tx pgx.Tx) error {
		batch := &pgx.Batch{}
		for _, r := range results {
			batch.Queue(`
				UPDATE live.session_players SET final_score = $2, final_rank = $3
				WHERE id = $1`,
				r.PlayerID, r.Score, r.Rank)
		}
		batch.Queue(`
			UPDATE live.game_sessions SET status = 'finished', finished_at = now()
			WHERE id = $1`,
			sessionID)
		return tx.SendBatch(ctx, batch).Close()
	})
}

func (p *PostgresStore) ListGames(ctx context.Context, hostUserID int64, limit int) ([]GameSummary, error) {
	// LEFT JOIN, а не JOIN: игра без игроков (отменили в пустом лобби)
	// тоже должна попасть в список — с player_count = 0.
	rows, err := p.db.Query(ctx, `
		SELECT s.id, s.room_code, s.quiz_id, s.quiz_title, s.host_user_id, s.status,
		       s.created_at, s.started_at, s.finished_at, count(pl.id)
		FROM live.game_sessions s
		LEFT JOIN live.session_players pl ON pl.session_id = s.id
		WHERE s.host_user_id = $1
		GROUP BY s.id
		ORDER BY s.created_at DESC, s.id DESC
		LIMIT $2`,
		hostUserID, limit)
	if err != nil {
		return nil, err
	}
	// CollectRows читает все строки и сам закрывает rows; забытый
	// rows.Close() держал бы соединение из пула занятым.
	games, err := pgx.CollectRows(rows, func(row pgx.CollectableRow) (GameSummary, error) {
		var g GameSummary
		err := row.Scan(&g.ID, &g.RoomCode, &g.QuizID, &g.QuizTitle, &g.HostUserID, &g.Status,
			&g.CreatedAt, &g.StartedAt, &g.FinishedAt, &g.PlayerCount)
		return g, err
	})
	if err != nil {
		return nil, err
	}
	return games, nil
}

func (p *PostgresStore) GetGame(ctx context.Context, id int64) (GameDetails, error) {
	var g GameDetails
	err := p.db.QueryRow(ctx, `
		SELECT id, room_code, quiz_id, quiz_title, host_user_id, status, created_at, started_at, finished_at
		FROM live.game_sessions WHERE id = $1`,
		id,
	).Scan(&g.ID, &g.RoomCode, &g.QuizID, &g.QuizTitle, &g.HostUserID, &g.Status, &g.CreatedAt, &g.StartedAt, &g.FinishedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return GameDetails{}, ErrNotFound
	}
	if err != nil {
		return GameDetails{}, err
	}

	rows, err := p.db.Query(ctx, `
		SELECT id, nickname, final_score, final_rank, left_at IS NOT NULL
		FROM live.session_players
		WHERE session_id = $1
		ORDER BY final_rank NULLS LAST, id`,
		id)
	if err != nil {
		return GameDetails{}, err
	}
	g.Players, err = pgx.CollectRows(rows, func(row pgx.CollectableRow) (PlayerResult, error) {
		var pr PlayerResult
		err := row.Scan(&pr.PlayerID, &pr.Nickname, &pr.Score, &pr.Rank, &pr.Left)
		return pr, err
	})
	if err != nil {
		return GameDetails{}, err
	}

	// Агрегаты считает БД: count(option_id) пропускает NULL (не ответил),
	// FILTER считает только верные.
	rows, err = p.db.Query(ctx, `
		SELECT question_index, question_id,
		       count(*), count(option_id), count(*) FILTER (WHERE is_correct)
		FROM live.player_answers
		WHERE session_id = $1
		GROUP BY question_index, question_id
		ORDER BY question_index`,
		id)
	if err != nil {
		return GameDetails{}, err
	}
	g.Questions, err = pgx.CollectRows(rows, func(row pgx.CollectableRow) (QuestionStats, error) {
		var q QuestionStats
		err := row.Scan(&q.QuestionIndex, &q.QuestionID, &q.Total, &q.Answered, &q.Correct)
		return q, err
	})
	if err != nil {
		return GameDetails{}, err
	}
	return g, nil
}
