package screen

import (
	"strings"
	"unicode"

	"golang.org/x/text/width"
)

// RuneWidth is the number of terminal columns a rune occupies. East Asian ambiguous characters
// count as one column, which is what terminals do unless the user opts into double width.
func RuneWidth(r rune) int {
	if r == 0 || unicode.Is(unicode.Mn, r) || unicode.Is(unicode.Me, r) || unicode.Is(unicode.Cf, r) {
		return 0
	}
	switch width.LookupRune(r).Kind() {
	case width.EastAsianWide, width.EastAsianFullwidth:
		return 2
	}
	return 1
}

// StringWidth sums RuneWidth over a string.
func StringWidth(s string) int {
	total := 0
	for _, r := range s {
		total += RuneWidth(r)
	}
	return total
}

type cell struct {
	text  string
	style Style
	// tail 表示这一格是前一格宽字符的右半边，不单独输出。
	tail bool
}

// Buffer is a grid of cells that is serialized in one piece, so a frame is always complete.
type Buffer struct {
	Width, Height int
	cells         [][]cell
	base          Style
}

// NewBuffer fills the grid with spaces in the base style.
func NewBuffer(w, h int, base Style) *Buffer {
	b := &Buffer{Width: max(w, 0), Height: max(h, 0), base: base}
	b.cells = make([][]cell, b.Height)
	for y := range b.cells {
		b.cells[y] = make([]cell, b.Width)
		for x := range b.cells[y] {
			b.cells[y][x] = cell{text: " ", style: base}
		}
	}
	return b
}

func (b *Buffer) blank(y, x int) {
	b.cells[y][x] = cell{text: " ", style: b.cells[y][x].style}
}

// Text writes s at (y, x), clipped by display width. Like the curses version it never writes the last
// column. Control characters become "?" so error strings cannot inject escape sequences.
func (b *Buffer) Text(y, x int, s string, st Style) {
	if y < 0 || y >= b.Height || x < 0 {
		return
	}
	limit := b.Width - 1
	for _, r := range s {
		if unicode.IsControl(r) {
			r = '?'
		}
		w := RuneWidth(r)
		if w == 0 {
			continue
		}
		if x+w > limit {
			return
		}
		row := b.cells[y]
		// 覆盖宽字符的一半时，另一半改成空格，避免残影。
		if row[x].tail && x > 0 {
			b.blank(y, x-1)
		}
		if x+w < b.Width && row[x+w].tail {
			b.blank(y, x+w)
		}
		row[x] = cell{text: string(r), style: st}
		if w == 2 {
			row[x+1] = cell{style: st, tail: true}
		}
		x += w
	}
}

// Fill paints a rectangle of spaces in a style.
func (b *Buffer) Fill(y, x, h, w int, st Style) {
	for row := y; row < y+h; row++ {
		b.Text(row, x, strings.Repeat(" ", max(w, 0)), st)
	}
}

// Render serializes the grid; every line starts from a reset style so lines can be repainted alone.
// The last column is never emitted: if the terminal measures some character wider than we do, the line
// still ends before the edge instead of wrapping and shifting every following line. Each line ends in the
// base style, so the erase-to-end-of-line the renderer adds paints that column in the canvas color.
func (b *Buffer) Render(p Profile) string {
	var out strings.Builder
	for y, row := range b.cells {
		if y > 0 {
			out.WriteByte('\n')
		}
		current, started := Style{}, false
		for _, c := range row[:max(len(row)-1, 0)] {
			if c.tail {
				continue
			}
			if !started || c.style != current {
				out.WriteString(SGR(c.style, p))
				current, started = c.style, true
			}
			out.WriteString(c.text)
		}
		out.WriteString(SGR(Style{BG: b.base.BG}, p))
	}
	return out.String()
}

// Plain returns the grid text without styles, for tests.
func (b *Buffer) Plain() []string {
	lines := make([]string, len(b.cells))
	for y, row := range b.cells {
		var line strings.Builder
		for _, c := range row {
			line.WriteString(c.text)
		}
		lines[y] = line.String()
	}
	return lines
}
