package launcher

import (
	"os"
	"path/filepath"
	"runtime"
	"slices"
	"strings"
	"testing"

	"tuiarcade/platform/internal/catalog"
	"tuiarcade/platform/internal/paths"
)

func entry(root string, argv ...string) catalog.Entry {
	return catalog.Entry{ID: "demo", Name: "演示", Argv: argv, Root: root, Cwd: root, ManagedData: true,
		Source: catalog.Dev, Terminal: catalog.DefaultTerminal}
}

func lookup(env []string, key string) (string, bool) {
	for _, pair := range env {
		if k, v, ok := strings.Cut(pair, "="); ok && k == key {
			return v, true
		}
	}
	return "", false
}

func TestEnvReplacesPlatformKeysAndKeepsTheRest(t *testing.T) {
	roots := paths.Resolve(func(string) string { return "" }, "linux", "/home/u", "/")
	env := Env(entry("/g", "./x"), []string{"PATH=/bin", "PYTHONPATH=/mine", "TUI_ARCADE_DATA_DIR=/evil"}, roots)
	for key, want := range map[string]string{
		"TUI_ARCADE_DATA_DIR": roots.GameData("demo"), "TUI_ARCADE_LOG_DIR": roots.GameLogs("demo"),
		"TUI_ARCADE_GAME_ID": "demo", "TUI_ARCADE_PROTOCOL": "1", "TUI_ARCADE_LAUNCHER": "1", "PYTHONPATH": "/mine",
	} {
		if got, _ := lookup(env, key); got != want {
			t.Errorf("%s = %q, want %q", key, got, want)
		}
	}
	if slices.Contains(env, "TUI_ARCADE_DATA_DIR=/evil") {
		t.Error("inherited data dir must be replaced")
	}
	unmanaged := entry("/g", "./x")
	unmanaged.ManagedData = false
	if _, ok := lookup(Env(unmanaged, nil, roots), "TUI_ARCADE_DATA_DIR"); ok {
		t.Error("unmanaged games get no data dir")
	}
}

func TestPrepareChecksBeforeHandoff(t *testing.T) {
	home := t.TempDir()
	roots := paths.Resolve(func(k string) string { return map[string]string{"TUI_ARCADE_HOME": home}[k] }, "linux", "", "/")
	if _, problem := Prepare(entry(home, "./bin/game"), nil, roots, ""); problem != "游戏入口缺失，请重新安装" {
		t.Errorf("missing entry: %q", problem)
	}
	if _, problem := Prepare(entry(home, "{python}", "main.py"), nil, roots, ""); !strings.Contains(problem, "Python") {
		t.Errorf("missing python: %q", problem)
	}
	blocked := entry(home, "./x")
	blocked.Issue = "需要更新平台（清单协议 9）"
	if _, problem := Prepare(blocked, nil, roots, ""); problem != blocked.Issue {
		t.Errorf("issue: %q", problem)
	}
	game, problem := Prepare(entry(home, "{python}", "{dir}/main.py"), nil, roots, "/usr/bin/python3")
	if problem != "" || game.Argv[0] != "/usr/bin/python3" || game.Argv[1] != home+"/main.py" {
		t.Fatalf("%v %q", game, problem)
	}
	for _, dir := range []string{roots.GameData("demo"), roots.GameLogs("demo")} {
		if info, err := os.Stat(dir); err != nil || !info.IsDir() {
			t.Errorf("%s not created", dir)
		}
	}
}

func TestRunReportsExitStatusCwdAndSignals(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("POSIX shell")
	}
	home := t.TempDir()
	roots := paths.Resolve(func(k string) string { return map[string]string{"TUI_ARCADE_HOME": home}[k] }, "linux", "", "/")
	script := filepath.Join(home, "game.sh")
	os.WriteFile(script, []byte("#!/bin/sh\npwd > \"$TUI_ARCADE_DATA_DIR/ran\"\nexit 3\n"), 0o755)
	game, _ := Prepare(entry(home, "./game.sh"), os.Environ(), roots, "")
	game.Run()
	if game.ExitCode != 3 || game.Err != nil {
		t.Errorf("exit %d %v", game.ExitCode, game.Err)
	}
	ran, _ := os.ReadFile(filepath.Join(roots.GameData("demo"), "ran"))
	if real, _ := filepath.EvalSymlinks(home); strings.TrimSpace(string(ran)) != real && strings.TrimSpace(string(ran)) != home {
		t.Errorf("cwd %q", ran)
	}
	os.WriteFile(script, []byte("#!/bin/sh\nkill -INT $$\n"), 0o755)
	game.Run()
	if !Interrupted(game.ExitCode) {
		t.Errorf("Ctrl-C exit should count as interrupted: %d", game.ExitCode)
	}
	os.WriteFile(filepath.Join(home, "plain"), []byte("x"), 0o644)
	if _, problem := Prepare(entry(home, "./plain"), nil, roots, ""); problem != "游戏入口不可执行，请重新安装" {
		t.Errorf("non-executable entry: %q", problem)
	}
	if !Quiet() {
		t.Error("a Ctrl-C right after a game belongs to the game")
	}
	missing := &Game{Argv: []string{filepath.Join(home, "none")}, Dir: home}
	missing.Run()
	if missing.Err == nil || !strings.Contains(missing.Err.Error(), "找不到") {
		t.Errorf("missing program: %v", missing.Err)
	}
}
