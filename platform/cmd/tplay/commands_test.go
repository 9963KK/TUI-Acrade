package main

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"tuiarcade/platform/internal/catalog"
	"tuiarcade/platform/internal/install"
	"tuiarcade/platform/internal/paths"
	"tuiarcade/platform/internal/registry"
)

func setup(t *testing.T) (*install.Manager, string) {
	t.Helper()
	root := t.TempDir()
	repo := filepath.Join(root, "repo")
	t.Setenv("TUI_ARCADE_HOME", filepath.Join(root, "home"))
	t.Setenv("TUI_ARCADE_REPO", repo)
	os.MkdirAll(filepath.Join(repo, "platform"), 0o755)
	os.WriteFile(filepath.Join(repo, "platform", "go.mod"), []byte("module test"), 0o644)
	game := filepath.Join(repo, "games", "demo")
	os.MkdirAll(game, 0o755)
	raw, _ := json.Marshal(map[string]any{"manifest_version": 1, "id": "demo", "name": "Demo", "version": "1.0.0", "authors": []string{"tester"}, "launch": map[string]any{"argv": []string{"{python}", "-c", "print('GAME')"}}})
	os.WriteFile(filepath.Join(game, "game.json"), raw, 0o644)
	m := install.New(paths.Current(), repo)
	m.Out = &bytes.Buffer{}
	return m, game
}

func execute(t *testing.T, m *install.Manager, args []string, input string) (int, string, string) {
	t.Helper()
	out, errs := &bytes.Buffer{}, &bytes.Buffer{}
	m.Out = out
	code := command(m, args, strings.NewReader(input), out, errs)
	return code, out.String(), errs.String()
}

func TestCLIInstallCheckListAndUninstall(t *testing.T) {
	m, path := setup(t)
	if code, out, err := execute(t, m, []string{"list"}, ""); code != 0 || !strings.Contains(out, "尚未安装") {
		t.Fatal(code, out, err)
	}
	if code, out, err := execute(t, m, []string{"install", "demo"}, "n\n"); code != 0 || !strings.Contains(out, "已取消") {
		t.Fatal(code, out, err)
	}
	f, _ := registry.Load(m.RecordPath())
	if len(f.Games) != 0 {
		t.Fatal("cancel installed")
	}
	if code, out, err := execute(t, m, []string{"install", "demo", "--yes"}, ""); code != 0 || !strings.Contains(out, "安装完成") {
		t.Fatal(code, out, err)
	}
	if code, out, err := execute(t, m, []string{"list"}, ""); code != 0 || !strings.Contains(out, "demo\tDemo\t已安装") {
		t.Fatal(code, out, err)
	}
	for _, target := range []string{"demo", path, ""} {
		args := []string{"check", "--run"}
		if target != "" {
			args = append(args, target)
		}
		if code, out, err := execute(t, m, args, ""); code != 0 || !strings.Contains(out, "[通过] 试运行") {
			t.Fatal(code, out, err)
		}
	}
	if code, _, err := execute(t, m, []string{"uninstall", "demo", "--yes"}, ""); code != 0 {
		t.Fatal(err)
	}
	if _, err := os.Stat(path); err != nil {
		t.Fatal("source removed")
	}
}

func TestCLIErrorExitCodesAndArgumentOrder(t *testing.T) {
	m, _ := setup(t)
	for _, args := range [][]string{{"install"}, {"uninstall"}, {"install", "/missing"}, {"check", "/missing"}, {"install", "--bogus"}, {"check", "one", "two"}} {
		if code, _, _ := execute(t, m, args, ""); code == 0 {
			t.Fatal("unexpected success", args)
		}
	}
	o, err := parseOptions([]string{"demo", "--yes", "--keep", "--run"})
	if err != nil || !o.yes || !o.keep || !o.run || o.target != "demo" {
		t.Fatal(o, err)
	}
	if code, out, _ := execute(t, m, []string{"check"}, ""); code != 0 || !strings.Contains(out, "没有检查对象") {
		t.Fatal(out)
	}
}

func TestCLICheckMarksBrokenInstallationAndFullCheckRepairs(t *testing.T) {
	m, path := setup(t)
	if code, _, err := execute(t, m, []string{"install", "demo", "--yes"}, ""); code != 0 {
		t.Fatal(err)
	}
	raw, _ := os.ReadFile(filepath.Join(path, "game.json"))
	os.WriteFile(filepath.Join(path, "game.json"), []byte("broken"), 0o644)
	if code, out, _ := execute(t, m, []string{"check", "demo"}, ""); code != 1 || !strings.Contains(out, "[失败] 清单") {
		t.Fatal(code, out)
	}
	f, _ := registry.Load(m.RecordPath())
	if f.Find("demo").Status != registry.NeedsRepair {
		t.Fatal(f)
	}
	os.WriteFile(filepath.Join(path, "game.json"), raw, 0o644)
	if code, _, err := execute(t, m, []string{"check", "demo", "--run"}, ""); code != 0 {
		t.Fatal(err)
	}
	f, _ = registry.Load(m.RecordPath())
	if f.Find("demo").Status != registry.Installed {
		t.Fatal(f)
	}
}

func TestRunVersionHelpInvalidFlagsAndRepositoryOverride(t *testing.T) {
	_, path := setup(t)
	out, errs := &bytes.Buffer{}, &bytes.Buffer{}
	if repository() != catalog.FindRepo(path) {
		t.Fatal(repository())
	}
	if code := run([]string{"--version"}, strings.NewReader(""), out, errs); code != 0 || !strings.Contains(out.String(), "tplay") {
		t.Fatal(code)
	}
	if code := run([]string{"--help"}, strings.NewReader(""), out, errs); code != 0 {
		t.Fatal(code)
	}
	for _, args := range [][]string{{"--bad"}, {"extra"}} {
		if code := run(args, strings.NewReader(""), out, errs); code != 2 {
			t.Fatal(code)
		}
	}
	if code := run([]string{"list"}, strings.NewReader(""), out, errs); code != 0 {
		t.Fatal(code)
	}
}
