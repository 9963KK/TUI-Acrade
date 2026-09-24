package launcher

import (
	"os"
	"os/exec"

	"golang.org/x/sys/windows"
)

var (
	kernel32                = windows.NewLazySystemDLL("kernel32.dll")
	getConsoleOutputCP      = kernel32.NewProc("GetConsoleOutputCP")
	setConsoleOutputCP      = kernel32.NewProc("SetConsoleOutputCP")
	flushConsoleInputBuffer = kernel32.NewProc("FlushConsoleInputBuffer")
)

// consoleState is the Windows counterpart of termios: both console modes plus the output code page
// (docs/game-integration.md §3.2).
type consoleState struct {
	input, output windows.Handle
	inMode        uint32
	outMode       uint32
	codePage      uintptr
	ok            bool
}

var handoffSignals = []os.Signal{os.Interrupt}

// writeReset 需要虚拟终端处理：Bubble Tea 释放终端时已把输出模式还原，经典 conhost 下可能不含 VT，
// 直接写入会把转义序列当作文字显示。临时打开 VT 输出，写完再恢复。
func writeReset() {
	out := windows.Handle(os.Stdout.Fd())
	var mode uint32
	if windows.GetConsoleMode(out, &mode) != nil {
		return
	}
	if windows.SetConsoleMode(out, mode|windows.ENABLE_VIRTUAL_TERMINAL_PROCESSING) != nil {
		return
	}
	os.Stdout.WriteString(Reset)
	_ = windows.SetConsoleMode(out, mode)
}

func saveTerminal() *consoleState {
	s := &consoleState{input: windows.Handle(os.Stdin.Fd()), output: windows.Handle(os.Stdout.Fd())}
	if windows.GetConsoleMode(s.input, &s.inMode) != nil || windows.GetConsoleMode(s.output, &s.outMode) != nil {
		return nil
	}
	s.codePage, _, _ = getConsoleOutputCP.Call()
	s.ok = true
	return s
}

func restoreTerminal(s *consoleState) {
	if s == nil || !s.ok {
		return
	}
	// 丢弃游戏退出时残留的按键，再恢复控制台模式（含虚拟终端处理）与代码页。
	flushConsoleInputBuffer.Call(uintptr(s.input))
	_ = windows.SetConsoleMode(s.input, s.inMode)
	_ = windows.SetConsoleMode(s.output, s.outMode)
	if s.codePage != 0 {
		setConsoleOutputCP.Call(s.codePage)
	}
}

func signalCode(*exec.ExitError) (int, bool) { return 0, false }
