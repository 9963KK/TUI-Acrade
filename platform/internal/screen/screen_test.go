package screen

import (
	"strings"
	"testing"
)

func env(values map[string]string) func(string) string {
	return func(key string) string { return values[key] }
}

func TestIndexedMatchesPythonTheme(t *testing.T) {
	// 与 tests/test_theme.py 相同的量化结果。
	for rgb, want := range map[RGB]int{{20, 20, 20}: 233, {36, 36, 36}: 235, {122, 162, 247}: 111} {
		if got := Indexed(rgb); got != want {
			t.Errorf("Indexed(%v) = %d, want %d", rgb, got, want)
		}
	}
	if Basic(RGB{0, 90, 200}) != 4 || Basic(RGB{205, 0, 0}) != 1 {
		t.Error("basic mapping")
	}
}

func TestWidthsAndClipping(t *testing.T) {
	if StringWidth("坦克 A") != 6 || StringWidth("é") != 1 || StringWidth("─▟") != 2 {
		t.Fatal("widths")
	}
	b := NewBuffer(8, 2, Style{})
	b.Text(0, 0, "坦克ABCDEFG", Style{})
	if got := b.Plain()[0]; got != "坦克ABC " {
		t.Errorf("clip keeps last column free: %q", got)
	}
	// 用窄字符覆盖宽字符的右半边，左半边随之清空。
	b.Text(0, 1, "x", Style{})
	if got := b.Plain()[0]; got != " x克ABC " {
		t.Errorf("wide overwrite: %q", got)
	}
	b.Text(5, 0, "out of range", Style{})
	b.Text(1, -1, "negative", Style{})
	b.Text(1, 0, "a\x1b]52;c\n", Style{})
	if got := b.Plain()[1]; got != "a?]52;c " {
		t.Errorf("control characters must not reach the terminal: %q", got)
	}
}

func TestRenderNeverEmitsTheLastColumn(t *testing.T) {
	b := NewBuffer(6, 2, Style{})
	b.Text(0, 0, "abcdef", Style{})
	for _, line := range strings.Split(b.Render(Mono), "\n") {
		plain := strings.NewReplacer("\x1b[0m", "").Replace(line)
		if strings.Contains(plain, "\x1b") {
			t.Fatalf("unexpected escape in %q", plain)
		}
		if StringWidth(plain) != 5 {
			t.Errorf("line %q is %d wide", plain, StringWidth(plain))
		}
	}
}

func TestRenderDegradesColors(t *testing.T) {
	st := Style{FG: C(122, 162, 247).WithBasic(6), BG: C(20, 20, 20).WithBasic(0), Bold: true}
	cases := map[Profile]string{
		TrueColor: "\x1b[0;1;38;2;122;162;247;48;2;20;20;20m",
		Color256:  "\x1b[0;1;38;5;111;48;5;233m",
		ANSI8:     "\x1b[0;1;36;40m",
		Mono:      "\x1b[0;1m",
	}
	for profile, want := range cases {
		if got := SGR(st, profile); got != want {
			t.Errorf("profile %d: %q, want %q", profile, got, want)
		}
	}
	b := NewBuffer(4, 2, st)
	out := b.Render(TrueColor)
	// 行尾停在底色上：渲染器补的“清除到行尾”会用画布颜色填满最后一列。
	if strings.Count(out, "\n") != 1 || !strings.HasSuffix(out, "\x1b[0;48;2;20;20;20m") {
		t.Errorf("render: %q", out)
	}
}

func TestDetection(t *testing.T) {
	cases := []struct {
		env  map[string]string
		want Profile
	}{
		{map[string]string{"TERM": "xterm-256color", "COLORTERM": "truecolor"}, TrueColor},
		{map[string]string{"TERM": "xterm-256color"}, Color256},
		{map[string]string{"TERM": "xterm"}, ANSI16},
		{map[string]string{"TERM": "linux"}, ANSI8},
		{map[string]string{"TERM": "xterm-256color", "NO_COLOR": "1"}, Mono},
	}
	for _, c := range cases {
		if got := DetectProfile(env(c.env)); got != c.want {
			t.Errorf("%v: %d, want %d", c.env, got, c.want)
		}
	}
	if NewTheme(env(map[string]string{"TERM": "linux"})).Rich || NewTheme(env(map[string]string{"TERM": "xterm-256color", "ARCADE_ASCII": "1"})).Rich {
		t.Error("ascii fallback")
	}
	if !NewTheme(env(map[string]string{"TERM": "xterm-256color"})).Rich {
		t.Error("rich by default")
	}
	if !UnicodeLocale(env(map[string]string{"LANG": "zh_CN.UTF-8"})) || UnicodeLocale(env(map[string]string{"LC_ALL": "C", "LANG": "en_US.UTF-8"})) {
		t.Error("locale")
	}
}
