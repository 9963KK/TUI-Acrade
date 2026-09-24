// Package lobby is the gallery: it lists games from their manifests and hands the terminal to the chosen one.
package lobby

import (
	"fmt"
	"strings"

	tea "github.com/charmbracelet/bubbletea"

	"tuiarcade/platform/internal/catalog"
	"tuiarcade/platform/internal/launcher"
	"tuiarcade/platform/internal/screen"
)

const (
	// 画廊每页 2 行 3 列；不足一页时补空展位。12 个名额正好两页。
	columns   = 3
	page      = 6
	minWidth  = 80
	minHeight = 24
)

var moves = map[string]int{"up": -columns, "down": columns, "left": -1, "right": 1,
	"w": -columns, "s": columns, "a": -1, "d": 1}

var networkTags = map[string]string{"optional": "部分功能联网", "required": "需要联网"}

// Launch prepares a game. It returns the command that hands over the terminal, or a problem shown in the lobby
// without ever leaving it.
type Launch func(catalog.Entry) (tea.Cmd, string)

// Notice is a modal message.
type Notice struct {
	Title string
	Lines []string
}

// Finished is sent when a game process has ended and the terminal is back.
type Finished struct {
	Name string
	Code int
	Err  error
}

// Model is the Bubble Tea model of the lobby.
type Model struct {
	games         []catalog.Entry
	problems      []catalog.Problem
	theme         screen.Theme
	launch        Launch
	start         *catalog.Entry
	selection     int
	width, height int
	help          bool
	notice        *Notice
}

// New builds the lobby. start, when set, is opened as soon as the window size is known (--game).
func New(games []catalog.Entry, problems []catalog.Problem, theme screen.Theme, launch Launch, start *catalog.Entry) Model {
	return Model{games: games, problems: problems, theme: theme, launch: launch, start: start}
}

// Command wraps a prepared game so Bubble Tea releases the terminal, runs it, and reports back.
func Command(entry catalog.Entry, game *launcher.Game) tea.Cmd {
	return tea.Exec(game, func(err error) tea.Msg {
		if err == nil {
			err = game.Err
		}
		return Finished{entry.Name, game.ExitCode, err}
	})
}

func (m Model) slots() int {
	return max(page, (len(m.games)+page-1)/page*page)
}

func (m Model) Init() tea.Cmd { return nil }

func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width, m.height = msg.Width, msg.Height
		if m.start != nil {
			entry := *m.start
			m.start = nil
			return m.open(entry)
		}
	case Finished:
		switch {
		case msg.Err != nil:
			m.notice = &Notice{"无法启动", []string{msg.Name + "：" + msg.Err.Error(), "Enter 关闭"}}
		case msg.Code != 0 && !launcher.Interrupted(msg.Code):
			// 退出码只代表进程是否正常结束，不代表游戏胜负；Ctrl-C 离开不提示。
			m.notice = &Notice{"游戏异常退出", []string{fmt.Sprintf("%s以代码 %d 结束。", msg.Name, msg.Code), "Enter 关闭"}}
		}
	case tea.KeyMsg:
		return m.key(strings.ToLower(msg.String()))
	}
	return m, nil
}

func (m Model) key(key string) (tea.Model, tea.Cmd) {
	if key == "ctrl+c" {
		return m, tea.Quit
	}
	if m.notice != nil {
		switch key {
		case "enter", "esc", " ", "q":
			m.notice = nil
		}
		return m, nil
	}
	if m.width < minWidth || m.height < minHeight {
		if key == "q" || key == "esc" {
			return m, tea.Quit
		}
		return m, nil
	}
	if m.help {
		switch key {
		case "esc", "?", "h", "q", "enter":
			m.help = false
		}
		return m, nil
	}
	switch key {
	case "?", "h":
		m.help = true
	case "q", "esc":
		return m, tea.Quit
	case "enter", " ":
		if m.selection < len(m.games) {
			return m.open(m.games[m.selection])
		}
	default:
		if delta, ok := moves[key]; ok {
			target := m.selection + delta
			// 左右只在同一行内移动，不从行尾折到下一行。
			sameRow := target/columns == m.selection/columns
			if target >= 0 && target < m.slots() && (delta == columns || delta == -columns || sameRow) {
				m.selection = target
			}
		}
	}
	return m, nil
}

