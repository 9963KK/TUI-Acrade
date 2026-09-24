package screen

// GrokNight 风格的语义配色，与 kit/arcade_kit/theme.py 使用相同的 RGB 值。
var inks = map[string]Color{
	"text":    C(225, 225, 225).WithBasic(7),
	"muted":   C(150, 150, 150).WithBasic(7),
	"border":  C(80, 80, 88).WithBasic(7),
	"accent":  C(122, 162, 247).WithBasic(6),
	"player":  C(158, 206, 106).WithBasic(2),
	"warning": C(224, 175, 104).WithBasic(3),
	"dim":     C(78, 78, 78).WithBasic(7),
}

var surfaces = map[string]Color{
	"canvas": C(20, 20, 20).WithBasic(0),
	"panel":  C(36, 36, 36).WithBasic(0),
}

// Theme turns semantic roles into styles and decides between Unicode and ASCII line art.
type Theme struct {
	Profile Profile
	// Rich 为 false 时边框、分割线和提示都使用 ASCII，避免歧义宽度字符被终端画成双宽。
	Rich    bool
	Unicode bool
}

// NewTheme reads the environment once.
func NewTheme(getenv func(string) string) Theme {
	profile := DetectProfile(getenv)
	return Theme{
		Profile: profile,
		Rich:    profile != Mono && getenv("ARCADE_ASCII") != "1" && getenv("TERM") != "linux",
		Unicode: UnicodeLocale(getenv),
	}
}

// Role is the style for a semantic role on a surface.
func (t Theme) Role(role, surface string, bold bool) Style {
	fg, ok := inks[role]
	if !ok {
		fg = inks["text"]
	}
	return Style{FG: fg, BG: surfaces[surface], Bold: bold}
}

// Base is the canvas style used to clear the screen.
func (t Theme) Base() Style { return t.Role("text", "canvas", false) }

// Glyphs 返回 Unicode 或 ASCII 线条字符。
func (t Theme) Rule() string {
	if t.Rich {
		return "─"
	}
	return "-"
}

// Dot separates items in a line; the middle dot is East Asian ambiguous width, so ASCII mode avoids it.
func (t Theme) Dot() string {
	if t.Rich {
		return " · "
	}
	return " - "
}

func (t Theme) Arrows() string {
	if t.Rich {
		return "↑↓←→"
	}
	return "方向键"
}

// Corners are the four open corners of an empty gallery slot.
func (t Theme) Corners() [4]string {
	if t.Rich {
		return [4]string{"┌─", "─┐", "└─", "─┘"}
	}
	return [4]string{"+-", "-+", "+-", "-+"}
}

// Frame returns top corners, bottom corners, side and horizontal line.
func (t Theme) Frame(heavy bool) (top, bottom [2]string, side, line string) {
	switch {
	case t.Rich && heavy:
		return [2]string{"┏", "┓"}, [2]string{"┗", "┛"}, "┃", "━"
	case t.Rich:
		return [2]string{"╭", "╮"}, [2]string{"╰", "╯"}, "│", "─"
	case heavy:
		return [2]string{"+", "+"}, [2]string{"+", "+"}, "|", "="
	}
	return [2]string{"+", "+"}, [2]string{"+", "+"}, "|", "-"
}
