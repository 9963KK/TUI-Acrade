package lobby

import (
	"strings"

	"tuiarcade/platform/internal/screen"
)

// canvas wraps a buffer with the semantic helpers the lobby draws with.
type canvas struct {
	buffer  *screen.Buffer
	theme   screen.Theme
	surface string
}

func (c *canvas) paint(y, x int, value string, style screen.Style) {
	c.buffer.Text(y, x, value, style)
}

func (c *canvas) text(y, x int, value, role string, bold bool) {
	c.paint(y, x, value, c.theme.Role(role, c.surface, bold))
}

func (c *canvas) box(y, x, height, width int, title, role string, heavy, fill bool) {
	top, bottom, side, line := c.theme.Frame(heavy)
	inner := strings.Repeat(line, max(width-2, 0))
	c.text(y, x, top[0]+inner+top[1], role, false)
	for row := 1; row < height-1; row++ {
		if fill {
			c.text(y+row, x, side+strings.Repeat(" ", max(width-2, 0))+side, role, false)
		} else {
			c.text(y+row, x, side, role, false)
			c.text(y+row, x+width-1, side, role, false)
		}
	}
	c.text(y+height-1, x, bottom[0]+inner+bottom[1], role, false)
	if title != "" {
		c.text(y, x+3, " "+title+" ", "accent", true)
	}
}

// hints draws key hints: keys in the text color, labels muted, so the eye finds the keys first.
func (c *canvas) hints(y, x int, items [][2]string) {
	for _, item := range items {
		c.text(y, x, item[0], "text", true)
		x += screen.StringWidth(item[0]) + 1
		c.text(y, x, item[1], "muted", false)
		x += screen.StringWidth(item[1]) + 3
	}
}

func (c *canvas) centeredDialog(title string, lines []string) {
	const width = 54
	height := len(lines)*2 + 3
	y, x := (c.buffer.Height-height)/2, (c.buffer.Width-width)/2
	previous := c.surface
	c.surface = "panel"
	c.box(y, x, height, width, title, "border", false, true)
	for i, line := range lines {
		c.text(y+2+i*2, x+3, line, "text", false)
	}
	c.surface = previous
}
