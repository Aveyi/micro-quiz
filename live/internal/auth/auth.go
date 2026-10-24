// Package auth проверяет JWT ведущего, выданный сервисом content.
// Формат токена — docs/quiz-design.md, раздел 6.
package auth

import (
	"errors"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

// issuer — кто выдаёт токены. Проверка iss отсекает токены, подписанные
// тем же секретом, но выпущенные для другой цели.
const issuer = "quiz-content"

// leeway — допустимое расхождение часов content и live при проверке exp.
const leeway = 30 * time.Second

var (
	// ErrNoToken — заголовка Authorization нет. Это не ошибка: так подключается игрок.
	ErrNoToken = errors.New("токен не передан")
	// ErrInvalidToken — токен есть, но ему нельзя верить (HTTP 401).
	ErrInvalidToken = errors.New("токен невалиден")
)

// Host — ведущий, личность которого подтвердил токен.
type Host struct {
	UserID   int64
	Username string
}

// claims — содержимое токена. RegisteredClaims даёт стандартные поля
// sub, iss, exp; username — наше собственное поле.
type claims struct {
	Username string `json:"username"`
	jwt.RegisteredClaims
}

type Verifier struct {
	secret []byte
	parser *jwt.Parser
}

func NewVerifier(secret []byte) *Verifier {
	return &Verifier{
		secret: secret,
		parser: jwt.NewParser(
			// Принимаем только HS256. Без этого злоумышленник может прислать
			// токен с "alg": "none" (без подписи) или с другим алгоритмом.
			jwt.WithValidMethods([]string{jwt.SigningMethodHS256.Alg()}),
			jwt.WithIssuer(issuer),
			// Библиотека по умолчанию пропускает токен без exp — он был бы вечным.
			jwt.WithExpirationRequired(),
			jwt.WithLeeway(leeway),
		),
	}
}

// Verify проверяет подпись и поля токена и возвращает ведущего.
// Подробная причина отказа остаётся в тексте ошибки (для логов),
// а сравнивать ошибку нужно с ErrInvalidToken через errors.Is.
func (v *Verifier) Verify(token string) (Host, error) {
	var c claims
	_, err := v.parser.ParseWithClaims(token, &c, func(*jwt.Token) (any, error) {
		return v.secret, nil
	})
	if err != nil {
		return Host{}, fmt.Errorf("%w: %v", ErrInvalidToken, err)
	}

	// По стандарту sub — строка, а нам нужен числовой id пользователя.
	id, err := strconv.ParseInt(c.Subject, 10, 64)
	if err != nil || id <= 0 {
		return Host{}, fmt.Errorf("%w: sub %q не положительное число", ErrInvalidToken, c.Subject)
	}
	return Host{UserID: id, Username: c.Username}, nil
}

// FromRequest достаёт токен из заголовка "Authorization: Bearer <токен>"
// и проверяет его. Если заголовка нет, возвращает ErrNoToken.
func (v *Verifier) FromRequest(r *http.Request) (Host, error) {
	h := r.Header.Get("Authorization")
	if h == "" {
		return Host{}, ErrNoToken
	}
	// Название схемы по стандарту HTTP регистронезависимо: "bearer" тоже подходит.
	scheme, token, ok := strings.Cut(h, " ")
	if !ok || !strings.EqualFold(scheme, "Bearer") || token == "" {
		return Host{}, fmt.Errorf("%w: заголовок Authorization не в формате Bearer", ErrInvalidToken)
	}
	return v.Verify(token)
}
