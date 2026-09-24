package paths

import (
	"path/filepath"
	"runtime"
	"testing"
)

// posix 跳过 Windows 主机：Linux / macOS 规则使用 POSIX 绝对路径，只在对应系统上生效。
func posix(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("POSIX path semantics")
	}
}

func env(values map[string]string) func(string) string {
	return func(key string) string { return values[key] }
}

func expect(t *testing.T, got, want string) {
	t.Helper()
	if got != filepath.FromSlash(want) {
		t.Errorf("got %q, want %q", got, filepath.FromSlash(want))
	}
}

// 期望值与 tests/test_paths.py 相同，保证 Go 平台与 Python 工具包对目录的理解一致。

func TestSystemNames(t *testing.T) {
	for goos, want := range map[string]string{"darwin": "macos", "linux": "linux", "windows": "windows", "freebsd": "linux"} {
		if got := System(goos); got != want {
			t.Errorf("System(%q) = %q, want %q", goos, got, want)
		}
	}
}

func TestLinuxFollowsXDG(t *testing.T) {
	posix(t)
	base := Resolve(env(nil), "linux", "/home/u", "/cwd")
	expect(t, base.Data, "/home/u/.local/share/tui-arcade")
	expect(t, base.Programs, "/home/u/.local/share/tui-arcade/programs")
	expect(t, base.Logs, "/home/u/.local/state/tui-arcade/logs")
	expect(t, base.Cache, "/home/u/.cache/tui-arcade")
	custom := Resolve(env(map[string]string{"XDG_DATA_HOME": "/d", "XDG_STATE_HOME": "/s", "XDG_CACHE_HOME": "/c"}),
		"linux", "/home/u", "/cwd")
	expect(t, custom.Data, "/d/tui-arcade")
	expect(t, custom.Logs, "/s/tui-arcade/logs")
	expect(t, custom.Cache, "/c/tui-arcade")
}

func TestMacOSUsesLibraryUnlessXDGIsSet(t *testing.T) {
	posix(t)
	base := Resolve(env(nil), "macos", "/home/u", "/cwd")
	expect(t, base.Data, "/home/u/Library/Application Support/TUI Arcade")
	expect(t, base.Logs, "/home/u/Library/Logs/TUI Arcade")
	expect(t, base.Cache, "/home/u/Library/Caches/TUI Arcade")
	expect(t, Resolve(env(map[string]string{"XDG_DATA_HOME": "/d"}), "macos", "/home/u", "/cwd").Data, "/d/tui-arcade")
	expect(t, Resolve(env(map[string]string{"XDG_STATE_HOME": "/s"}), "macos", "/home/u", "/cwd").Logs, "/s/tui-arcade/logs")
}

func TestWindowsUsesLocalAppData(t *testing.T) {
	posix(t)
	base := Resolve(env(map[string]string{"LOCALAPPDATA": "/L"}), "windows", "/home/u", "/cwd")
	expect(t, base.Programs, "/L/Programs/tui-arcade")
	expect(t, base.Data, "/L/tui-arcade")
	expect(t, base.Logs, "/L/tui-arcade/logs")
}

func TestRelativeLocationsNeverLeakToGames(t *testing.T) {
	posix(t)
	// 家目录缺失时结果仍然是绝对路径。
	if base := Resolve(env(nil), "linux", "", "/cwd"); !filepath.IsAbs(base.Data) || !filepath.IsAbs(base.Logs) {
		t.Errorf("relative roots: %+v", base)
	}
	expect(t, Resolve(env(map[string]string{"XDG_DATA_HOME": "rel"}), "linux", "/home/u", "/cwd").Data,
		"/home/u/.local/share/tui-arcade")
	portable := Resolve(env(map[string]string{"TUI_ARCADE_HOME": "portable"}), "linux", "/home/u", "/cwd")
	expect(t, portable.Data, "/cwd/portable/data")
	expect(t, portable.GameData("tank"), "/cwd/portable/data/games/tank")
	expect(t, portable.GameLogs("tank"), "/cwd/portable/logs/tank")
}
