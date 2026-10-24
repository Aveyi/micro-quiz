package game

import (
	"strings"
	"testing"
)

func TestNormalizeNickname(t *testing.T) {
	tests := []struct {
		in, want string
		ok       bool
	}{
		{"Вася", "Вася", true},
		{"  Вася  ", "Вася", true},
		{"Вася Пупкин", "Вася Пупкин", true},
		{strings.Repeat("я", 20), strings.Repeat("я", 20), true}, // 20 символов = 40 байт
		{strings.Repeat("я", 21), "", false},
		{strings.Repeat("a", 21), "", false},
		{"", "", false},
		{"   ", "", false},
		{"Вася\nПетя", "", false},
		{"Вася\x00", "", false},
		{"\xff\xfe", "", false}, // не UTF-8
	}
	for _, tt := range tests {
		got, ok := normalizeNickname(tt.in)
		if got != tt.want || ok != tt.ok {
			t.Errorf("normalizeNickname(%q) = %q, %v; ожидали %q, %v", tt.in, got, ok, tt.want, tt.ok)
		}
	}
}
