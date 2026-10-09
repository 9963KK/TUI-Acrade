package install

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"

	"tuiarcade/platform/internal/registry"
)

type transaction struct {
	ID   string `json:"id"`
	Kind string `json:"kind"`
}

// 在移动目录前落盘；进程中断后依据安装记录决定恢复还是删除。
func writeTransaction(stage, id, kind string) error {
	raw, err := json.Marshal(transaction{ID: id, Kind: kind})
	if err != nil {
		return err
	}
	f, err := os.CreateTemp(stage, ".transaction-*.json")
	if err != nil {
		return err
	}
	defer f.Close()
	defer os.Remove(f.Name())
	if _, err := f.Write(raw); err != nil {
		return err
	}
	if err := f.Sync(); err != nil {
		return err
	}
	if err := f.Close(); err != nil {
		return err
	}
	return os.Rename(f.Name(), filepath.Join(stage, ".transaction.json"))
}

func (m *Manager) recoverTransaction(stage string, f registry.File) error {
	raw, err := os.ReadFile(filepath.Join(stage, ".transaction.json"))
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil {
		return err
	}
	var tx transaction
	if err := json.Unmarshal(raw, &tx); err != nil {
		return err
	}
	if !validID(tx.ID) {
		return errors.New("中断事务包含非法游戏 ID")
	}
	game := filepath.Join(m.Roots.Programs, "games", tx.ID)
	envs := filepath.Join(m.Roots.Programs, "envs", tx.ID)
	switch tx.Kind {
	case "install":
		if r := f.Find(tx.ID); r != nil && r.Path == game {
			return nil
		}
		return m.restoreMove(game, filepath.Join(stage, "source"))
	case "uninstall":
		if f.Find(tx.ID) == nil {
			return nil
		}
		if err := m.restoreMove(filepath.Join(stage, "game"), game); err != nil {
			return err
		}
		return m.restoreMove(filepath.Join(stage, "envs"), envs)
	default:
		return errors.New("未知中断事务类型")
	}
}

func (m *Manager) restoreMove(from, to string) error {
	if _, err := os.Lstat(from); errors.Is(err, os.ErrNotExist) {
		return nil
	} else if err != nil {
		return err
	}
	if err := m.safeRemoval(from); err != nil {
		return err
	}
	if err := m.safeRemoval(to); err != nil {
		return err
	}
	if _, err := os.Lstat(to); err == nil {
		return errors.New("恢复中断事务时目标目录已存在，请保留暂存目录并检查")
	} else if !errors.Is(err, os.ErrNotExist) {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(to), 0o755); err != nil {
		return err
	}
	return os.Rename(from, to)
}
