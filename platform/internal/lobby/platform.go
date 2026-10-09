package lobby

import (
	"io"
	"strings"

	tea "github.com/charmbracelet/bubbletea"

	"tuiarcade/platform/internal/catalog"
	"tuiarcade/platform/internal/install"
	"tuiarcade/platform/internal/launcher"
	"tuiarcade/platform/internal/registry"
	"tuiarcade/platform/internal/screen"
)

type loaded struct {
	games   []catalog.Entry
	choices []install.Choice
	err     error
}
type acquired struct {
	candidate *install.Candidate
	err       error
}
type operated struct {
	err   error
	title string
}

// Platform 管理启动和安装页面，画廊负责启动游戏。
type Platform struct {
	manager       *install.Manager
	theme         screen.Theme
	gallery       Model
	choices       []install.Choice
	page          string
	selection     int
	width, height int
	busy          bool
	input         string
	notice        *Notice
	action        string
	scroll        int
	candidate     *install.Candidate
}

func NewPlatform(manager *install.Manager, theme screen.Theme, games []catalog.Entry, start *catalog.Entry) Platform {
	m := Platform{manager: manager, theme: theme, page: "start"}
	m.gallery = m.newGallery(games, start)
	m.choices, _ = manager.Choices()
	if len(games) == 0 {
		m.selection = 1
	}
	if start != nil {
		m.page = "gallery"
	}
	return m
}

func (m Platform) newGallery(games []catalog.Entry, start *catalog.Entry) Model {
	launch := func(entry catalog.Entry) (tea.Cmd, string) {
		game, problem := m.manager.Launch(entry)
		if problem != "" {
			return nil, problem
		}
		return Command(entry, game), ""
	}
	g := New(games, nil, m.theme, launch, start)
	g.width, g.height, g.back = m.width, m.height, true
	g.report = func(entry catalog.Entry) []string {
		f, err := registry.Load(m.manager.RecordPath())
		if err != nil {
			return []string{err.Error(), "Enter 关闭"}
		}
		r := f.Find(entry.ID)
		if r == nil {
			return []string{"游戏尚未安装", "Enter 关闭"}
		}
		lines := install.Report(r.Checks)
		if len(lines) > 6 {
			lines = lines[:6]
		}
		return append(lines, "日志："+r.LogFile, "Enter 关闭，返回安装页面修复")
	}
	return g
}

func (m Platform) Init() tea.Cmd { return nil }

func (m Platform) refresh(page string) (tea.Model, tea.Cmd) {
	m.page, m.busy, m.selection = page, true, 0
	return m, func() tea.Msg {
		games, err := m.manager.Library()
		choices, choiceErr := m.manager.Choices()
		if err == nil {
			err = choiceErr
		}
		return loaded{games, choices, err}
	}
}

func (m Platform) operation(fn func(*install.Manager) tea.Msg) (tea.Model, tea.Cmd) {
	m.busy = true
	var result tea.Msg
	task := &launcher.Task{Do: func(in io.Reader, out io.Writer) error {
		worker := *m.manager
		worker.In, worker.Out, worker.Columns, worker.Rows = in, out, m.width, m.height
		result = fn(&worker)
		return nil
	}}
	return m, tea.Exec(task, func(err error) tea.Msg {
		if err != nil {
			return operated{err, "操作失败"}
		}
		return result
	})
}

