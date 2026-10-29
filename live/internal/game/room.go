package game

import (
	"encoding/json"
	"log/slog"
	"time"

	"github.com/gorilla/websocket"

	"github.com/Aveyi/micro-quiz/live/internal/content"
	"github.com/Aveyi/micro-quiz/live/internal/session"
)

// phase — состояние комнаты (docs/quiz-design.md, раздел 4.5).
// finished и cancelled отдельной фазой не нужны: в этот момент комната
// закрывается и её горутина завершается.
type phase int

const (
	phaseLobby    phase = iota
	phaseQuestion       // идёт вопрос, принимаем ответы
	phaseResult         // вопрос закончился, ждём next от ведущего
)

type inbound struct {
	client *Client
	msg    []byte
}

// Room — одна комната в памяти инстанса. Всё её состояние принадлежит
// одной горутине run: остальные горутины общаются с ней только через
// каналы. Поэтому мьютексы для состояния комнаты не нужны и гонок нет.
// Это модель «актора»: «не общайтесь через общую память — делитесь
// памятью через общение».
type Room struct {
	sess     session.Session
	quiz     content.Quiz
	store    session.Store
	log      *slog.Logger
	timeouts Timeouts
	onClose  func() // убирает комнату из менеджера

	register   chan *Client
	unregister chan *Client
	inbound    chan inbound
	quit       chan struct{} // остановка сервера
	// done закрывается, когда run завершился. Тогда отправка в каналы
	// выше заблокировала бы горутину навсегда, поэтому все отправки
	// делаются через select с done.
	done chan struct{}

	// Состояние: только для горутины run.
	phase   phase
	host    *Client
	clients map[*Client]bool // все подключённые, включая ведущего
	players []*Client        // вошедшие через join и ещё не выбывшие, в порядке входа
	left    []*Client        // выбыли во время игры: их очки нужны для истории
	closed  bool             // комната завершена, run должен выйти

	// Текущий вопрос.
	qIndex   int
	qStarted time.Time
	qLimit   time.Duration
	qTimer   *time.Timer
	answers  map[*Client]answer
}

func newRoom(sess session.Session, quiz content.Quiz, store session.Store, log *slog.Logger, t Timeouts) *Room {
	return &Room{
		sess:       sess,
		quiz:       quiz,
		store:      store,
		log:        log.With("room", sess.RoomCode, "session_id", sess.ID),
		timeouts:   t,
		register:   make(chan *Client),
		unregister: make(chan *Client),
		inbound:    make(chan inbound),
		quit:       make(chan struct{}),
		done:       make(chan struct{}),
		clients:    make(map[*Client]bool),
	}
}

// enter, leave и deliver вызываются из горутин клиентов.
// false означает, что комната уже закрыта.

func (r *Room) enter(c *Client) bool {
	select {
	case r.register <- c:
		return true
	case <-r.done:
		return false
	}
}

func (r *Room) leave(c *Client) {
	select {
	case r.unregister <- c:
	case <-r.done:
	}
}

func (r *Room) deliver(c *Client, msg []byte) bool {
	select {
	case r.inbound <- inbound{c, msg}:
		return true
	case <-r.done:
		return false
	}
}

// shutdown просит комнату закрыться из-за остановки сервера.
func (r *Room) shutdown() {
	select {
	case r.quit <- struct{}{}:
	case <-r.done:
	}
}

func (r *Room) run() {
	defer close(r.done)
	r.log.Info("комната открыта", "quiz_id", r.quiz.ID)

	// Все таймеры комнаты живут здесь же, в её горутине, и срабатывают
	// как обычные события в select — никакой отдельной синхронизации.
	hostWait := time.NewTimer(r.timeouts.HostWait)
	defer hostWait.Stop()
	// Срок лобби отсчитывается от создания комнаты, а не от подключения
	// ведущего: то же правило применяет уборка брошенных лобби в БД
	// (session.ExpireLobbiesLoop). Если срок уже вышел, таймер сработает сразу.
	lobby := time.NewTimer(time.Until(r.sess.CreatedAt.Add(r.timeouts.Lobby)))
	defer lobby.Stop()
	// Проверяем «молчунов» в несколько раз чаще, чем их таймаут,
	// чтобы отключать их не сильно позже срока.
	sweep := time.NewTicker(r.timeouts.Join / 4)
	defer sweep.Stop()

	for {
		select {
		case c := <-r.register:
			r.add(c)
		case c := <-r.unregister:
			r.disconnect(c, websocket.CloseNormalClosure, "")
		case in := <-r.inbound:
			r.handle(in)
		case now := <-sweep.C:
			r.dropSilent(now)
		case <-r.questionTimeout():
			r.finishQuestion()
		case <-hostWait.C:
			if r.host == nil {
				r.closeRoom("host_left")
			}
		case <-lobby.C:
			if r.phase == phaseLobby {
				r.closeRoom("lobby_timeout")
			}
		case <-r.quit:
			r.closeRoom("server_shutdown")
		}

		// Ведущий ушёл — сам или его отключили как медленного.
		if !r.closed && r.host != nil && !r.clients[r.host] {
			r.closeRoom("host_left")
		}
		if !r.closed {
			r.removeGonePlayers()
		}
		if r.closed {
			return
		}
	}
}

