package lobby

import (
	"errors"
	"fmt"
	"path/filepath"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/x/ansi"

	"tuiarcade/platform/internal/catalog"
	"tuiarcade/platform/internal/screen"
)

var rich = screen.Theme{Profile: screen.TrueColor, Rich: true, Unicode: true}

func tank(t *testing.T) catalog.Entry {
	t.Helper()
	root := catalog.FindRepo(".")
	entry, err := catalog.Parse(filepath.Join(root, "games", "tank", catalog.Manifest), catalog.Builtin, catalog.Host{System: "macos", Arch: "arm64"})
	if err != nil {
		t.Fatal(err)
	}
	return entry
}

type recorder struct{ opened []string }

func (r *recorder) launch(entry catalog.Entry) (tea.Cmd, string) {
	r.opened = append(r.opened, entry.ID)
	return func() tea.Msg { return nil }, ""
}

func sized(m Model, w, h int) Model {
	next, _ := m.Update(tea.WindowSizeMsg{Width: w, Height: h})
	return next.(Model)
}

func press(m Model, keys ...string) (Model, tea.Cmd) {
	var cmd tea.Cmd
	for _, key := range keys {
		var msg tea.KeyMsg
		switch key {
		case "up", "down", "left", "right", "enter", "esc", "ctrl+c":
			msg = tea.KeyMsg{Type: map[string]tea.KeyType{"up": tea.KeyUp, "down": tea.KeyDown, "left": tea.KeyLeft,
				"right": tea.KeyRight, "enter": tea.KeyEnter, "esc": tea.KeyEsc, "ctrl+c": tea.KeyCtrlC}[key]}
		default:
			msg = tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune(key)}
		}
		var next tea.Model
		next, cmd = m.Update(msg)
		m = next.(Model)
	}
	return m, cmd
}

func plain(m Model) string {
	// 去掉颜色序列，只比较文字。
	var out strings.Builder
	view := m.View()
	for i := 0; i < len(view); i++ {
		if view[i] == 0x1b {
			for i < len(view) && view[i] != 'm' {
				i++
			}
			continue
		}
		out.WriteByte(view[i])
	}
	return out.String()
}

func TestListsGamesAndLaunchesSelection(t *testing.T) {
	r := &recorder{}
	m := sized(New([]catalog.Entry{tank(t)}, nil, rich, r.launch, nil), 80, 24)
	view := plain(m)
	for _, want := range []string{"终端游戏厅", "坦克大战", "TANK BATTLE", " 35 关 ", "内置 · v0.3.0", "▜▛", "─"} {
		if !strings.Contains(view, want) {
			t.Errorf("missing %q", want)
		}
	}
	m, cmd := press(m, "enter")
	if len(r.opened) != 1 || cmd == nil || m.notice != nil {
		t.Errorf("launch: %v %v", r.opened, m.notice)
	}
	if _, cmd := press(m, "q"); cmd == nil {
		t.Error("q quits")
	}
}

func TestGalleryMovesInGridAndIgnoresEmptySlots(t *testing.T) {
	r := &recorder{}
	m := sized(New([]catalog.Entry{tank(t)}, nil, rich, r.launch, nil), 80, 24)
	m, _ = press(m, "up", "left")
	if m.selection != 0 {
		t.Fatal(m.selection)
	}
	m, _ = press(m, "right", "s")
	if m.selection != 4 {
		t.Fatal(m.selection)
	}
	m, _ = press(m, "down", "d", "d")
	if m.selection != 5 || !strings.Contains(plain(m), "06 号展位") {
		t.Fatal(m.selection)
	}
	press(m, "enter")
	if len(r.opened) != 0 {
		t.Error("empty slots cannot be launched")
	}
	m.selection = 2
	if m, _ = press(m, "right"); m.selection != 2 {
		t.Error("right must not wrap to the next row")
	}
	m.selection = 3
	if m, _ = press(m, "left"); m.selection != 3 {
		t.Error("left must not wrap to the previous row")
	}
}

func TestMoreGamesThanAPageArePaged(t *testing.T) {
	var games []catalog.Entry
	for i := range 7 {
		game := tank(t)
		game.ID, game.Name = fmt.Sprintf("g%d", i), fmt.Sprintf("游戏%d", i)
		games = append(games, game)
	}
	m := sized(New(games, nil, rich, (&recorder{}).launch, nil), 80, 24)
	if m.slots() != 12 || !strings.Contains(plain(m), "已收录 7 款 · 第 1/2 页") {
		t.Fatal(plain(m))
	}
	m, _ = press(m, "down", "down")
	if view := plain(m); m.selection != 6 || !strings.Contains(view, "游戏6") || strings.Contains(view, "游戏0") {
		t.Error("second page")
	}
}

