package launcher

import "golang.org/x/sys/unix"

const (
	ioctlGet = unix.TCGETS
	// TCSETSF：清空未读输入后再设置终端属性，等同 tcsetattr(TCSAFLUSH)。
	ioctlSetFlush = unix.TCSETSF
)
