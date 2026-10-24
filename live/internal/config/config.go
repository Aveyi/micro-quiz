// Package config читает настройки сервиса из переменных окружения.
// Список переменных — docs/quiz-design.md, раздел 8.3.
package config

import (
	"fmt"
	"os"
	"strconv"
)

type Config struct {
	Port int
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
	return Config{Port: port}, nil
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
