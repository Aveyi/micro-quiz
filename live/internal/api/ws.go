package api

import (
	"errors"
	"log/slog"
	"net/http"

	"github.com/gorilla/websocket"

	"github.com/Aveyi/micro-quiz/live/internal/auth"
	"github.com/Aveyi/micro-quiz/live/internal/content"
	"github.com/Aveyi/micro-quiz/live/internal/game"
	"github.com/Aveyi/micro-quiz/live/internal/session"
)

type WS struct {
	Auth  *auth.Verifier
	Store session.Store
	Rooms *game.Manager
	Log   *slog.Logger
	// Upgrader по умолчанию проверяет заголовок Origin: если он есть и не
	// совпадает с адресом сервера, подключение отклоняется. Это защита от
	// чужих веб-страниц, которые пытаются подключиться из браузера
	// пользователя. Десктопный клиент Origin не шлёт, ему это не мешает.
	Upgrader websocket.Upgrader
}

// Connect — GET /live/ws?room=<код>. Все проверки делаем ДО Upgrade:
// пока протокол не переключён, ошибку можно вернуть обычным HTTP-кодом,
// и клиент сразу поймёт причину (docs/quiz-design.md, раздел 4.1).
func (h *WS) Connect(w http.ResponseWriter, r *http.Request) {
	code := r.URL.Query().Get("room")
	if code == "" {
		writeError(w, http.StatusBadRequest, "нужен параметр room")
		return
	}

	host, err := h.Auth.FromRequest(r)
	role := game.RoleHost
	switch {
	case errors.Is(err, auth.ErrNoToken):
		role = game.RolePlayer
	case err != nil:
		writeError(w, http.StatusUnauthorized, "токен невалиден или просрочен")
		return
	}

	sess, err := h.Store.GetActive(r.Context(), code)
	if errors.Is(err, session.ErrNotFound) {
		writeError(w, http.StatusNotFound, "комнаты с таким кодом нет")
		return
	}
	if err != nil {
		h.Log.Error("поиск сессии", "room", code, "err", err)
		writeError(w, http.StatusInternalServerError, "внутренняя ошибка")
		return
	}

	var room *game.Room
	if role == game.RoleHost {
		if sess.HostUserID != host.UserID {
			writeError(w, http.StatusForbidden, "комната создана другим пользователем")
			return
		}
		room, err = h.Rooms.OpenForHost(r.Context(), sess)
		switch {
		case errors.Is(err, game.ErrHostConnected):
			writeError(w, http.StatusConflict, "ведущий уже подключён к этой комнате")
			return
		case errors.Is(err, game.ErrShuttingDown):
			writeError(w, http.StatusServiceUnavailable, "сервер перезапускается, повторите")
			return
		case errors.Is(err, content.ErrQuizNotFound):
			writeError(w, http.StatusNotFound, "викторина удалена")
			return
		case err != nil:
			h.Log.Error("открытие комнаты", "room", code, "err", err)
			writeError(w, http.StatusBadGateway, "не удалось загрузить викторину")
			return
		}
	} else {
		// Комната в памяти появляется, когда подключается ведущий.
		room = h.Rooms.Get(code)
		if room == nil {
			writeError(w, http.StatusNotFound, "ведущий ещё не открыл комнату")
			return
		}
	}

	conn, err := h.Upgrader.Upgrade(w, r, nil)
	if err != nil {
		// Upgrade уже сам ответил клиенту HTTP-ошибкой. Если это был
		// ведущий, комната закроется сама, не дождавшись его.
		h.Log.Warn("upgrade не удался", "room", code, "err", err)
		return
	}
	// Дальше эта горутина HTTP-запроса становится readPump клиента.
	h.Rooms.Serve(room, conn, role)
}
