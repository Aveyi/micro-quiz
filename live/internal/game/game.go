package game

import (
	"context"
	"encoding/json"
	"slices"
	"strconv"
	"time"

	"github.com/gorilla/websocket"

	"github.com/Aveyi/micro-quiz/live/internal/session"
)

const leaderboardSize = 10

// answer — ответ игрока на текущий вопрос.
type answer struct {
	optionID int64
	correct  bool
	elapsed  time.Duration
	points   int
}

// handleStart — ведущий начинает игру.
func (r *Room) handleStart(c *Client) {
	switch {
	case c.role != RoleHost:
		r.sendTo(c, errorMsg("not_allowed", "начать игру может только ведущий"))
		return
	case r.phase != phaseLobby:
		r.sendTo(c, errorMsg("invalid_state", "игра уже идёт"))
		return
	case len(r.players) == 0:
		r.sendTo(c, errorMsg("invalid_state", "в комнате нет ни одного игрока"))
		return
	}

	// Кто подключился, но не успел войти, — уже не войдёт.
	for cl := range r.clients {
		if cl.role == RolePlayer && cl.playerID == 0 {
			r.reject(cl, "game_already_started", "игра уже началась")
		}
	}

	r.setStatus(session.StatusRunning)
	r.log.Info("игра началась", "players", len(r.players))
	r.startQuestion(0)
}

func (r *Room) startQuestion(i int) {
	q := r.quiz.Questions[i]
	r.phase = phaseQuestion
	r.qIndex = i
	r.qLimit = time.Duration(q.TimeLimitSec) * r.timeouts.QuestionSecond
	r.answers = make(map[*Client]answer, len(r.players))

	opts := make([]optionData, 0, len(q.Options))
	for _, o := range q.Options {
		opts = append(opts, optionData{OptionID: o.ID, Text: o.Text})
	}
	r.broadcastMembers(encode("question", questionData{
		QuestionIndex: i,
		QuestionCount: len(r.quiz.Questions),
		Text:          q.Text,
		Options:       opts,
		TimeLimitSec:  q.TimeLimitSec,
	}))

	// Время ответа меряет сервер: от отправки вопроса до получения ответа.
	// time.Now() в Go содержит монотонные часы, поэтому перевод системных
	// часов (NTP, ручная настройка) не испортит разницу.
	r.qStarted = time.Now()
	r.qTimer = time.NewTimer(r.qLimit)
}

// handleAnswer — игрок отвечает на текущий вопрос.
func (r *Room) handleAnswer(c *Client, raw json.RawMessage) {
	switch {
	case c.role == RoleHost:
		r.sendTo(c, errorMsg("not_allowed", "ведущий не отвечает на вопросы"))
		return
	case c.playerID == 0 || r.phase != phaseQuestion:
		r.sendTo(c, errorMsg("invalid_state", "сейчас нет вопроса"))
		return
	}

	var d answerData
	if err := json.Unmarshal(raw, &d); err != nil || d.QuestionIndex == nil {
		r.sendTo(c, errorMsg("bad_message", "ожидали {\"question_index\": 0, \"option_id\": 17}"))
		return
	}
	if *d.QuestionIndex != r.qIndex {
		// Ответ на прошлый вопрос, пришедший уже во время следующего:
		// по протоколу молча отбрасываем.
		return
	}
	if _, ok := r.answers[c]; ok {
		r.sendTo(c, errorMsg("already_answered", "ответ уже принят"))
		return
	}

	q := r.quiz.Questions[r.qIndex]
	valid := false
	for _, o := range q.Options {
		if o.ID == d.OptionID {
			valid = true
			break
		}
	}
	if !valid {
		r.sendTo(c, errorMsg("bad_message", "в этом вопросе нет такого варианта"))
		return
	}

	elapsed := time.Since(r.qStarted)
	if elapsed > r.qLimit {
		// Таймер уже истёк, просто его событие ещё в очереди select.
		r.sendTo(c, errorMsg("invalid_state", "время вышло"))
		return
	}
	a := answer{optionID: d.OptionID, correct: d.OptionID == q.CorrectOptionID(), elapsed: elapsed}
	if a.correct {
		a.points = points(elapsed, r.qLimit)
	}
	r.answers[c] = a

	r.sendTo(c, encode("answer_accepted", answerAcceptedData{QuestionIndex: r.qIndex}))
	r.sendProgress()
	if r.allAnswered() {
		r.finishQuestion()
	}
}

