package install

import (
	"errors"
	"os"
	"path/filepath"
	"strings"

	"tuiarcade/platform/internal/registry"
)

func (m *Manager) gameLock(id string) (func(), error) {
	if !validID(id) {
		return nil, errors.New("非法游戏 ID")
	}
	release, err := registry.TryLock(filepath.Join(m.Roots.Data, ".locks", id+".lock"))
	if err != nil {
		return nil, errors.New("游戏正在运行或另一个窗口正在安装／卸载，请稍后重试")
	}
	return release, nil
}

func (m *Manager) ownedEnv(path, id string) bool {
	parent := filepath.Join(m.Roots.Programs, "envs", id)
	return filepath.Dir(path) == parent && strings.HasPrefix(filepath.Base(path), "runtime-")
}

func (m *Manager) safeRemoval(path string) error {
	parent, err := filepath.EvalSymlinks(filepath.Dir(path))
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil {
		return err
	}
	root, err := filepath.EvalSymlinks(m.Roots.Programs)
	if err != nil {
		return err
	}
	rel, err := filepath.Rel(root, parent)
	if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return errors.New("平台目录的符号链接指向外部，拒绝删除")
	}
	return nil
}

func (m *Manager) cleanEnvironments(f registry.File) error {
	root := filepath.Join(m.Roots.Programs, "envs")
	if err := m.safeRemoval(filepath.Join(root, "check")); err != nil {
		return err
	}
	games, err := os.ReadDir(root)
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil {
		return err
	}
	for _, game := range games {
		if !game.IsDir() || !validID(game.Name()) {
			continue
		}
		parent := filepath.Join(root, game.Name())
		envs, err := os.ReadDir(parent)
		if err != nil {
			return err
		}
		for _, env := range envs {
			if !env.IsDir() || !strings.HasPrefix(env.Name(), "runtime-") {
				continue
			}
			path := filepath.Join(parent, env.Name())
			if record := f.Find(game.Name()); record != nil && record.Env == path {
				continue
			}
			release, err := registry.TryLock(filepath.Join(path, ".lease"))
			if err != nil {
				continue
			}
			release()
			if err := os.RemoveAll(path); err != nil {
				return err
			}
		}
	}
	return nil
}

// 创建目录和租约时持有记录锁，避免启动清理误删刚创建的目录。
func (m *Manager) leasedDirectory(root, prefix string) (string, func(), error) {
	unlock, err := registry.Lock(m.RecordPath() + ".lock")
	if err != nil {
		return "", nil, err
	}
	defer unlock()
	if _, err := registry.Load(m.RecordPath()); err != nil {
		return "", nil, err
	}
	if err := os.MkdirAll(root, 0o755); err != nil {
		return "", nil, err
	}
	if err := m.safeRemoval(filepath.Join(root, "check")); err != nil {
		return "", nil, err
	}
	path, err := os.MkdirTemp(root, prefix)
	if err != nil {
		return "", nil, err
	}
	release, err := registry.Lock(filepath.Join(path, ".lease"))
	if err != nil {
		_ = os.RemoveAll(path)
		return "", nil, err
	}
	return path, release, nil
}