func (m Model) open(entry catalog.Entry) (tea.Model, tea.Cmd) {
	if entry.Issue != "" {
		m.notice = &Notice{"无法启动", []string{entry.Name + "：" + entry.Issue, "Enter 关闭"}}
		return m, nil
	}
	if need := entry.Terminal; m.width < need.Columns || m.height < need.Rows {
		m.notice = &Notice{"窗口太小", []string{
			fmt.Sprintf("%s需要 %d x %d，当前 %d x %d。", entry.Name, need.Columns, need.Rows, m.width, m.height),
			"放大窗口后再进入    Enter 关闭"}}
		return m, nil
	}
	cmd, problem := m.launch(entry)
	if problem != "" {
		m.notice = &Notice{"无法启动", []string{entry.Name + "：" + problem, "Enter 关闭"}}
		return m, nil
	}
	return m, cmd
}

// View renders the whole screen from scratch; Bubble Tea only writes the lines that changed.
func (m Model) View() string {
	if m.width <= 0 || m.height <= 0 {
		return ""
	}
	c := &canvas{buffer: screen.NewBuffer(m.width, m.height, m.theme.Base()), theme: m.theme, surface: "canvas"}
	if m.width < minWidth || m.height < minHeight {
		c.text(1, 1, "窗口太小。", "warning", true)
		c.text(3, 1, fmt.Sprintf("游戏厅需要 80 x 24，当前 %d x %d", m.width, m.height), "text", false)
		c.text(5, 1, "放大窗口即可继续；Q 退出。", "text", false)
		return c.buffer.Render(m.theme.Profile)
	}
	m.drawLobby(c)
	switch {
	case m.notice != nil:
		c.centeredDialog(m.notice.Title, m.notice.Lines)
	case m.help:
		c.centeredDialog("游戏厅说明", []string{m.theme.Arrows() + " / WASD：在展位之间移动",
			"Enter：进入选中的游戏    Q：退出", "游戏在当前终端中运行，退出后回到这里。", "Enter / Esc 关闭说明"})
	}
	return c.buffer.Render(m.theme.Profile)
}

func (m Model) drawLobby(c *canvas) {
	x0, oy := max(0, (m.width-80)/2)+1, max(0, (m.height-24)/2)
	c.text(oy, x0, "TUI ARCADE", "accent", true)
	c.text(oy, x0+12, "终端游戏厅", "text", true)
	count := fmt.Sprintf("已收录 %d 款", len(m.games))
	if len(m.problems) > 0 {
		// 无法解析的清单不上架，只提示数量，避免一份坏清单拖垮整个大厅。
		count += m.theme.Dot() + fmt.Sprintf("%d 份清单无效", len(m.problems))
	}
	if m.slots() > page {
		count += m.theme.Dot() + fmt.Sprintf("第 %d/%d 页", m.selection/page+1, m.slots()/page)
	}
	c.text(oy, x0+78-screen.StringWidth(count), count, "muted", false)
	c.text(oy+1, x0, strings.Repeat(m.theme.Rule(), 78), "border", false)
	first := m.selection / page * page
	for slot := first; slot < first+page; slot++ {
		row, column := (slot-first)/columns, (slot-first)%columns
		m.drawCard(c, oy+3+row*8, x0+column*27, slot)
	}
	c.text(oy+18, x0, strings.Repeat(m.theme.Rule(), 78), "border", false)
	if m.selection < len(m.games) {
		entry := m.games[m.selection]
		c.text(oy+19, x0, entry.Name, "text", true)
		c.text(oy+19, x0+screen.StringWidth(entry.Name)+2, entry.Presentation.NameEn, "muted", false)
		status, role := m.status(entry)
		c.text(oy+19, x0+78-screen.StringWidth(status), status, role, false)
		c.text(oy+20, x0, entry.Description, "text", false)
		// 标签做成浮起的小胶囊，与说明文字区分层次；联网需求由平台统一展示。
		tags := append([]string{}, entry.Presentation.Tags...)
		if tag := networkTags[entry.Network]; tag != "" {
			tags = append(tags, tag)
		}
		x := x0
		c.surface = "panel"
		for _, tag := range tags {
			c.text(oy+21, x, " "+tag+" ", "muted", false)
			x += screen.StringWidth(tag) + 3
		}
		c.surface = "canvas"
	} else {
		c.text(oy+19, x0, fmt.Sprintf("%02d 号展位", m.selection+1), "muted", true)
		c.text(oy+20, x0, "暂无游戏", "dim", false)
	}
	c.hints(oy+23, x0, [][2]string{{m.theme.Arrows(), "选择"}, {"Enter", "开始"}, {"?", "帮助"}, {"Q", "退出"}})
}

