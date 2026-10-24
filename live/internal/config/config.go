// Package config читает настройки сервиса из переменных окружения.
// Список переменных — docs/quiz-design.md, раздел 8.3.
package config

import (
	"fmt"
	"net/url"
	"os"
	"strconv"
	"strings"
)

// minSecretLen — минимальная длина JWT_SECRET в байтах. Для HS256 ключ
// должен быть не короче самого хэша, 256 бит (RFC 7518, раздел 3.2):
// короткий секрет можно подобрать перебором по любому перехваченному токену.
const minSecretLen = 32

type Config struct {
	Port      int
	JWTSecret []byte
	// ContentURL — адрес сервиса content внутри Docker-сети, без завершающего "/".
	ContentURL string
	// InternalToken — общий с content секрет для /internal (заголовок X-Internal-Token).
	InternalToken string
}

// Load собирает конфиг и сразу проверяет его: лучше упасть при старте
// с понятной ошибкой, чем работать с неверными настройками.
func Load() (Config, error) {
	port, err := intEnv("PORT", 8080)
	if err != nil {
		return Config{}, err
	}
	if port < 1 || port > 65535 {
		return Config{}, fmt.Errorf("PORT: %d вне диапазона 1–65535", port)
	}

	// У секрета нет значения по умолчанию: сервис с общеизвестным
	// секретом принимал бы поддельные токены.
	secret := os.Getenv("JWT_SECRET")
	if len(secret) < minSecretLen {
		return Config{}, fmt.Errorf("JWT_SECRET: нужно не меньше %d байт, задано %d", minSecretLen, len(secret))
	}

	contentURL := os.Getenv("CONTENT_URL")
	if contentURL == "" {
		contentURL = "http://content:8000"
	}
	if u, err := url.Parse(contentURL); err != nil || (u.Scheme != "http" && u.Scheme != "https") || u.Host == "" {
		return Config{}, fmt.Errorf("CONTENT_URL: %q не похож на http(s)://хост[:порт]", contentURL)
	}

	internalToken := os.Getenv("INTERNAL_TOKEN")
	if internalToken == "" {
		return Config{}, fmt.Errorf("INTERNAL_TOKEN: не задан")
	}

	return Config{
		Port:          port,
		JWTSecret:     []byte(secret),
		ContentURL:    strings.TrimRight(contentURL, "/"),
		InternalToken: internalToken,
	}, nil
}

// intEnv возвращает число из переменной name или def, если переменная не задана.
func intEnv(name string, def int) (int, error) {
	s := os.Getenv(name)
	if s == "" {
		return def, nil
	}
	n, err := strconv.Atoi(s)
	if err != nil {
		return 0, fmt.Errorf("%s: %q не число", name, s)
	}
	return n, nil
}
