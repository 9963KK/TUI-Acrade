// Package launcher hands the current terminal to a game process and takes it back
// (docs/game-integration.md §3). Games run in the foreground of the same terminal window.
package launcher

import (
	"errors"
	"io"
	"io/fs"
	"os"
	"os/exec"
	"os/signal"
	"strconv"
	"strings"
	"sync/atomic"
	"time"

	"tuiarcade/platform/internal/catalog"
	"tuiarcade/platform/internal/paths"
)

// Reset undoes terminal modes a crashed game may leave behind: colors, mouse and focus reporting, bracketed
// paste, the Kitty keyboard protocol, application cursor keys and keypad, a scroll region, disabled
// autowrap, a hidden cursor and the alternate screen.
const Reset = "\x1b[0m\x1b[?1000l\x1b[?1002l\x1b[?1003l\x1b[?1006l\x1b[?1004l\x1b[?2004l\x1b[<u" +
	"\x1b[?1l\x1b>\x1b[r\x1b[?7h\x1b[?25h\x1b[?1049l"

// grace is how long after a game ends a Ctrl-C is still attributed to the game: the signal reaches the
// platform and the game at the same moment, and the game's exit may be noticed first.
const grace = 500 * time.Millisecond

var (
	handingOff atomic.Bool
	handedBack atomic.Int64
)

// Quiet reports whether an interrupt signal belongs to a game rather than to the lobby.
func Quiet() bool {
	return handingOff.Load() || time.Since(time.Unix(0, handedBack.Load())) < grace
}

var platformKeys = []string{"TUI_ARCADE_LAUNCHER", "TUI_ARCADE_PROTOCOL", "TUI_ARCADE_GAME_ID",
	"TUI_ARCADE_DATA_DIR", "TUI_ARCADE_LOG_DIR"}

// Env builds the game's environment; inherited values of the platform keys are replaced by this assignment.
func Env(entry catalog.Entry, environ []string, roots paths.Roots) []string {
	env := make([]string, 0, len(environ)+len(platformKeys))
	for _, pair := range environ {
		key, _, _ := strings.Cut(pair, "=")
		keep := true
		for _, reserved := range platformKeys {
			if strings.EqualFold(key, reserved) {
				keep = false
			}
		}
		if keep {
			env = append(env, pair)
		}
	}
	env = append(env, "TUI_ARCADE_LAUNCHER=1", "TUI_ARCADE_PROTOCOL="+strconv.Itoa(catalog.Protocol),
		"TUI_ARCADE_GAME_ID="+entry.ID, "TUI_ARCADE_LOG_DIR="+roots.GameLogs(entry.ID))
	if entry.ManagedData {
		env = append(env, "TUI_ARCADE_DATA_DIR="+roots.GameData(entry.ID))
	}
	return env
}

// Game is one launch: argv, environment and working directory, resolved before the terminal is handed over.
type Game struct {
	Argv []string
	Env  []string
	Dir  string
	// ExitCode 为负数表示被信号结束（-2 即 SIGINT）。
	ExitCode int
	Err      error
	// Release 释放安装管理器持有的游戏锁，防止运行期间被卸载。
	Release func()
}

// Prepare checks everything that can fail before the lobby gives up the terminal:
// known issues, the interpreter, a present entry and writable private directories.
func Prepare(entry catalog.Entry, environ []string, roots paths.Roots, python string) (*Game, string) {
	if entry.Issue != "" {
		return nil, entry.Issue
	}
	argv, err := entry.Command(python)
	if err != nil {
		return nil, err.Error()
	}
	if strings.HasPrefix(entry.Argv[0], "./") {
		// LookPath 与实际执行的解析一致：检查可执行权限，Windows 上按 PATHEXT 补全扩展名。
		if _, err := exec.LookPath(argv[0]); err != nil {
			if info, statErr := os.Stat(argv[0]); statErr == nil && !info.IsDir() {
				return nil, "游戏入口不可执行，请重新安装"
			}
			return nil, "游戏入口缺失，请重新安装"
		}
	}
	dirs := []string{roots.GameLogs(entry.ID)}
	if entry.ManagedData {
		dirs = append(dirs, roots.GameData(entry.ID))
	}
	for _, dir := range dirs {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return nil, "无法创建数据目录：" + err.Error()
		}
	}
	return &Game{Argv: argv, Env: Env(entry, environ, roots), Dir: entry.Cwd}, ""
}

// Python finds the interpreter for development sources: TUI_ARCADE_PYTHON, then python3 / python on PATH.
func Python(getenv func(string) string) string {
	if configured := getenv("TUI_ARCADE_PYTHON"); configured != "" {
		return configured
	}
	for _, name := range []string{"python3", "python"} {
		if path, err := exec.LookPath(name); err == nil {
			return path
		}
	}
	return ""
}

// Interrupted reports exit statuses that mean the player pressed Ctrl-C, which is a normal way to leave.
func Interrupted(code int) bool {
	return code == -2 || code == 130 || code == 0xC000013A
}

// The lobby's Bubble Tea program calls these while the terminal is released; the game always talks to the
// real terminal files so it sees a TTY, never a pipe.
func (g *Game) SetStdin(io.Reader)  {}
func (g *Game) SetStdout(io.Writer) {}
func (g *Game) SetStderr(io.Writer) {}

// Run executes the game in the foreground and always restores the terminal afterwards.
func (g *Game) Run() error {
	if g.Release != nil {
		defer g.Release()
	}
	saved := saveTerminal()
	handingOff.Store(true)
	// 游戏运行期间平台自己不响应键盘信号（Ctrl-C、Ctrl-\）；用 Notify 捕获而不是忽略，
	// 被捕获的信号在子进程 exec 后恢复默认行为，游戏照常收到。
	signals := make(chan os.Signal, 1)
	signal.Notify(signals, handoffSignals...)
	cmd := exec.Command(g.Argv[0], g.Argv[1:]...)
	cmd.Dir, cmd.Env = g.Dir, g.Env
	cmd.Stdin, cmd.Stdout, cmd.Stderr = os.Stdin, os.Stdout, os.Stderr
	err := cmd.Run()
	handedBack.Store(time.Now().UnixNano())
	handingOff.Store(false)
	signal.Stop(signals)
	writeReset()
	restoreTerminal(saved)
	g.ExitCode, g.Err = status(err)
	return nil
}

func status(err error) (int, error) {
	if err == nil {
		return 0, nil
	}
	var exit *exec.ExitError
	if errors.As(err, &exit) {
		if code, ok := signalCode(exit); ok {
			return code, nil
		}
		return exit.ExitCode(), nil
	}
	switch {
	case errors.Is(err, fs.ErrNotExist):
		return 0, errors.New("找不到游戏程序")
	case errors.Is(err, fs.ErrPermission):
		return 0, errors.New("游戏程序没有执行权限")
	}
	return 0, err
}
