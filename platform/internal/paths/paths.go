// Package paths resolves per-OS locations for installed programs, game data, logs and cache.
//
// 规则与 kit/arcade_kit/paths.py 保持一致（docs/architecture.md 第 6 节）：平台据此分配目录，
// Python 游戏单独运行时用同一规则找到同一位置。两边的测试使用相同的期望值。
package paths

import (
	"os"
	"os/user"
	"path/filepath"
	"runtime"
	"strings"
)

// Roots are the four top-level locations the platform manages.
type Roots struct {
	Programs string
	Data     string
	Logs     string
	Cache    string
}

// System maps a GOOS value to the system names used in manifests.
func System(goos string) string {
	switch goos {
	case "windows":
		return "windows"
	case "darwin":
		return "macos"
	}
	return "linux"
}

// Resolve computes roots from an environment lookup, system name, home directory and working directory.
// Every returned path is absolute: they are injected into games whose working directory differs.
func Resolve(getenv func(string) string, system, home, cwd string) Roots {
	r := resolve(getenv, system, home, cwd)
	absolute := func(path string) string {
		if filepath.IsAbs(path) {
			return path
		}
		return filepath.Join(cwd, path)
	}
	return Roots{absolute(r.Programs), absolute(r.Data), absolute(r.Logs), absolute(r.Cache)}
}

func resolve(getenv func(string) string, system, home, cwd string) Roots {
	// 整体改到一个目录下，用于测试、便携安装或多份独立环境；
	// 相对路径转为绝对路径，因为这些目录会注入给工作目录不同的游戏进程。
	if base := getenv("TUI_ARCADE_HOME"); base != "" {
		switch {
		case filepath.IsAbs(base):
		case filepath.VolumeName(base) != "" || strings.HasPrefix(base, `\`):
			// Windows 上的 C:foo、\foo 相对于某个盘的当前目录，交给系统解析。
			if resolved, err := filepath.Abs(base); err == nil {
				base = resolved
			}
		default:
			base = filepath.Join(cwd, base)
		}
		return Roots{filepath.Join(base, "programs"), filepath.Join(base, "data"),
			filepath.Join(base, "logs"), filepath.Join(base, "cache")}
	}
	if system == "windows" {
		local := getenv("LOCALAPPDATA")
		if local == "" {
			local = filepath.Join(home, "AppData", "Local")
		}
		data := filepath.Join(local, "tui-arcade")
		return Roots{filepath.Join(local, "Programs", "tui-arcade"), data,
			filepath.Join(data, "logs"), filepath.Join(data, "cache")}
	}
	// XDG 规范要求忽略相对路径的取值。
	xdg := func(key string) string {
		if value := getenv(key); value != "" && filepath.IsAbs(value) {
			return filepath.Join(value, "tui-arcade")
		}
		return ""
	}
	or := func(value, fallback string) string {
		if value != "" {
			return value
		}
		return fallback
	}
	if system == "macos" {
		// 显式设置的 XDG 变量优先，方便习惯 XDG 的用户与测试隔离；目录结构与 Linux 一致。
		support := or(xdg("XDG_DATA_HOME"), filepath.Join(home, "Library", "Application Support", "TUI Arcade"))
		logs := filepath.Join(home, "Library", "Logs", "TUI Arcade")
		if state := xdg("XDG_STATE_HOME"); state != "" {
			logs = filepath.Join(state, "logs")
		}
		return Roots{filepath.Join(support, "programs"), support, logs,
			or(xdg("XDG_CACHE_HOME"), filepath.Join(home, "Library", "Caches", "TUI Arcade"))}
	}
	data := or(xdg("XDG_DATA_HOME"), filepath.Join(home, ".local", "share", "tui-arcade"))
	state := or(xdg("XDG_STATE_HOME"), filepath.Join(home, ".local", "state", "tui-arcade"))
	return Roots{filepath.Join(data, "programs"), data, filepath.Join(state, "logs"),
		or(xdg("XDG_CACHE_HOME"), filepath.Join(home, ".cache", "tui-arcade"))}
}

// Current resolves roots for the running process.
func Current() Roots {
	home, err := os.UserHomeDir()
	if err != nil || !filepath.IsAbs(home) {
		// 未设置 HOME 时与 Python 的 Path.home() 一致，改从用户数据库取家目录。
		if u, err := user.Current(); err == nil && filepath.IsAbs(u.HomeDir) {
			home = u.HomeDir
		}
	}
	cwd, _ := os.Getwd()
	return Resolve(os.Getenv, System(runtime.GOOS), home, cwd)
}

// GameData is the private data directory assigned to one game.
func (r Roots) GameData(id string) string { return filepath.Join(r.Data, "games", id) }

// GameLogs is the private log directory assigned to one game.
func (r Roots) GameLogs(id string) string { return filepath.Join(r.Logs, id) }
