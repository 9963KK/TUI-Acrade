package lobby

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/x/ansi"
	"tuiarcade/platform/internal/catalog"
	"tuiarcade/platform/internal/install"
	"tuiarcade/platform/internal/paths"
	"tuiarcade/platform/internal/registry"
)

func platform(t *testing.T) Platform {
	t.Helper()
	root := t.TempDir()
	m := install.New(paths.Roots{Programs: filepath.Join(root, "programs"), Data: filepath.Join(root, "data"), Logs: filepath.Join(root, "logs"), Cache: filepath.Join(root, "cache")}, root)
	game := filepath.Join(root, "games", "demo")
	os.MkdirAll(game, 0o755)
	raw, _ := json.Marshal(map[string]any{"manifest_version": 1, "id": "demo", "name": "测试游戏", "version": "1.0.0", "authors": []string{"tester"}, "launch": map[string]any{"argv": []string{"{python}", "-c", "print('GAME')"}}})
	os.WriteFile(filepath.Join(game, "game.json"), raw, 0o644)
	p := NewPlatform(m, rich, nil, nil)
	p.width, p.height = 80, 24
	return p
}

func platformKey(p Platform, typ tea.KeyType, runes string) (Platform, tea.Cmd) {
	next, cmd := p.Update(tea.KeyMsg{Type: typ, Runes: []rune(runes)})
	return next.(Platform), cmd
}

func TestFirstRunDefaultsToInstallAndOnlyConfirmedOperationsRun(t *testing.T) {
	p := platform(t)
	if p.page != "start" || p.selection != 1 || !strings.Contains(ansi.Strip(p.View()), "启动界面") {
		t.Fatal(p.page)
	}
	p, cmd := platformKey(p, tea.KeyEnter, "")
	if cmd == nil || p.page != "install" {
		t.Fatal("install navigation")
	}
	next, _ := p.Update(cmd())
	p = next.(Platform)
	p, cmd = platformKey(p, tea.KeyEnter, "")
	if cmd != nil || p.action != "install" || p.notice.Title != "确认安装" {
		t.Fatal("confirmation omitted")
	}
	p, _ = platformKey(p, tea.KeyEsc, "")
	if p.notice != nil || p.candidate != nil {
		t.Fatal("cancel did not clear candidate")
	}
	p, _ = platformKey(p, tea.KeyEnter, "")
	p, cmd = platformKey(p, tea.KeyEnter, "")
	if cmd == nil || !p.busy {
		t.Fatal("confirmed install did not hand terminal over")
	}
}

func TestLocalInputPreservesCaseGitIsConfirmedBeforeCloneAndQuitReturns(t *testing.T) {
	p := platform(t)
	p.page = "install"
	p.selection = len(p.choices)
	p, _ = platformKey(p, tea.KeyEnter, "")
	if p.page != "input" {
		t.Fatal(p.page)
	}
	p, _ = platformKey(p, tea.KeyRunes, "https://example.invalid/CaseSensitive.git")
	if !strings.Contains(p.input, "CaseSensitive") {
		t.Fatal("path lowercased")
	}
	p, cmd := platformKey(p, tea.KeyEnter, "")
	if cmd != nil || p.action != "clone" {
		t.Fatal("git ran before confirmation")
	}
	p, _ = platformKey(p, tea.KeyRunes, "n")
	p, _ = platformKey(p, tea.KeyEsc, "")
	if p.page != "install" {
		t.Fatal(p.page)
	}
	p, _ = platformKey(p, tea.KeyRunes, "q")
	if p.page != "start" {
		t.Fatal(p.page)
	}
	p, cmd = platformKey(p, tea.KeyRunes, "q")
	if cmd == nil {
		t.Fatal("start does not quit")
	}
}

func TestGallerySearchAndBackAndRepairReport(t *testing.T) {
	r := &recorder{}
	entries := []catalog.Entry{tank(t), {ID: "snake", Name: "贪吃蛇", Presentation: catalog.Presentation{NameEn: "SNAKE"}, Terminal: catalog.DefaultTerminal}}
	m := sized(New(entries, nil, rich, r.launch, nil), 80, 24)
	m.back = true
	m, _ = press(m, "/")
	m, _ = press(m, "SNAKE")
	if len(m.games) != 1 || m.games[0].ID != "snake" {
		t.Fatal(m.games)
	}
	m, _ = press(m, "enter")
	m, _ = press(m, "esc")
	if len(m.games) != 2 || m.query != "" {
		t.Fatal(m.games)
	}
	_, cmd := press(m, "q")
	if _, ok := cmd().(Back); !ok {
		t.Fatal("gallery exits entire program")
	}
	m.games[0].Issue = "缺少模块"
	m, _ = press(m, "enter")
	if m.notice == nil || !strings.Contains(m.notice.Title, "检查报告") || len(r.opened) != 0 {
		t.Fatal("repair entry launched")
	}
}

func TestPlatformAllPagesSmallWindowsAndNoticesRender(t *testing.T) {
	p := platform(t)
	for _, size := range [][2]int{{80, 24}, {120, 40}, {30, 10}} {
		for _, page := range []string{"start", "install", "input", "gallery"} {
			p.width, p.height = size[0], size[1]
			p.page = page
			next, _ := p.Update(tea.WindowSizeMsg{Width: p.width, Height: p.height})
			p = next.(Platform)
			for _, notice := range []*Notice{nil, {"检查报告", []string{strings.Repeat("长", 200), "测试"}}} {
				p.notice = notice
				if p.View() == "" {
					t.Fatal("empty view")
				}
			}
		}
	}
}

func TestPlatformForwardsGameFailureAndShowsCheckReport(t *testing.T) {
	p := platform(t)
	p.page = "gallery"
	next, _ := p.Update(Finished{Name: "测试游戏", Code: 3})
	p = next.(Platform)
	if p.gallery.notice == nil || p.gallery.notice.Title != "游戏异常退出" {
		t.Fatal("exit result was lost")
	}
	p.gallery.notice = nil
	entry := tank(t)
	entry.Issue = "缺少模块"
	_, err := registry.Update(p.manager.RecordPath(), func(f *registry.File) error {
		f.Put(registry.Record{ID: entry.ID, Status: registry.NeedsRepair, Checks: []registry.Check{{Name: "模块", Detail: "curses"}}, LogFile: "install.log"})
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	p.gallery = p.newGallery([]catalog.Entry{entry}, nil)
	p, _ = platformKey(p, tea.KeyEnter, "")
	if p.gallery.notice == nil || !strings.Contains(strings.Join(p.gallery.notice.Lines, " "), "curses") {
		t.Fatal("no stored report")
	}
}

func TestPlatformInstallResultsAndMissingRecordAreVisible(t *testing.T) {
	p := platform(t)
	p.page = "install"
	p.selection = 0
	c, err := p.manager.Builtin("demo")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := p.manager.Install(c); err != nil {
		t.Fatal(err)
	}
	next, _ := p.Update(operated{title: "安装完成"})
	p = next.(Platform)
	if p.notice.Title != "安装完成" || len(p.gallery.games) != 1 {
		t.Fatal("stale games")
	}
	p, _ = platformKey(p, tea.KeyEnter, "")
	p, _ = platformKey(p, tea.KeyEnter, "")
	if p.action != "uninstall" {
		t.Fatal("installed row does not confirm uninstall")
	}
	p, _ = platformKey(p, tea.KeyEsc, "")
	next, _ = p.Update(loaded{err: registry.ErrUnreadable})
	p = next.(Platform)
	if p.notice == nil || p.notice.Title != "无法读取安装记录" {
		t.Fatal("lost registry error")
	}
}
