// Command tplay is the TUI Arcade lobby: it lists games and runs the chosen one in this terminal.
package main

import (
	"flag"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"

	tea "github.com/charmbracelet/bubbletea"
	"golang.org/x/term"

	"tuiarcade/platform/internal/catalog"
	"tuiarcade/platform/internal/launcher"
	"tuiarcade/platform/internal/lobby"
	"tuiarcade/platform/internal/paths"
	"tuiarcade/platform/internal/screen"
)

// version is set at build time with -ldflags "-X main.version=...".
var version = "dev"

func main() { os.Exit(run()) }

func run() int {
	gameID := flag.String("game", "", "launch a game directly; the lobby appears after it exits")
	showVersion := flag.Bool("version", false, "print the version")
	flag.Parse()
	if *showVersion {
		fmt.Println("tplay", version)
		return 0
	}
	roots := paths.Current()
	// 开发来源：可执行文件所在源码仓库的 games/ 与 TUI_ARCADE_DEV_GAMES。不看当前目录，
	// 否则在任意含 games/ 的目录里运行都会加载那里的游戏。
	repo := ""
	if exe, err := os.Executable(); err == nil {
		if real, err := filepath.EvalSymlinks(exe); err == nil {
			repo = catalog.FindRepo(filepath.Dir(real))
		}
	}
	games, problems := catalog.Load(catalog.Dirs(repo, os.Getenv("TUI_ARCADE_DEV_GAMES"), roots.Programs), catalog.CurrentHost())
	var start *catalog.Entry
	if *gameID != "" {
		for i := range games {
			if games[i].ID == *gameID {
				start = &games[i]
			}
		}
		if start == nil {
			fmt.Fprintf(os.Stderr, "tplay: unknown game %q\n", *gameID)
			return 2
		}
	}
	if !term.IsTerminal(int(os.Stdin.Fd())) || !term.IsTerminal(int(os.Stdout.Fd())) {
		fmt.Fprintln(os.Stderr, "Please run TUI Arcade in an interactive terminal.")
		return 1
	}
	python := launcher.Python(os.Getenv)
	launch := func(entry catalog.Entry) (tea.Cmd, string) {
		game, problem := launcher.Prepare(entry, os.Environ(), roots, python)
		if problem != "" {
			return nil, problem
		}
		return lobby.Command(entry, game), ""
	}
	model := lobby.New(games, problems, screen.NewTheme(os.Getenv), launch, start)
	program := tea.NewProgram(model, tea.WithAltScreen(), tea.WithoutSignalHandler())
	// 平台自己处理信号：游戏运行期间及刚结束时的键盘信号（Ctrl-C、Ctrl-\）属于游戏，不能让大厅随之退出。
	signals := make(chan os.Signal, 1)
	signal.Notify(signals, os.Interrupt, syscall.SIGQUIT, syscall.SIGTERM)
	go func() {
		for s := range signals {
			if s != syscall.SIGTERM && launcher.Quiet() {
				continue
			}
			program.Send(tea.QuitMsg{})
		}
	}()
	if _, err := program.Run(); err != nil {
		fmt.Fprintln(os.Stderr, "tplay:", err)
		return 1
	}
	return 0
}
