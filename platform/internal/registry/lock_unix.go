//go:build !windows

package registry

import (
	"os"
	"path/filepath"

	"golang.org/x/sys/unix"
)

// Lock 获取独占锁；进程退出时内核自动释放，避免留下失效的锁。
func Lock(path string) (func(), error) {
	return lock(path, unix.LOCK_EX)
}

// TryLock 获取非阻塞租约，活动安装被占用时立即返回错误。
func TryLock(path string) (func(), error) { return lock(path, unix.LOCK_EX|unix.LOCK_NB) }

func lock(path string, mode int) (func(), error) {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return nil, err
	}
	file, err := os.OpenFile(path, os.O_CREATE|os.O_RDWR, 0o644)
	if err != nil {
		return nil, err
	}
	if err := unix.Flock(int(file.Fd()), mode); err != nil {
		file.Close()
		return nil, err
	}
	return func() {
		_ = unix.Flock(int(file.Fd()), unix.LOCK_UN)
		file.Close()
	}, nil
}