func (m Platform) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width, m.height = msg.Width, msg.Height
		if m.page == "gallery" {
			next, cmd := m.gallery.Update(msg)
			m.gallery = next.(Model)
			return m, cmd
		}
	case Back:
		m.page, m.selection = "start", 0
	case Finished:
		next, cmd := m.gallery.Update(msg)
		m.gallery = next.(Model)
		return m, cmd
	case loaded:
		m.busy = false
		if msg.err != nil {
			m.notice = &Notice{"无法读取安装记录", []string{msg.err.Error(), "修复记录后再试；原记录未覆盖。"}}
			m.action = "result"
		} else {
			m.choices = msg.choices
			m.gallery = m.newGallery(msg.games, nil)
		}
	case acquired:
		m.busy = false
		if msg.err != nil {
			m.notice, m.action = &Notice{"获取失败", []string{msg.err.Error()}}, "result"
		} else {
			m.candidate = msg.candidate
			plan, err := m.manager.Plan(msg.candidate)
			if err != nil {
				m.notice, m.action = &Notice{"无法安装", []string{err.Error()}}, "result"
			} else {
				m.notice, m.action = &Notice{"确认安装", plan}, "install"
			}
		}
		m.scroll = 0
	case operated:
		m.busy, m.action, m.scroll = false, "result", 0
		if msg.err != nil {
			m.notice = &Notice{"操作失败", []string{msg.err.Error()}}
			if m.candidate != nil && m.candidate.Stage != "" {
				m.notice.Lines = append(m.notice.Lines, "现场："+m.candidate.Stage, "K 保留现场；Enter 默认清理")
			}
		} else {
			m.candidate = nil
			m.notice = &Notice{msg.title, []string{"游戏列表已更新，卸载始终保留存档。", "Enter / Q / Esc 关闭结果"}}
		}
		games, refreshErr := m.manager.Library()
		choices, choiceErr := m.manager.Choices()
		if refreshErr == nil {
			refreshErr = choiceErr
		}
		if refreshErr != nil {
			m.notice.Lines = append(m.notice.Lines, "刷新游戏列表失败："+refreshErr.Error())
		} else {
			m.choices, m.gallery = choices, m.newGallery(games, nil)
		}
	case tea.KeyMsg:
		key := strings.ToLower(msg.String())
		if key == "ctrl+c" {
			if m.candidate != nil {
				m.candidate.Close(false)
			}
			return m, tea.Quit
		}
		if m.busy {
			return m, nil
		}
		if m.notice != nil {
			return m.modalKey(key)
		}
		if m.width < minWidth || m.height < minHeight {
			if key == "q" || key == "esc" {
				if m.page == "start" {
					return m, tea.Quit
				}
				m.page, m.selection = "start", 0
			}
			return m, nil
		}
		if m.page == "gallery" {
			next, cmd := m.gallery.Update(msg)
			m.gallery = next.(Model)
			return m, cmd
		}
		if m.page == "input" {
			switch msg.Type {
			case tea.KeyEsc:
				m.page = "install"
			case tea.KeyEnter:
				if strings.TrimSpace(m.input) == "" {
					return m, nil
				}
				if install.IsGit(m.input) {
					m.notice, m.action = &Notice{"确认获取源码", []string{"将执行 git clone --depth 1：", m.input, "获取后展示清单、作者及将执行的命令。"}}, "clone"
				} else {
					candidate, err := m.manager.Acquire(m.input, catalog.Local)
					return m.Update(acquired{candidate, err})
				}
			case tea.KeyBackspace, tea.KeyDelete:
				runes := []rune(m.input)
				if len(runes) > 0 {
					m.input = string(runes[:len(runes)-1])
				}
			case tea.KeyRunes:
				if len(m.input) < 4096 {
					m.input += string(msg.Runes)
				}
			}
			return m, nil
		}
		if key == "q" || key == "esc" {
			if m.page == "start" {
				return m, tea.Quit
			}
			m.page, m.selection = "start", 0
			return m, nil
		}
		limit := 3
		if m.page == "install" {
			limit = len(m.choices) + 1
		}
		switch key {
		case "up", "w":
			m.selection = (m.selection - 1 + limit) % limit
		case "down", "s":
			m.selection = (m.selection + 1) % limit
		case "enter", " ":
			if m.page == "start" {
				switch m.selection {
				case 0:
					return m.refresh("gallery")
				case 1:
					return m.refresh("install")
				case 2:
					return m, tea.Quit
				}
			}
			if m.selection == len(m.choices) {
				m.page, m.input = "input", ""
				return m, nil
			}
			choice := m.choices[m.selection]
			if choice.Status == "本机不支持" {
				return m, nil
			}
			if choice.Status == "已安装" {
				return m.uninstallNotice(choice)
			}
			var candidate *install.Candidate
			var err error
			if choice.Record != nil {
				candidate, err = m.manager.Existing(choice.Entry.ID)
			} else {
				candidate = &install.Candidate{Entry: choice.Entry}
			}
			return m.Update(acquired{candidate, err})
		case "u":
			if m.page == "install" && m.selection < len(m.choices) && m.choices[m.selection].Record != nil {
				return m.uninstallNotice(m.choices[m.selection])
			}
		}
	}
	return m, nil
}

func (m Platform) uninstallNotice(choice install.Choice) (tea.Model, tea.Cmd) {
	m.notice, m.action = &Notice{"确认卸载", []string{choice.Entry.Name + "（" + choice.Entry.ID + "）", "移除安装登记与运行环境。", "git 来源删除克隆目录；内置／本地源码保留。", "游戏存档始终保留。"}}, "uninstall"
	return m, nil
}