// questionTimeout — канал таймера текущего вопроса или nil, если вопроса
// нет. Чтение из nil-канала блокируется навсегда, поэтому в select эта
// ветка просто «выключена», пока таймер не нужен. Частый приём в Go.
func (r *Room) questionTimeout() <-chan time.Time {
	if r.qTimer == nil {
		return nil
	}
	return r.qTimer.C
}

func (r *Room) add(c *Client) {
	if c.role == RoleHost && r.host != nil {
		// Менеджер не пускает второго ведущего; это страховка.
		r.clients[c] = true
		r.disconnect(c, websocket.ClosePolicyViolation, "host already connected")
		return
	}
	r.clients[c] = true
	c.connectedAt = time.Now()
	if c.role == RoleHost {
		r.host = c
		r.log.Info("ведущий подключился")
		r.sendTo(c, encode("joined", joinedData{
			Role:          RoleHost,
			RoomCode:      r.sess.RoomCode,
			QuizTitle:     r.quiz.Title,
			QuestionCount: len(r.quiz.Questions),
			Players:       []playerInfo{}, // [] а не null: клиенту проще
		}))
	}
	// Игрок пока только подключён: участником он станет после join.
}

func (r *Room) handle(in inbound) {
	if !r.clients[in.client] {
		return // сообщение от уже отключённого клиента
	}
	var env envelope
	if err := json.Unmarshal(in.msg, &env); err != nil || env.Type == "" {
		r.sendTo(in.client, errorMsg("bad_message", "ожидали JSON вида {\"type\": ..., \"data\": {...}}"))
		return
	}
	switch env.Type {
	case "join":
		r.handleJoin(in.client, env.Data)
	case "start":
		r.handleStart(in.client)
	case "answer":
		r.handleAnswer(in.client, env.Data)
	case "next":
		r.handleNext(in.client)
	default:
		// Неизвестные type по протоколу молча игнорируем: так новые
		// сообщения не ломают старые серверы и клиенты.
	}
}

// sendTo кладёт сообщение в очередь клиента, не блокируясь. Если очередь
// полна, клиент не успевает читать — отключаем его: одна медленная сеть
// не должна тормозить всю комнату.
func (r *Room) sendTo(c *Client, msg []byte) {
	if !r.clients[c] {
		return
	}
	select {
	case c.send <- msg:
	default:
		r.log.Warn("клиент не успевает читать, отключаем", "role", c.role)
		r.disconnect(c, websocket.ClosePolicyViolation, "too slow")
	}
}

// broadcast — всем подключённым, включая тех, кто ещё не прислал join.
// Нужен только для room_closed: закрытие касается всех.
func (r *Room) broadcast(msg []byte) {
	for c := range r.clients {
		r.sendTo(c, msg) // удалять из map во время range в Go можно
	}
}

// broadcastMembers — ведущему и вошедшим игрокам. Тот, кто только
// подключился и не прислал join, не участник и не должен видеть,
// что происходит в комнате.
func (r *Room) broadcastMembers(msg []byte) {
	if r.host != nil {
		r.sendTo(r.host, msg)
	}
	for _, p := range r.players {
		r.sendTo(p, msg) // sendTo пропускает уже отключённых
	}
}

// disconnect убирает клиента из комнаты и закрывает его очередь —
// writePump отправит close-фрейм с кодом и закроет соединение.
func (r *Room) disconnect(c *Client, code int, text string) {
	if !r.clients[c] {
		return // уже отключён: второй close(send) вызвал бы панику
	}
	delete(r.clients, c)
	c.closeCode, c.closeText = code, text
	close(c.send)
	if c == r.host {
		r.log.Info("ведущий отключился")
	}
}

// closeRoom завершает комнату: всем room_closed, сессия — cancelled.
func (r *Room) closeRoom(reason string) {
	code := websocket.CloseNormalClosure
	if reason == "server_shutdown" {
		code = websocket.CloseGoingAway // 1001: «сервер уходит»
	}
	r.broadcast(encode("room_closed", roomClosedData{Reason: reason}))
	for c := range r.clients {
		r.disconnect(c, code, reason)
	}

	r.setStatus(session.StatusCancelled)
	r.stopQuestionTimer()
	r.closed = true
	r.onClose()
	r.log.Info("комната закрыта", "reason", reason)
}