// status is the top-right line of the detail card: why a game cannot run, then the window requirement,
// then capability hints (which never block launching), then version and source.
func (m Model) status(entry catalog.Entry) (string, string) {
	t := entry.Terminal
	switch {
	case entry.Issue != "":
		return entry.Issue, "warning"
	case m.width < t.Columns || m.height < t.Rows:
		return fmt.Sprintf("需要 %d x %d 窗口", t.Columns, t.Rows), "warning"
	case t.Color == "truecolor" && m.theme.Profile != screen.TrueColor:
		return "建议使用真彩色终端", "warning"
	case (t.Color == "16" && m.theme.Profile.Colors() < 16) || (t.Color == "256" && m.theme.Profile.Colors() < 256):
		return "建议使用 " + t.Color + " 色终端", "warning"
	case t.Unicode == "required" && !m.theme.Unicode:
		return "需要 UTF-8 终端", "warning"
	}
	status := "v" + entry.Version
	if entry.Source == catalog.Dev {
		status = "开发来源" + m.theme.Dot() + status
	}
	return status, "muted"
}

func (m Model) drawCard(c *canvas, y, x, slot int) {
	selected := slot == m.selection
	number := fmt.Sprintf("%02d", slot+1)
	if slot >= len(m.games) {
		if selected {
			c.box(y, x, 6, 24, "", "accent", true, true)
		} else {
			// 空展位只画四角，像墙上的空画框，不与已上架的游戏抢视线。
			corners := m.theme.Corners()
			c.text(y, x, corners[0], "dim", false)
			c.text(y, x+22, corners[1], "dim", false)
			c.text(y+5, x, corners[2], "dim", false)
			c.text(y+5, x+22, corners[3], "dim", false)
		}
		role := "dim"
		if selected {
			role = "accent"
		}
		c.text(y+6, x+1, number, role, false)
		return
	}
	entry := m.games[slot]
	role := "border"
	if selected {
		role = "accent"
	}
	c.box(y, x, 6, 24, "", role, selected, false)
	m.drawCover(c, y+1, x+1, entry.Presentation)
	// 铭牌只放编号和名称，英文名与简介留给下方说明卡；不能运行的游戏名称变暗。
	numberRole, nameRole := "muted", "text"
	if selected {
		numberRole, nameRole = "accent", "accent"
	}
	if entry.Issue != "" {
		nameRole = "muted"
	}
	c.text(y+6, x+1, number, numberRole, false)
	c.text(y+6, x+4, entry.Name, nameRole, true)
}

func (m Model) drawCover(c *canvas, y, x int, look catalog.Presentation) {
	bg := screen.C(look.Background.R, look.Background.G, look.Background.B)
	blank := screen.Style{FG: screen.C(225, 225, 225), BG: bg}
	for row := 0; row < catalog.CoverHeight; row++ {
		c.paint(y+row, x, strings.Repeat(" ", catalog.CoverWidth*2), blank)
	}
	for row, line := range look.Cover {
		for column, key := range []rune(line) {
			cell, ok := look.Cells[key]
			if !ok {
				continue
			}
			style := screen.Style{FG: screen.C(cell.FG.R, cell.FG.G, cell.FG.B), BG: bg, Bold: cell.Bold}
			if cell.BG != nil {
				style.BG = screen.C(cell.BG.R, cell.BG.G, cell.BG.B)
			}
			glyph := cell.ASCII
			if m.theme.Rich {
				glyph = cell.Text
			}
			c.paint(y+row, x+column*2, glyph, style)
		}
	}
}
