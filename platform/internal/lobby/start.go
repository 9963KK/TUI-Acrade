package lobby

import (
	"fmt"
	"strings"

	"tuiarcade/platform/internal/screen"
)

// 每个像素占两列，在终端中保留手柄轮廓；纯文本终端使用 ASCII 符号。
var startController = []string{
	"     AAAAAAAAAAAAAAAAAAAA     ",
	"   AAA..................AAA   ",
	"  AA.....D.........G......AA  ",
	" AA.....DDD....SS.....R....AA ",
	" AA......D.........B.......AA ",
	"  AA.........AAAAAA.......AA  ",
	"   AAAAAAAAA      AAAAAAAAA   ",
}

func (m Platform) drawStart(c *canvas) {
	const height, iconWidth, buttonWidth = 23, 60, 30
	// 与整个窗口对齐，预留缓冲区不绘制的最后一列。
	width := c.buffer.Width - 1
	y, x := (c.buffer.Height-height)/2, (width-iconWidth)/2
	center := func(row int, text, role string, bold bool) {
		c.text(y+row, (width-screen.StringWidth(text))/2, text, role, bold)
	}
	for row, line := range startController {
		for col, pixel := range line {
			if pixel == ' ' {
				continue
			}
			role, glyph := "accent", "##"
			switch pixel {
			case 'D':
				role, glyph = "text", "++"
			case 'S':
				role, glyph = "muted", "--"
			case 'G':
				role, glyph = "player", "OO"
			case 'R':
				role, glyph = "warning", "OO"
			case 'B':
				glyph = "OO"
			}
			style := m.theme.Role(role, "canvas", true)
			if m.theme.Rich && m.theme.Unicode {
				glyph = "██"
			}
			if pixel == '.' {
				glyph = "  "
				style = m.theme.Role("text", "panel", false)
			}
			c.paint(y+row, x+col*2, glyph, style)
		}
	}
	center(8, "T U I   A R C A D E", "accent", true)
	center(10, "把终端变成你的街机厅", "text", false)
	for i, label := range []string{"进入游戏厅", "安装游戏", "退出游戏厅"} {
		row := y + 13 + i*3
		if i != m.selection {
			center(13+i*3, label, "muted", false)
			continue
		}
		left := (buttonWidth - screen.StringWidth(label)) / 2
		text := strings.Repeat(" ", left) + label + strings.Repeat(" ", buttonWidth-left-screen.StringWidth(label))
		style := m.theme.Role("text", "canvas", true)
		style.FG, style.BG = style.BG, style.FG
		buttonX := (width - buttonWidth) / 2
		c.paint(row, buttonX, text, style)
		c.text(row, buttonX-3, ">", "accent", true)
		c.text(row, buttonX+buttonWidth+2, "<", "accent", true)
	}
	center(21, fmt.Sprintf("启动界面%s已安装 %d 款游戏", m.theme.Dot(), len(m.gallery.allGames)), "dim", false)
	center(22, "方向键选择   Enter 确认   Q 退出", "muted", false)
}