func (m Platform) modalKey(key string) (tea.Model, tea.Cmd) {
	if key == "up" {
		m.scroll = max(0, m.scroll-1)
		return m, nil
	}
	if key == "down" {
		m.scroll++
		return m, nil
	}
	if key == "k" && m.action == "result" && m.candidate != nil {
		m.candidate.Close(true)
		m.candidate = nil
		m.notice = nil
		return m, nil
	}
	if key == "esc" || key == "q" || key == "n" {
		if m.candidate != nil {
			m.candidate.Close(false)
			m.candidate = nil
		}
		m.notice = nil
		return m, nil
	}
	if key != "enter" && key != "y" {
		return m, nil
	}
	action := m.action
	m.notice = nil
	switch action {
	case "clone":
		return m.operation(func(worker *install.Manager) tea.Msg {
			candidate, err := worker.Acquire(m.input, catalog.Git)
			return acquired{candidate, err}
		})
	case "install":
		return m.operation(func(worker *install.Manager) tea.Msg {
			_, err := worker.Install(m.candidate)
			return operated{err, "安装完成"}
		})
	case "uninstall":
		id := m.choices[m.selection].Entry.ID
		return m.operation(func(worker *install.Manager) tea.Msg { return operated{worker.Uninstall(id), "卸载完成"} })
	default:
		if m.candidate != nil {
			m.candidate.Close(false)
			m.candidate = nil
		}
	}
	return m, nil
}

func wrap(lines []string, width int) []string {
	out := []string{}
	for _, line := range lines {
		part, used := "", 0
		for _, r := range line {
			size := screen.RuneWidth(r)
			if used+size > width {
				out = append(out, part)
				part, used = "", 0
			}
			part += string(r)
			used += size
		}
		out = append(out, part)
	}
	return out
}

func (m Platform) View() string {
	if m.page == "gallery" && m.notice == nil {
		return m.gallery.View()
	}
	if m.width <= 0 || m.height <= 0 {
		return ""
	}
	c := &canvas{buffer: screen.NewBuffer(m.width, m.height, m.theme.Base()), theme: m.theme, surface: "canvas"}
	ox, oy := max(0, (m.width-80)/2)+2, max(0, (m.height-24)/2)
	title := "启动界面"
	if m.page == "install" || m.page == "input" {
		title = "安装管理"
	}
	if m.page != "start" || m.width < minWidth || m.height < minHeight {
		c.text(oy, ox, "TUI ARCADE / "+title, "accent", true)
	}
	if m.width < minWidth || m.height < minHeight {
		c.text(oy+3, ox, "窗口太小，需要 80 x 24；Q 返回。", "warning", false)
		return c.buffer.Render(m.theme.Profile)
	}
	if m.page == "start" {
		m.drawStart(c)
	} else if m.page == "install" {
		c.text(oy+2, ox, "安装游戏", "text", true)
		first := max(0, m.selection-12)
		for i := first; i < min(first+14, len(m.choices)+1); i++ {
			label := "+ 从 git 地址或本地目录添加…"
			if i < len(m.choices) {
				choice := m.choices[i]
				label = choice.Entry.Name + "    " + choice.Status
			}
			m.row(c, oy+4+i-first, ox+2, label, i == m.selection)
		}
		if m.selection < len(m.choices) {
			choice := m.choices[m.selection]
			entry := choice.Entry
			detail := "来源：" + string(entry.Source)
			if entry.Python != nil {
				detail += "  Python " + entry.Python.Version.String()
			}
			if entry.Issue != "" {
				detail = entry.Issue
			}
			if choice.Record != nil && choice.Record.Problem != "" {
				detail = choice.Record.Problem
			}
			c.text(oy+20, ox, detail, "muted", false)
		}
		c.text(oy+22, ox, "Enter 安装／卸载   U 卸载登记   Q / Esc 返回启动界面", "muted", false)
	} else if m.page == "input" {
		c.text(oy+5, ox, "输入 git 地址或本地游戏目录：", "text", true)
		c.text(oy+8, ox, m.input+"_", "accent", false)
		c.text(oy+12, ox, "Enter 获取清单并确认安装；Esc 取消", "muted", false)
	}
	if m.busy {
		c.centeredDialog("处理中", []string{"正在检查游戏与运行环境，请稍候。"})
	}
	if m.notice != nil {
		c.surface = "panel"
		c.box(oy+2, ox, 21, 74, m.notice.Title, "border", false, true)
		lines := wrap(m.notice.Lines, 68)
		first := min(m.scroll, max(0, len(lines)-16))
		for i := first; i < min(len(lines), first+16); i++ {
			c.text(oy+4+i-first, ox+3, lines[i], "text", false)
		}
		c.text(oy+21, ox+3, "方向键滚动；Enter / Y 确认；Esc / N 取消", "muted", false)
	}
	return c.buffer.Render(m.theme.Profile)
}

func (m Platform) row(c *canvas, y, x int, label string, selected bool) {
	style := m.theme.Role("text", "canvas", selected)
	if selected {
		style.FG, style.BG = style.BG, style.FG
	}
	c.paint(y, x, " "+label+strings.Repeat(" ", max(0, 56-screen.StringWidth(label))), style)
}
