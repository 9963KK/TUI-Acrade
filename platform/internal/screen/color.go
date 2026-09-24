// Package screen draws the lobby into a cell buffer and serializes it with colors degraded to
// what the terminal supports: 24-bit, 256, basic 8, or none.
package screen

import (
	"fmt"
	"runtime"
	"strings"
)

// Profile is the color capability of the terminal.
type Profile int

const (
	Mono Profile = iota
	ANSI8
	ANSI16
	Color256
	TrueColor
)

// Colors is the number of colors a profile can show.
func (p Profile) Colors() int {
	return [...]int{0, 8, 16, 256, 1 << 24}[p]
}

// DetectProfile reads the conventional environment variables; it never queries the terminal.
func DetectProfile(getenv func(string) string) Profile {
	term := getenv("TERM")
	if getenv("NO_COLOR") != "" || term == "dumb" {
		return Mono
	}
	switch strings.ToLower(getenv("COLORTERM")) {
	case "truecolor", "24bit":
		return TrueColor
	}
	if getenv("WT_SESSION") != "" {
		// Windows Terminal 支持 24 位颜色但不设置 COLORTERM。
		return TrueColor
	}
	switch {
	case strings.Contains(term, "256color"), term == "xterm-kitty", term == "xterm-ghostty":
		return Color256
	case term == "linux":
		return ANSI8
	case term == "" && runtime.GOOS != "windows":
		return Mono
	}
	return ANSI16
}

// UnicodeLocale reports whether the locale promises UTF-8 output.
func UnicodeLocale(getenv func(string) string) bool {
	if runtime.GOOS == "windows" {
		return true
	}
	for _, key := range []string{"LC_ALL", "LC_CTYPE", "LANG"} {
		if value := strings.ToLower(getenv(key)); value != "" {
			return strings.Contains(value, "utf-8") || strings.Contains(value, "utf8")
		}
	}
	return false
}

// RGB is a 24-bit color.
type RGB struct{ R, G, B uint8 }

// Color is an optional RGB value with an optional explicit basic-8 fallback (-1 means nearest).
type Color struct {
	RGB   RGB
	Set   bool
	Basic int
}

// C builds a color that degrades to the nearest basic color.
func C(r, g, b uint8) Color { return Color{RGB{r, g, b}, true, -1} }

// WithBasic pins the basic-8 fallback, used where the nearest color would lose contrast.
func (c Color) WithBasic(index int) Color {
	c.Basic = index
	return c
}

// Style is foreground, background and weight of a cell.
type Style struct {
	FG, BG Color
	Bold   bool
}

// Indexed returns the nearest xterm-256 index, skipping the user-defined first 16 colors.
func Indexed(c RGB) int {
	levels := [6]int{0, 95, 135, 175, 215, 255}
	best, bestDistance := 16, 1<<30
	try := func(index, r, g, b int) {
		dr, dg, db := int(c.R)-r, int(c.G)-g, int(c.B)-b
		if distance := dr*dr + dg*dg + db*db; distance < bestDistance {
			best, bestDistance = index, distance
		}
	}
	for r := 0; r < 6; r++ {
		for g := 0; g < 6; g++ {
			for b := 0; b < 6; b++ {
				try(16+r*36+g*6+b, levels[r], levels[g], levels[b])
			}
		}
	}
	for i := 0; i < 24; i++ {
		gray := 8 + i*10
		try(232+i, gray, gray, gray)
	}
	return best
}

var basic = [8]RGB{{0, 0, 0}, {205, 0, 0}, {0, 205, 0}, {205, 205, 0}, {0, 0, 238}, {205, 0, 205}, {0, 205, 205}, {229, 229, 229}}

// Basic returns the nearest of the eight standard ANSI colors.
func Basic(c RGB) int {
	best, bestDistance := 0, 1<<30
	for index, candidate := range basic {
		dr, dg, db := int(c.R)-int(candidate.R), int(c.G)-int(candidate.G), int(c.B)-int(candidate.B)
		if distance := dr*dr + dg*dg + db*db; distance < bestDistance {
			best, bestDistance = index, distance
		}
	}
	return best
}

// SGR renders the escape sequence that switches to a style from a reset state.
func SGR(s Style, p Profile) string {
	var parts []string
	if s.Bold {
		parts = append(parts, "1")
	}
	layer := func(c Color, base int) {
		if !c.Set || p == Mono {
			return
		}
		switch p {
		case TrueColor:
			parts = append(parts, fmt.Sprintf("%d;2;%d;%d;%d", base+8, c.RGB.R, c.RGB.G, c.RGB.B))
		case Color256:
			parts = append(parts, fmt.Sprintf("%d;5;%d", base+8, Indexed(c.RGB)))
		default:
			index := c.Basic
			if index < 0 {
				index = Basic(c.RGB)
			}
			parts = append(parts, fmt.Sprint(base+index))
		}
	}
	layer(s.FG, 30)
	layer(s.BG, 40)
	if len(parts) == 0 {
		return "\x1b[0m"
	}
	return "\x1b[0;" + strings.Join(parts, ";") + "m"
}
