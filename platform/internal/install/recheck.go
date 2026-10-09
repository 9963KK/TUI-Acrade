package install

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"time"

	"tuiarcade/platform/internal/catalog"
	"tuiarcade/platform/internal/registry"
)

// 检查已登记游戏时持有游戏锁，试运行和卸载不能同时发生。
func (m *Manager) CheckRegistered(id string, run bool) ([]registry.Check, error) {
	release, err := m.gameLock(id)
	if err != nil {
		return nil, err
	}
	defer release()
	f, err := registry.Load(m.RecordPath())
	if err != nil {
		return nil, err
	}
	r := f.Find(id)
	if r == nil {
		return nil, fmt.Errorf("游戏 %q 尚未安装", id)
	}
	logPath := filepath.Join(m.Roots.GameLogs(id), "check.log")
	if err := os.MkdirAll(filepath.Dir(logPath), 0o755); err != nil {
		return nil, err
	}
	log, err := os.OpenFile(logPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		return nil, err
	}
	defer log.Close()
	worker := *m
	worker.Out = io.MultiWriter(m.Out, log)
	entry, err := catalog.Parse(filepath.Join(r.Path, catalog.Manifest), catalog.Source(r.Source), m.Host)
	var checks []registry.Check
	if err != nil {
		checks = []registry.Check{{Name: "清单", Detail: err.Error()}}
	} else if entry.ID != id {
		checks = []registry.Check{{Name: "清单", Detail: "游戏 ID 已改变"}}
	} else {
		checks = worker.Check(entry, r.Python, run)
	}
	for _, line := range Report(checks) {
		fmt.Fprintln(log, line)
	}
	problem := Problem(checks)
	fingerprint, hashErr := Fingerprint(r.Path)
	_, err = registry.Update(m.RecordPath(), func(current *registry.File) error {
		latest := current.Find(id)
		if latest == nil || latest.InstalledAt != r.InstalledAt {
			return nil
		}
		latest.Checks, latest.CheckedAt, latest.LogFile = checks, time.Now().UTC(), logPath
		if problem != "" {
			latest.Status, latest.Problem = registry.NeedsRepair, problem
		} else if run {
			latest.Status, latest.Problem = registry.Installed, ""
		}
		if hashErr == nil {
			latest.Fingerprint = fingerprint
		}
		return nil
	})
	if err != nil {
		return checks, err
	}
	fmt.Fprintln(m.Out, "日志：", logPath)
	return checks, nil
}
