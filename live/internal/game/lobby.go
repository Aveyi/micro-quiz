package game

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"time"
	"unicode"
	"unicode/utf8"

	"github.com/gorilla/websocket"

	"github.com/Aveyi/micro-quiz/live/internal/session"
)

const (
	maxPlayers     = 50
	maxNicknameLen = 20 // в символах, не в байтах
)

type joinData struct {
	Nickname string `json:"nickname"`
}

type lobbyUpdateData struct {
	Players []playerInfo `json:"players"`
}

// handleJoin — игрок входит в комнату с ником.
// Ошибки и что после них с соединением — docs/quiz-design.md, раздел 4.4.
func (r *Room) handleJoin(c *Client, raw json.RawMessage) {
	switch {
	case c.role == RoleHost:
		r.sendTo(c, errorMsg("not_allowed", "ведущий не входит в комнату как игрок"))
		return
	case c.playerID != 0:
		r.sendTo(c, errorMsg("invalid_state", "вы уже в комнате"))
		return
	case r.phase != phaseLobby:
		r.reject(c, "game_already_started", "игра уже началась")
		return
	case len(r.players) >= maxPlayers:
		r.reject(c, "room_full", "в комнате уже 50 игроков")
		return
	}

	var d joinData
	if err := json.Unmarshal(raw, &d); err != nil {
		r.sendTo(c, errorMsg("bad_message", "ожидали {\"nickname\": \"...\"}"))
		return
	}
	nick, ok := normalizeNickname(d.Nickname)
	if !ok {
		r.sendTo(c, errorMsg("invalid_nickname", "ник должен быть от 1 до 20 символов"))
		return
	}
	for _, p := range r.players {
		// Без учёта регистра: «Вася» и «вася» на экране не различить.
		// То же правило в БД: индекс по lower(nickname).
		if strings.EqualFold(p.nickname, nick) {
			r.sendTo(c, errorMsg("nickname_taken", "ник уже занят"))
			return
		}
	}

	// player_id выдаёт БД: это id строки в live.session_players.
	ctx, cancel := dbContext()
	id, err := r.store.AddPlayer(ctx, r.sess.ID, nick)
	cancel()
	switch {
	case errors.Is(err, session.ErrNicknameTaken):
		// Сюда попадаем, только если правила сравнения в Go и в БД
		// разошлись (lower() и EqualFold для редких символов). Индекс в
		// БД — последняя линия защиты.
		r.sendTo(c, errorMsg("nickname_taken", "ник уже занят"))
		return
	case err != nil:
		r.log.Error("не удалось записать игрока", "nickname", nick, "err", err)
		r.sendTo(c, errorMsg("server_error", "временная ошибка сервера, попробуйте ещё раз"))
		return
	}
	c.playerID, c.nickname = id, nick
	r.players = append(r.players, c)
	r.log.Info("игрок вошёл", "player_id", c.playerID, "nickname", nick, "players", len(r.players))

	list := r.playerList()
	r.sendTo(c, encode("joined", joinedData{
		Role:          RolePlayer,
		PlayerID:      c.playerID,
		RoomCode:      r.sess.RoomCode,
		QuizTitle:     r.quiz.Title,
		QuestionCount: len(r.quiz.Questions),
		Players:       list,
	}))
	r.broadcastMembers(encode("lobby_update", lobbyUpdateData{Players: list}))
}

// normalizeNickname обрезает пробелы по краям и проверяет ник.
func normalizeNickname(s string) (string, bool) {
	s = strings.TrimSpace(s)
	// len(s) считает байты, а кириллическая буква — это 2 байта в UTF-8.
	// «20 символов» — это 20 рун.
	n := utf8.RuneCountInString(s)
	if n == 0 || n > maxNicknameLen || !utf8.ValidString(s) {
		return "", false
	}
	for _, ch := range s {
		// Переводы строк и прочие управляющие символы сломали бы
		// таблицу лидеров на экране.
		if unicode.IsControl(ch) {
			return "", false
		}
	}
	return s, true
}

// reject отправляет ошибку и закрывает соединение (room_full, game_already_started).
func (r *Room) reject(c *Client, code, message string) {
	r.sendTo(c, errorMsg(code, message))
	r.disconnect(c, websocket.CloseNormalClosure, code)
}

func (r *Room) playerList() []playerInfo {
	list := make([]playerInfo, 0, len(r.players))
	for _, p := range r.players {
		list = append(list, playerInfo{PlayerID: p.playerID, Nickname: p.nickname})
	}
	return list
}

// removeGonePlayers убирает из списка игроков тех, кто отключился —
// сам или потому что не успевал читать. Вызывается после каждого события
// комнаты, а не внутри disconnect: disconnect бывает посреди рассылки,
// и новая рассылка оттуда запутала бы порядок сообщений.
func (r *Room) removeGonePlayers() {
	for {
		kept := make([]*Client, 0, len(r.players))
		var gone []*Client
		for _, p := range r.players {
			if r.clients[p] {
				kept = append(kept, p)
			} else {
				gone = append(gone, p)
			}
		}
		if len(gone) == 0 {
			return
		}
		r.players = kept

		// Рассылки ниже могут отключить ещё кого-то медленного — тогда
		// цикл пройдёт ещё раз.
		if r.phase == phaseLobby {
			for _, p := range gone {
				r.log.Info("игрок вышел", "player_id", p.playerID, "nickname", p.nickname)
				// Из лобби удаляем совсем: он не играл, а его ник должен
				// освободиться (в БД ник уникален в сессии).
				r.storeCall("удаление игрока", func(ctx context.Context) error {
					return r.store.RemovePlayer(ctx, p.playerID)
				})
			}
			r.broadcastMembers(encode("lobby_update", lobbyUpdateData{Players: r.playerList()}))
			continue
		}

		// Во время игры выбывший не может вернуться, но его очки остаются.
		r.left = append(r.left, gone...)
		for _, p := range gone {
			p.left = true
			r.storeCall("отметка выбывшего", func(ctx context.Context) error {
				return r.store.MarkLeft(ctx, p.playerID)
			})
			r.log.Info("игрок выбыл", "player_id", p.playerID, "nickname", p.nickname, "score", p.score)
			r.broadcastMembers(encode("player_left", playerLeftData{PlayerID: p.playerID, Nickname: p.nickname}))
		}
		if r.phase == phaseQuestion {
			r.sendProgress()
			// Может оказаться, что все оставшиеся уже ответили.
			if r.allAnswered() {
				r.finishQuestion()
			}
		}
	}
}

// dropSilent отключает тех, кто подключился, но так и не прислал join.
// Иначе можно открыть тысячи соединений к чужой комнате и держать их.
func (r *Room) dropSilent(now time.Time) {
	for c := range r.clients {
		if c.role == RolePlayer && c.playerID == 0 && now.Sub(c.connectedAt) > r.timeouts.Join {
			r.disconnect(c, websocket.ClosePolicyViolation, "join timeout")
		}
	}
}
