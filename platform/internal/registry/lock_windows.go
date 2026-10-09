package registry

import (
	"os"
	"path/filepath"

	"golang.org/x/sys/windows"
)

// Lock 获取独占锁；Windows 在进程退出时自动释放。
func Lock(path string) (func(), error) {
	return lock(path, windows.LOCKFILE_EXCLUSIVE_LOCK)
}

// TryLock 获取非阻塞租约，跳过活动安装。
func TryLock(path string) (func(), error) {
	return lock(path, windows.LOCKFILE_EXCLUSIVE_LOCK|windows.LOCKFILE_FAIL_IMMEDIATELY)
}

func lock(path string, flags uint32) (func(), error) {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return nil, err
	}
	file, err := os.OpenFile(path, os.O_CREATE|os.O_RDWR, 0o644)
	if err != nil {
		return nil, err
	}
	overlapped := new(windows.Overlapped)
	handle := windows.Handle(file.Fd())
	if err := windows.LockFileEx(handle, flags, 0, 1, 0, overlapped); err != nil {
		file.Close()
		return nil, err
	}
	return func() {
		_ = windows.UnlockFileEx(handle, 0, 1, 0, overlapped)
		file.Close()
	}, nil
}
