// Package install 准备运行环境、检查、登记和卸载游戏，见 docs/game-installation.md。
package install

import (
	"context"
	"fmt"
	"os/exec"
	"strings"
	"time"

	"tuiarcade/platform/internal/catalog"
)

// Interpreter 表示本机发现的 Python 解释器。
type Interpreter struct {
	Path    string
	Version catalog.Version
}

func probe(path string) (catalog.Version, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	out, err := exec.CommandContext(ctx, path, "-c", "import sys;print('%d.%d.%d' % tuple(sys.version_info[:3]))").Output()
	if err != nil {
		return catalog.Version{}, err
	}
	return catalog.ParseVersion(strings.TrimSpace(string(out)))
}

// candidates 优先尝试 TUI_ARCADE_PYTHON，其次为 PATH 中的 python3、python、python3.<n>。
func candidates(getenv func(string) string) []string {
	var names []string
	if configured := getenv("TUI_ARCADE_PYTHON"); configured != "" {
		names = append(names, configured)
	}
	names = append(names, "python3", "python")
	for minor := 20; minor >= 8; minor-- {
		names = append(names, fmt.Sprintf("python3.%d", minor))
	}
	seen := map[string]bool{}
	var paths []string
	for _, name := range names {
		path, err := exec.LookPath(name)
		if err != nil || seen[path] {
			continue
		}
		seen[path] = true
		paths = append(paths, path)
	}
	return paths
}

// FindPython 返回首个符合版本要求的解释器，失败时说明找到的版本。
func FindPython(want catalog.Constraint, getenv func(string) string) (Interpreter, string) {
	var found []string
	for _, path := range candidates(getenv) {
		version, err := probe(path)
		if err != nil {
			continue
		}
		if want.Allows(version) {
			return Interpreter{path, version}, ""
		}
		found = append(found, fmt.Sprintf("%s（%s）", version, path))
	}
	if len(found) == 0 {
		return Interpreter{}, fmt.Sprintf("需要 Python %s，本机未找到 Python；可设置 TUI_ARCADE_PYTHON", want)
	}
	return Interpreter{}, fmt.Sprintf("需要 Python %s，本机只有 %s", want, strings.Join(found, "、"))
}

// MissingModules 用新的解释器进程导入模块，返回导入失败的模块名。
func MissingModules(python string, modules []string) ([]string, error) {
	if len(modules) == 0 {
		return nil, nil
	}
	script := "import importlib,sys\nfor name in sys.argv[1:]:\n    try:\n        importlib.import_module(name)\n    except Exception:\n        print(name)\n"
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	out, err := exec.CommandContext(ctx, python, append([]string{"-c", script}, modules...)...).Output()
	if err != nil {
		return nil, fmt.Errorf("无法运行 %s：%v", python, err)
	}
	return strings.Fields(string(out)), nil
}
