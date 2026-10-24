package game

import (
	"time"

	"github.com/gorilla/websocket"
)

const (
	// writeWait — сколько ждём, пока одно сообщение уйдёт клиенту.
	writeWait = 10 * time.Second
	// pongWait — если за это время от клиента ничего не пришло (даже pong),
	// считаем соединение мёртвым. Без этого «тихо пропавший» клиент
	// (выдернули кабель) висел бы в комнате вечно: TCP сам об этом не скажет.
	pongWait = 60 * time.Second
	// pingPeriod — как часто шлём ping. Меньше pongWait, чтобы pong успел
	// вернуться. Тот же интервал (54 с) учитываем в proxy_read_timeout nginx.
	pingPeriod = pongWait * 9 / 10
	// maxMessageSize — самое большое сообщение от клиента — join с ником,
	// это десятки байт; 4 КБ с запасом.
	maxMessageSize = 4096
	// sendBuffer — очередь исходящих сообщений клиента. Если клиент не
	// успевает её разбирать, комната его отключает, а не ждёт.
	sendBuffer = 32
)

type Role string

const (
	RoleHost   Role = "host"
	RolePlayer Role = "player"
)

// Client — одно WebSocket-соединение. У соединения ровно один читатель
// (readPump) и ровно один писатель (writePump): gorilla/websocket не
// разрешает писать в соединение из нескольких горутин одновременно.
type Client struct {
	conn *websocket.Conn
	room *Room
	role Role

	// send — очередь сообщений для writePump. Закрывает её только комната:
	// это сигнал writePump отправить close-фрейм и завершиться.
	send chan []byte
	// closeCode и closeText комната записывает перед close(send).
	// Закрытие канала гарантирует, что writePump увидит эти значения.
	closeCode int
	closeText string

	// Поля ниже меняет и читает только горутина комнаты.
	connectedAt time.Time
	playerID    int64 // 0 — ещё не вошёл через join
	nickname    string
}

func newClient(conn *websocket.Conn, room *Room, role Role) *Client {
	return &Client{
		conn:      conn,
		room:      room,
		role:      role,
		send:      make(chan []byte, sendBuffer),
		closeCode: websocket.CloseNormalClosure,
	}
}

// serve подключает соединение к комнате и обслуживает его до отключения.
// Возвращается, когда соединение закрыто.
func serve(room *Room, conn *websocket.Conn, role Role) {
	c := newClient(conn, room, role)
	if !room.enter(c) {
		// Комната закрылась между проверками и подключением.
		closeNow(conn, "room closed")
		return
	}
	go c.writePump()
	c.readPump()
}

// closeNow закрывает соединение, которое так и не попало в комнату.
func closeNow(conn *websocket.Conn, text string) {
	conn.WriteControl(websocket.CloseMessage,
		websocket.FormatCloseMessage(websocket.CloseGoingAway, text),
		time.Now().Add(writeWait))
	conn.Close()
}

// readPump читает сообщения клиента и передаёт их комнате.
func (c *Client) readPump() {
	defer func() {
		c.room.leave(c)
		c.conn.Close()
	}()

	c.conn.SetReadLimit(maxMessageSize)
	c.conn.SetReadDeadline(time.Now().Add(pongWait))
	// Каждый pong продлевает срок: клиент жив.
	c.conn.SetPongHandler(func(string) error {
		return c.conn.SetReadDeadline(time.Now().Add(pongWait))
	})

	for {
		_, msg, err := c.conn.ReadMessage()
		if err != nil {
			// Клиент закрыл соединение, связь пропала, истёк pongWait
			// или сообщение больше maxMessageSize.
			return
		}
		c.conn.SetReadDeadline(time.Now().Add(pongWait))
		if !c.room.deliver(c, msg) {
			return
		}
	}
}

// writePump отправляет клиенту сообщения из send и периодически ping.
func (c *Client) writePump() {
	ticker := time.NewTicker(pingPeriod)
	defer func() {
		ticker.Stop()
		// Закрытие соединения прерывает ReadMessage в readPump.
		c.conn.Close()
	}()

	for {
		select {
		case msg, ok := <-c.send:
			c.conn.SetWriteDeadline(time.Now().Add(writeWait))
			if !ok {
				// Комната закрыла очередь: прощаемся close-фреймом с кодом.
				c.conn.WriteMessage(websocket.CloseMessage,
					websocket.FormatCloseMessage(c.closeCode, c.closeText))
				return
			}
			if err := c.conn.WriteMessage(websocket.TextMessage, msg); err != nil {
				return
			}
		case <-ticker.C:
			c.conn.SetWriteDeadline(time.Now().Add(writeWait))
			if err := c.conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				return
			}
		}
	}
}
