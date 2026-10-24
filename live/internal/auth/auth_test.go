package auth

import (
	"encoding/base64"
	"errors"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

var secret = []byte("test-secret-test-secret-test-sec") // 32 байта

// sign выпускает токен так же, как это сделает content.
func sign(t *testing.T, method jwt.SigningMethod, key any, c jwt.MapClaims) string {
	t.Helper()
	s, err := jwt.NewWithClaims(method, c).SignedString(key)
	if err != nil {
		t.Fatal(err)
	}
	return s
}

// good — корректное содержимое токена; тесты портят в нём по одному полю.
func good() jwt.MapClaims {
	return jwt.MapClaims{
		"sub":      "1",
		"username": "teacher",
		"iss":      "quiz-content",
		"exp":      time.Now().Add(12 * time.Hour).Unix(),
	}
}

func with(key string, val any) jwt.MapClaims {
	c := good()
	if val == nil {
		delete(c, key)
	} else {
		c[key] = val
	}
	return c
}

func TestVerifyValid(t *testing.T) {
	v := NewVerifier(secret)
	host, err := v.Verify(sign(t, jwt.SigningMethodHS256, secret, good()))
	if err != nil {
		t.Fatal(err)
	}
	if host != (Host{UserID: 1, Username: "teacher"}) {
		t.Fatalf("host = %+v", host)
	}
}

func TestVerifyWithinLeeway(t *testing.T) {
	v := NewVerifier(secret)
	c := with("exp", time.Now().Add(-10*time.Second).Unix())
	if _, err := v.Verify(sign(t, jwt.SigningMethodHS256, secret, c)); err != nil {
		t.Fatalf("истёк 10 с назад, но в пределах leeway: %v", err)
	}
}

func TestVerifyRejects(t *testing.T) {
	hour := time.Now().Add(-time.Hour).Unix()
	none := sign(t, jwt.SigningMethodNone, jwt.UnsafeAllowNoneSignatureType, good())

	// Подделка: берём настоящий токен и меняем в нём sub на "2", подпись оставляем.
	orig := strings.Split(sign(t, jwt.SigningMethodHS256, secret, good()), ".")
	payload := base64.RawURLEncoding.EncodeToString(
		[]byte(`{"sub":"2","username":"teacher","iss":"quiz-content","exp":9999999999}`))
	tampered := orig[0] + "." + payload + "." + orig[2]

	tests := []struct {
		name  string
		token string
	}{
		{"чужой секрет", sign(t, jwt.SigningMethodHS256, []byte("other-secret-other-secret-other!!"), good())},
		{"alg none", none},
		{"alg HS512", sign(t, jwt.SigningMethodHS512, secret, good())},
		{"изменён payload", tampered},
		{"истёк", sign(t, jwt.SigningMethodHS256, secret, with("exp", hour))},
		{"нет exp", sign(t, jwt.SigningMethodHS256, secret, with("exp", nil))},
		{"чужой iss", sign(t, jwt.SigningMethodHS256, secret, with("iss", "evil"))},
		{"нет iss", sign(t, jwt.SigningMethodHS256, secret, with("iss", nil))},
		{"нет sub", sign(t, jwt.SigningMethodHS256, secret, with("sub", nil))},
		{"sub не число", sign(t, jwt.SigningMethodHS256, secret, with("sub", "abc"))},
		{"sub ноль", sign(t, jwt.SigningMethodHS256, secret, with("sub", "0"))},
		{"мусор", "not.a.jwt"},
		{"пустая строка", ""},
	}

	v := NewVerifier(secret)
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := v.Verify(tt.token)
			if !errors.Is(err, ErrInvalidToken) {
				t.Fatalf("ожидали ErrInvalidToken, получили %v", err)
			}
		})
	}
}

func TestFromRequest(t *testing.T) {
	token := sign(t, jwt.SigningMethodHS256, secret, good())

	tests := []struct {
		name   string
		header string
		want   error // nil — токен принят
	}{
		{"нет заголовка", "", ErrNoToken},
		{"Bearer", "Bearer " + token, nil},
		{"bearer строчными", "bearer " + token, nil},
		{"другая схема", "Basic " + token, ErrInvalidToken},
		{"без токена", "Bearer ", ErrInvalidToken},
		{"без пробела", "Bearer", ErrInvalidToken},
	}

	v := NewVerifier(secret)
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			r := httptest.NewRequest("GET", "/live/ws?room=482913", nil)
			if tt.header != "" {
				r.Header.Set("Authorization", tt.header)
			}
			_, err := v.FromRequest(r)
			if !errors.Is(err, tt.want) {
				t.Fatalf("ожидали %v, получили %v", tt.want, err)
			}
		})
	}
}
