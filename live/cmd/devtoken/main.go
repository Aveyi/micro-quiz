// devtoken выпускает JWT ведущего так же, как это делает content, —
// чтобы проверять live, не поднимая content. Только для разработки.
//
// Запуск: JWT_SECRET=... go run ./cmd/devtoken -sub 1
package main

import (
	"flag"
	"fmt"
	"os"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

func main() {
	sub := flag.String("sub", "1", "id пользователя (claim sub)")
	username := flag.String("username", "teacher", "имя пользователя")
	ttl := flag.Duration("ttl", 12*time.Hour, "срок жизни токена")
	flag.Parse()

	secret := os.Getenv("JWT_SECRET")
	if secret == "" {
		fmt.Fprintln(os.Stderr, "JWT_SECRET не задан")
		os.Exit(1)
	}

	token, err := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"sub":      *sub,
		"username": *username,
		"iss":      "quiz-content",
		"exp":      time.Now().Add(*ttl).Unix(),
	}).SignedString([]byte(secret))
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	fmt.Println(token)
}
