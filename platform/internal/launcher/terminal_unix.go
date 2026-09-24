//go:build darwin || linux

package launcher

import (
	"os"
	"os/exec"
	"syscall"

	"golang.org/x/sys/unix"
)

// 游戏运行期间由键盘产生、会结束平台的信号。
var handoffSignals = []os.Signal{os.Interrupt, syscall.SIGQUIT}

func writeReset() { os.Stdout.WriteString(Reset) }

// saveTerminal records termios so a game that exits in raw mode cannot leave the lobby broken.
func saveTerminal() *unix.Termios {
	state, err := unix.IoctlGetTermios(int(os.Stdin.Fd()), ioctlGet)
	if err != nil {
		return nil
	}
	return state
}

// restoreTerminal applies the saved termios after discarding pending input (like TCSAFLUSH), so keys the
// player pressed while the game was exiting do not trigger lobby actions.
func restoreTerminal(state *unix.Termios) {
	if state != nil {
		_ = unix.IoctlSetTermios(int(os.Stdin.Fd()), ioctlSetFlush, state)
	}
}

func signalCode(exit *exec.ExitError) (int, bool) {
	if status, ok := exit.Sys().(syscall.WaitStatus); ok && status.Signaled() {
		return -int(status.Signal()), true
	}
	return 0, false
}