// sendProgress — ведущему: сколько из оставшихся в игре уже ответили.
func (r *Room) sendProgress() {
	answered := 0
	for _, p := range r.players {
		if _, ok := r.answers[p]; ok {
			answered++
		}
	}
	r.sendTo(r.host, encode("answer_progress", answerProgressData{Answered: answered, Total: len(r.players)}))
}

func (r *Room) allAnswered() bool {
	for _, p := range r.players {
		if _, ok := r.answers[p]; !ok {
			return false
		}
	}
	return true
}

func (r *Room) stopQuestionTimer() {
	if r.qTimer != nil {
		r.qTimer.Stop()
		r.qTimer = nil
	}
}

// finishQuestion — вопрос закончился (таймер или ответили все):
// начисляем очки и рассылаем question_result.
func (r *Room) finishQuestion() {
	r.stopQuestionTimer()
	r.phase = phaseResult
	q := r.quiz.Questions[r.qIndex]

	// Очки получают все ответившие, в том числе выбывшие после ответа:
	// их результат останется в истории игры.
	for c, a := range r.answers {
		c.score += a.points
	}

	counts := make(map[string]int, len(q.Options))
	for _, o := range q.Options {
		counts[strconv.FormatInt(o.ID, 10)] = 0 // варианты без ответов тоже видны
	}
	for _, a := range r.answers {
		counts[strconv.FormatInt(a.optionID, 10)]++
	}

	rs := ranking(r.players)
	result := questionResultData{
		QuestionIndex:   r.qIndex,
		CorrectOptionID: q.CorrectOptionID(),
		Leaderboard:     leaderboard(rs, leaderboardSize),
	}

	host := result
	host.OptionCounts = counts
	r.sendTo(r.host, encode("question_result", host))

	// Каждому игроку — своё сообщение: общая часть плюс его личный результат.
	for _, p := range rs {
		a := r.answers[p.client] // нет ответа — нулевое значение: неверно, 0 очков
		mine := result
		mine.You = &questionYou{Correct: a.correct, Points: a.points, Score: p.client.score, Rank: p.rank}
		r.sendTo(p.client, encode("question_result", mine))
	}
	r.log.Info("вопрос завершён", "question_index", r.qIndex, "answered", len(r.answers), "players", len(r.players))
}

// handleNext — ведущий переходит к следующему вопросу или к итогам.
func (r *Room) handleNext(c *Client) {
	switch {
	case c.role != RoleHost:
		r.sendTo(c, errorMsg("not_allowed", "переключать вопросы может только ведущий"))
		return
	case r.phase != phaseResult:
		r.sendTo(c, errorMsg("invalid_state", "дождитесь окончания вопроса"))
		return
	}
	if r.qIndex+1 < len(r.quiz.Questions) {
		r.startQuestion(r.qIndex + 1)
		return
	}
	r.finishGame()
}

// finishGame — после последнего вопроса: game_over всем и закрытие комнаты.
func (r *Room) finishGame() {
	// В итогах — все, кто играл, включая выбывших (с пометкой left):
	// их очки честно заработаны. Места считаются среди всех.
	everyone := append(slices.Clone(r.players), r.left...)
	rs := ranking(everyone)
	board := leaderboard(rs, len(rs))

	r.sendTo(r.host, encode("game_over", gameOverData{Leaderboard: board}))
	for _, p := range rs {
		if p.client.left {
			continue // соединения у выбывшего уже нет
		}
		r.sendTo(p.client, encode("game_over", gameOverData{
			Leaderboard: board,
			You:         &gameOverYou{Score: p.client.score, Rank: p.rank},
		}))
	}

	r.setStatus(session.StatusFinished)
	for c := range r.clients {
		r.disconnect(c, websocket.CloseNormalClosure, "game over")
	}
	r.closed = true
	r.onClose()
	r.log.Info("игра завершена", "players", len(r.players), "left", len(r.left))
}

// setStatus обновляет статус сессии. Ошибку только логируем: игра в
// памяти идёт дальше, даже если хранилище на миг недоступно.
func (r *Room) setStatus(s session.Status) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := r.store.SetStatus(ctx, r.sess.ID, s); err != nil {
		r.log.Error("не удалось обновить статус сессии", "status", s, "err", err)
	}
}
