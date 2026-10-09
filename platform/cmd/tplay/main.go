// Command tplay 安装游戏并将当前终端交给选中的游戏。
package main

import (
	"flag"
	"fmt"
	"io"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"

	tea "github.com/charmbracelet/bubbletea"
	"golang.org/x/term"

	"tuiarcade/platform/internal/catalog"
	"tuiarcade/platform/internal/install"
	"tuiarcade/platform/internal/launcher"
	"tuiarcade/platform/internal/lobby"
	"tuiarcade/platform/internal/paths"
	"tuiarcade/platform/internal/screen"
)

var version = "dev"

func main() { os.Exit(run(os.Args[1:], os.Stdin, os.Stdout, os.Stderr)) }

func repository() string {
	if configured := os.Getenv("TUI_ARCADE_REPO"); configured != "" {
		return catalog.FindRepo(configured)
	}
	if exe, err := os.Executable(); err == nil {
		if real, err := filepath.EvalSymlinks(exe); err == nil {
			return catalog.FindRepo(filepath.Dir(real))
		}
	}
	return ""
}

func run(args []string, in io.Reader, out, errors io.Writer) int {
	manager := install.New(paths.Current(), repository())
	manager.In, manager.Out = in, out
	if len(args) > 0 {
		switch args[0] {
		case "install", "uninstall", "check", "list":
			return command(manager, args, in, out, errors)
		}
	}
	flags := flag.NewFlagSet("tplay", flag.ContinueOnError)
	flags.SetOutput(errors)
	gameID := flags.String("game", "", "launch an installed game; return to the lobby when it exits")
	showVersion := flags.Bool("version", false, "print the version")
	flags.Usage = func() {
		fmt.Fprintln(errors, "用法：tplay [--game ID] | install <ID/路径/git地址> [--yes] | uninstall ID [--yes] | check [ID/路径] [--run] | list")
		flags.PrintDefaults()
	}
	if err := flags.Parse(args); err != nil {
		if err == flag.ErrHelp {
			return 0
		}
		return 2
	}
	if *showVersion {
		fmt.Fprintln(out, "tplay", version)
		return 0
	}
	if flags.NArg() != 0 {
		flags.Usage()
		return 2
	}
	if !term.IsTerminal(int(os.Stdin.Fd())) || !term.IsTerminal(int(os.Stdout.Fd())) {
		fmt.Fprintln(errors, "Please run TUI Arcade in an interactive terminal.")
		return 1
	}
	if err := manager.CleanStaging(); err != nil {
		fmt.Fprintln(errors, "清理中断的安装：", err)
		return 1
	}
	games, err := manager.Library()
	if err != nil {
		fmt.Fprintln(errors, err)
		return 1
	}
	var start *catalog.Entry
	if *gameID != "" {
		for i := range games {
			if games[i].ID == *gameID {
				start = &games[i]
			}
		}
		if start == nil {
			fmt.Fprintf(errors, "游戏 %q 尚未安装，请先运行 tplay install %s\n", *gameID, *gameID)
			return 2
		}
	}
	model := lobby.NewPlatform(manager, screen.NewTheme(os.Getenv), games, start)
	program := tea.NewProgram(model, tea.WithAltScreen(), tea.WithoutSignalHandler())
	signals := make(chan os.Signal, 1)
	signal.Notify(signals, os.Interrupt, syscall.SIGQUIT, syscall.SIGTERM)
	defer signal.Stop(signals)
	go func() {
		for s := range signals {
			if s != syscall.SIGTERM && launcher.Quiet() {
				continue
			}
			program.Send(tea.QuitMsg{})
		}
	}()
	if _, err := program.Run(); err != nil {
		fmt.Fprintln(errors, "tplay:", err)
		return 1
	}
	return 0
}