func TestBlockedGamesAndNoticesNeverLaunch(t *testing.T) {
	r := &recorder{}
	blocked := tank(t)
	blocked.Issue, blocked.Network = "需要更新平台（清单协议 2）", "required"
	m := sized(New([]catalog.Entry{blocked}, []catalog.Problem{{Path: "x", Reason: "bad"}}, rich, r.launch, nil), 80, 24)
	view := plain(m)
	for _, want := range []string{"需要更新平台（清单协议 2）", " 需要联网 ", "已收录 1 款 · 1 份清单无效"} {
		if !strings.Contains(view, want) {
			t.Errorf("missing %q", want)
		}
	}
	m, _ = press(m, "enter")
	if len(r.opened) != 0 || m.notice == nil || m.notice.Title != "检查报告 / 需要修复" {
		t.Fatal("blocked game launched")
	}
	m, _ = press(m, "s")
	if m.selection != 0 {
		t.Error("notice swallows keys")
	}
	m, _ = press(m, "enter")
	if m.notice != nil {
		t.Error("enter closes the notice")
	}
	big := tank(t)
	big.Terminal.Columns, big.Terminal.Rows = 100, 30
	m = sized(New([]catalog.Entry{big}, nil, rich, r.launch, nil), 80, 24)
	if !strings.Contains(plain(m), "需要 100 x 30 窗口") {
		t.Error("size hint")
	}
	if m, _ = press(m, "enter"); m.notice == nil || m.notice.Title != "窗口太小" || len(r.opened) != 0 {
		t.Error("too small window must block")
	}
	failing := New([]catalog.Entry{tank(t)}, nil, rich, func(catalog.Entry) (tea.Cmd, string) { return nil, "入口缺失" }, nil)
	if m, _ = press(sized(failing, 80, 24), "enter"); m.notice == nil || m.notice.Lines[0] != "坦克大战：入口缺失" {
		t.Error("prepare problems are shown without leaving the lobby")
	}
}

func TestExitStatusesAfterAGame(t *testing.T) {
	m := sized(New([]catalog.Entry{tank(t)}, nil, rich, (&recorder{}).launch, nil), 80, 24)
	for _, c := range []struct {
		msg   Finished
		title string
	}{
		{Finished{"坦克大战", 3, nil}, "游戏异常退出"},
		{Finished{"坦克大战", 0, errors.New("找不到游戏程序")}, "无法启动"},
		{Finished{"坦克大战", -2, nil}, ""},
		{Finished{"坦克大战", 130, nil}, ""},
		{Finished{"坦克大战", 0, nil}, ""},
	} {
		next, _ := m.Update(c.msg)
		got := ""
		if n := next.(Model).notice; n != nil {
			got = n.Title
		}
		if got != c.title {
			t.Errorf("%+v: %q, want %q", c.msg, got, c.title)
		}
	}
}

func TestCapabilityHintsDoNotBlockLaunch(t *testing.T) {
	r := &recorder{}
	wants := tank(t)
	wants.Terminal.Color, wants.Terminal.Unicode = "256", "required"
	mono := screen.Theme{Profile: screen.Mono}
	m := sized(New([]catalog.Entry{wants}, nil, mono, r.launch, nil), 80, 24)
	if !strings.Contains(plain(m), "建议使用 256 色终端") {
		t.Error("color hint")
	}
	eight := sized(New([]catalog.Entry{wants}, nil, screen.Theme{Profile: screen.ANSI8, Unicode: true}, r.launch, nil), 80, 24)
	wants.Terminal.Color = "16"
	eight.games[0] = wants
	if !strings.Contains(plain(eight), "建议使用 16 色终端") {
		t.Error("8 colors are not 16")
	}
	wants.Terminal.Color = "optional"
	eight.games[0] = wants
	eight.theme.Unicode = false
	if !strings.Contains(plain(eight), "需要 UTF-8 终端") {
		t.Error("unicode hint follows the locale")
	}
	if m, _ = press(m, "enter"); len(r.opened) != 1 {
		t.Error("hints never block")
	}
}

func TestAsciiThemeAndTinyWindows(t *testing.T) {
	ascii := screen.Theme{Profile: screen.Color256, Rich: false}
	m := sized(New([]catalog.Entry{tank(t)}, nil, ascii, (&recorder{}).launch, nil), 80, 24)
	view := plain(m)
	// ASCII 模式下不得出现歧义宽度字符，否则“显示为双宽”的终端仍会错位。
	if !strings.Contains(view, "v!") || strings.ContainsAny(view, "─·│╭") || !strings.Contains(view, "方向键") {
		t.Error("ascii fallback")
	}
	for _, theme := range []screen.Theme{ascii, rich} {
		m.theme = theme
		for _, size := range [][2]int{{1, 1}, {30, 10}, {80, 24}, {120, 40}} {
			m = sized(m, size[0], size[1])
			// 用 Bubble Tea 自己的宽度算法量渲染结果：每行都要比窗口窄一列。
			for _, line := range strings.Split(m.View(), "\n") {
				if ansi.StringWidth(line) > max(size[0]-1, 0) {
					t.Errorf("%v: line reaches the last column: %q", size, ansi.Strip(line))
				}
			}
		}
	}
	if !strings.Contains(plain(sized(m, 30, 10)), "窗口太小") {
		t.Error("small window message")
	}
	if _, cmd := press(sized(m, 30, 10), "q"); cmd == nil {
		t.Error("q quits from a small window")
	}
}

func TestStartGameWaitsForWindowSize(t *testing.T) {
	r := &recorder{}
	game := tank(t)
	m := New([]catalog.Entry{game}, nil, rich, r.launch, &game)
	if m.View() != "" || len(r.opened) != 0 {
		t.Fatal("nothing before the size is known")
	}
	if next, cmd := m.Update(tea.WindowSizeMsg{Width: 80, Height: 24}); cmd == nil || len(r.opened) != 1 || next.(Model).start != nil {
		t.Error("--game opens once the size is known")
	}
}
