//go:build !windows

package install

import (
	"fmt"
	"io"
	"os/exec"
	"syscall"
	"time"

	"github.com/creack/pty"
)

// Smoke 按大厅的启动方式在指定尺寸的伪终端中检查画面、崩溃与退出响应。
func Smoke(argv, env []string, dir string, columns, rows int) SmokeResult {
	if len(argv) == 0 {
		return SmokeResult{Detail: "无法启动：入口为空"}
	}
	cmd := exec.Command(argv[0], argv[1:]...)
	cmd.Dir, cmd.Env = dir, env
	terminal, err := pty.StartWithSize(cmd, &pty.Winsize{Cols: uint16(columns), Rows: uint16(rows)})
	if err != nil {
		return SmokeResult{Detail: "无法启动：" + err.Error()}
	}
	defer terminal.Close()
	// 同时清理游戏派生的子进程，试运行不能留下后台任务。
	defer syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
	out := &transcript{first: make(chan struct{}), answer: func(b []byte) { terminal.Write(b) }}
	go io.Copy(out, terminal)
	done := make(chan error, 1)
	go func() { done <- cmd.Wait() }()

	result := func(ok bool, detail string) SmokeResult {
		return SmokeResult{OK: ok, Detail: detail, Output: out.tail()}
	}
	exited := func(err error) string {
		code := 0
		if exit, ok := err.(*exec.ExitError); ok {
			if status, ok := exit.Sys().(syscall.WaitStatus); ok && status.Signaled() {
				return "被信号 " + status.Signal().String() + " 结束"
			}
			code = exit.ExitCode()
		}
		return fmt.Sprintf("退出码 %d", code)
	}

	select {
	case <-out.first:
	case err := <-done:
		// 退出与最后一段输出几乎同时到达，稍等输出读完再判断是否出现过画面。
		time.Sleep(50 * time.Millisecond)
		select {
		case <-out.first:
			if err == nil {
				return result(true, "输出画面后自行正常结束")
			}
			return result(false, "启动后崩溃（"+exited(err)+"）")
		default:
		}
		return result(false, "还没有画面就结束了（"+exited(err)+"）")
	case <-time.After(firstOutput):
		syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
		<-done
		return result(false, fmt.Sprintf("%d 秒内没有画面输出", int(firstOutput/time.Second)))
	}
	select {
	case err := <-done:
		if err == nil {
			return result(true, "输出画面后自行正常结束")
		}
		return result(false, "启动后崩溃（"+exited(err)+"）")
	case <-time.After(settle):
	}
	// 与玩家一样按 Ctrl-C；游戏若在原始模式下读取按键，收到的是 0x03，同样应当退出。
	terminal.Write([]byte{3})
	select {
	case <-done:
		return result(true, "画面正常，Ctrl-C 可以退出")
	case <-time.After(exitWait):
	}
	syscall.Kill(-cmd.Process.Pid, syscall.SIGTERM)
	select {
	case <-done:
		return result(true, "画面正常；Ctrl-C 无效，SIGTERM 可以退出")
	case <-time.After(exitWait):
	}
	syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
	<-done
	return result(false, "无法用 Ctrl-C 或 SIGTERM 退出")
}
