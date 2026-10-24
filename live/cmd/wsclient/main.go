// wsclient — консольный WebSocket-клиент для ручной проверки live, пока нет
// десктопного приложения. Печатает всё, что пришло от сервера, и отправляет
// каждую введённую строку как сообщение.
//
// Ведущий: go run ./cmd/wsclient -room 482913 -token "$(go run ./cmd/devtoken)"
// Игрок:   go run ./cmd/wsclient -room 482913
// Затем вводите JSON, например: {"type":"join","data":{"nickname":"Вася"}}
package main

import (
	"bufio"
	"flag"
	"fmt"
	"net/http"
	"net/url"
	"os"

	"github.com/gorilla/websocket"
)

func main() {
	addr := flag.String("addr", "localhost:8080", "адрес live (или nginx)")
	room := flag.String("room", "", "код комнаты")
	token := flag.String("token", "", "JWT ведущего; пусто — подключиться игроком")
	flag.Parse()

	u := url.URL{Scheme: "ws", Host: *addr, Path: "/live/ws", RawQuery: url.Values{"room": {*room}}.Encode()}
	header := http.Header{}
	if *token != "" {
		header.Set("Authorization", "Bearer "+*token)
	}

	conn, resp, err := websocket.DefaultDialer.Dial(u.String(), header)
	if err != nil {
		if resp != nil {
			// Ошибка до переключения протокола: обычный HTTP-ответ.
			body := make([]byte, 512)
			n, _ := resp.Body.Read(body)
			fmt.Fprintf(os.Stderr, "HTTP %d: %s\n", resp.StatusCode, body[:n])
		} else {
			fmt.Fprintln(os.Stderr, err)
		}
		os.Exit(1)
	}
	defer conn.Close()
	fmt.Fprintln(os.Stderr, "подключено:", u.String())

	go func() {
		in := bufio.NewScanner(os.Stdin)
		for in.Scan() {
			if err := conn.WriteMessage(websocket.TextMessage, in.Bytes()); err != nil {
				return
			}
		}
		// Ctrl+D: вежливо закрываем соединение.
		conn.WriteMessage(websocket.CloseMessage, websocket.FormatCloseMessage(websocket.CloseNormalClosure, ""))
	}()

	for {
		_, msg, err := conn.ReadMessage()
		if err != nil {
			fmt.Fprintln(os.Stderr, "соединение закрыто:", err)
			return
		}
		fmt.Println("←", string(msg))
	}
}
