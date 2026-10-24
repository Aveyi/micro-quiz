package session

import (
	"regexp"
	"testing"
)

func TestNewCode(t *testing.T) {
	re := regexp.MustCompile(`^\d{6}$`)
	seen := map[string]bool{}
	for range 1000 {
		c := NewCode()
		if !re.MatchString(c) {
			t.Fatalf("код %q не из 6 цифр", c)
		}
		seen[c] = true
	}
	// Из 10^6 вариантов 1000 случайных почти наверняка разные.
	if len(seen) < 990 {
		t.Fatalf("всего %d разных кодов из 1000 — генератор не случайный?", len(seen))
	}
}
