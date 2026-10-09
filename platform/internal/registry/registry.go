// Package registry 管理 installed.json，决定游戏厅展示哪些游戏，见 docs/game-installation.md §5。
package registry

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"slices"
	"time"
)

// Status 表示已登记游戏的安装状态。
type Status string

const (
	Installed Status = "installed"
	// NeedsRepair 表示曾经安装，但之后的检查未通过；游戏厅显示但不能启动。
	NeedsRepair Status = "needs_repair"
)

// Check 对应检查报告中的一项结果。
type Check struct {
	Name    string `json:"name"`
	OK      bool   `json:"ok"`
	Detail  string `json:"detail,omitempty"`
	Skipped bool   `json:"skipped,omitempty"`
}

// Record 保存一款游戏的安装记录。
type Record struct {
	ID     string `json:"id"`
	Source string `json:"source"`
	// Path 为游戏目录：内置为仓库内目录，git 为克隆目录，本地为登记的目录。
	Path   string `json:"path"`
	URL    string `json:"url,omitempty"`
	Commit string `json:"commit,omitempty"`
	// Python 为 {python} 解析到的解释器；声明依赖时是虚拟环境中的解释器。
	Python      string    `json:"python,omitempty"`
	Env         string    `json:"env,omitempty"`
	Fingerprint string    `json:"fingerprint"`
	Status      Status    `json:"status"`
	Problem     string    `json:"problem,omitempty"`
	Checks      []Check   `json:"checks,omitempty"`
	LogFile     string    `json:"log,omitempty"`
	CheckedAt   time.Time `json:"checked_at"`
	InstalledAt time.Time `json:"installed_at"`
}

// File 保存完整的安装记录。
type File struct {
	Version int      `json:"version"`
	Games   []Record `json:"games"`
}

const version = 1

// ErrUnreadable 表示主记录和备份均无法读取，调用方不得覆盖原记录。
var ErrUnreadable = errors.New("安装记录无法读取")

func read(path string) (File, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return File{}, err
	}
	var f File
	if err := json.Unmarshal(raw, &f); err != nil {
		return File{}, fmt.Errorf("%w: %v", ErrUnreadable, err)
	}
	if f.Version != version {
		return File{}, fmt.Errorf("%w: 版本 %d", ErrUnreadable, f.Version)
	}
	return f, nil
}

// Load 读取安装记录；主记录损坏时读取备份，两者均损坏时返回 ErrUnreadable。
// 主记录和备份都不存在时才视为空记录。
func Load(path string) (File, error) {
	f, err := read(path)
	if err == nil {
		return f, nil
	}
	backup, backupErr := read(path + ".bak")
	if backupErr == nil {
		return backup, nil
	}
	if errors.Is(err, os.ErrNotExist) && errors.Is(backupErr, os.ErrNotExist) {
		return File{Version: version}, nil
	}
	if errors.Is(err, os.ErrNotExist) {
		err = backupErr
	}
	return File{}, fmt.Errorf("%s：%w", path, err)
}

// Save 同步临时文件、保留上一份 .bak 记录，再原子替换主记录。
func Save(path string, f File) error {
	f.Version = version
	raw, err := json.MarshalIndent(f, "", "  ")
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	tmp, err := os.CreateTemp(filepath.Dir(path), ".installed-*.json")
	if err != nil {
		return err
	}
	defer os.Remove(tmp.Name())
	if _, err := tmp.Write(append(raw, '\n')); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Sync(); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	// 先把当前有效记录移为 .bak：两次改名之间若中断，Load 会读到 .bak。
	if _, err := read(path); err == nil {
		if err := rename(path, path+".bak"); err != nil {
			return err
		}
	}
	return rename(tmp.Name(), path)
}

// rename 在 Windows 上短暂重试，避免文件扫描暂时占用目标。
func rename(from, to string) error {
	var err error
	for attempt := 0; attempt < 5; attempt++ {
		if err = os.Rename(from, to); err == nil || runtime.GOOS != "windows" {
			return err
		}
		time.Sleep(50 * time.Millisecond)
	}
	return err
}

// Find 按 ID 查找记录，找不到时返回 nil。
func (f *File) Find(id string) *Record {
	for i := range f.Games {
		if f.Games[i].ID == id {
			return &f.Games[i]
		}
	}
	return nil
}

// Put 添加或替换记录，保留安装顺序。
func (f *File) Put(r Record) {
	if existing := f.Find(r.ID); existing != nil {
		*existing = r
		return
	}
	f.Games = append(f.Games, r)
}

// Remove 删除指定游戏的记录。
func (f *File) Remove(id string) {
	f.Games = slices.DeleteFunc(f.Games, func(r Record) bool { return r.ID == id })
}

// Update 持有跨进程锁读取、修改并保存安装记录。
func Update(path string, change func(*File) error) (File, error) {
	unlock, err := Lock(path + ".lock")
	if err != nil {
		return File{}, err
	}
	defer unlock()
	f, err := Load(path)
	if err != nil {
		return File{}, err
	}
	if err := change(&f); err != nil {
		return f, err
	}
	return f, Save(path, f)
}
