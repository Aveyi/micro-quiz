package game

import (
	"math"
	"slices"
	"time"
)

// points — очки за правильный ответ (docs/quiz-design.md, раздел 2):
// мгновенно — 1000, в последний момент — 500, между ними линейно.
func points(elapsed, limit time.Duration) int {
	elapsed = min(max(elapsed, 0), limit)
	return int(math.Round(1000 * (1 - float64(elapsed)/float64(2*limit))))
}

type ranked struct {
	client *Client
	rank   int
}

// ranking сортирует игроков по очкам. Одинаковые очки — одно место
// («1, 1, 3»: так считают в спорте); при равенстве выше тот, кто раньше
// вошёл, чтобы порядок в таблице не прыгал от вопроса к вопросу.
func ranking(players []*Client) []ranked {
	sorted := slices.Clone(players) // не портим порядок входа в r.players
	slices.SortFunc(sorted, func(a, b *Client) int {
		if a.score != b.score {
			return b.score - a.score // по убыванию очков
		}
		return int(a.playerID - b.playerID)
	})

	out := make([]ranked, len(sorted))
	for i, c := range sorted {
		rank := i + 1
		if i > 0 && c.score == sorted[i-1].score {
			rank = out[i-1].rank
		}
		out[i] = ranked{client: c, rank: rank}
	}
	return out
}

// leaderboard превращает рейтинг в таблицу для клиента, не длиннее limit.
func leaderboard(rs []ranked, limit int) []leaderEntry {
	rs = rs[:min(len(rs), limit)]
	out := make([]leaderEntry, 0, len(rs))
	for _, r := range rs {
		out = append(out, leaderEntry{
			Rank:     r.rank,
			PlayerID: r.client.playerID,
			Nickname: r.client.nickname,
			Score:    r.client.score,
			Left:     r.client.left,
		})
	}
	return out
}
