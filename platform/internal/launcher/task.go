package launcher

import (
	"io"
	"os"
	"os/signal"
	"time"
)

// Task 将终端交给前台 git／pip 操作，结束后按游戏交接的规则恢复终端。
type Task struct {
	Do  func(io.Reader, io.Writer) error
	in  io.Reader
	out io.Writer
}

func (t *Task) SetStdin(r io.Reader)  { t.in = r }
func (t *Task) SetStdout(w io.Writer) { t.out = w }
func (t *Task) SetStderr(w io.Writer) { t.out = w }
func (t *Task) Run() error {
	if t.in == nil {
		t.in = os.Stdin
	}
	if t.out == nil {
		t.out = os.Stdout
	}
	saved := saveTerminal()
	handingOff.Store(true)
	signals := make(chan os.Signal, 1)
	signal.Notify(signals, handoffSignals...)
	defer func() {
		signal.Stop(signals)
		handedBack.Store(time.Now().UnixNano())
		handingOff.Store(false)
		writeReset()
		restoreTerminal(saved)
	}()
	return t.Do(t.in, t.out)
}
