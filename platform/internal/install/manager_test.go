package install

import (
	"bytes"
	"encoding/json"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"tuiarcade/platform/internal/catalog"
	"tuiarcade/platform/internal/paths"
	"tuiarcade/platform/internal/registry"
)

func manager(t *testing.T) *Manager {
	t.Helper()
	fast(t)
	root := t.TempDir()
	m := New(paths.Roots{Programs: filepath.Join(root, "programs"), Data: filepath.Join(root, "data"), Logs: filepath.Join(root, "logs"), Cache: filepath.Join(root, "cache")}, "")
	m.Out, m.In = &bytes.Buffer{}, strings.NewReader("")
	return m
}

func fixture(t *testing.T, root, id, body string, python map[string]any) string {
	t.Helper()
	os.MkdirAll(root, 0o755)
	manifest := map[string]any{"manifest_version": 1, "id": id, "name": "测试游戏", "version": "1.0.0", "authors": []string{"tester"}, "launch": map[string]any{"argv": []string{"{python}", "main.py"}}, "data": map[string]any{"managed_directory": true, "save_mode": "records"}}
	if python != nil {
		manifest["requirements"] = map[string]any{"python": python}
	}
	raw, _ := json.Marshal(manifest)
	if err := os.WriteFile(filepath.Join(root, "game.json"), raw, 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "main.py"), []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
	return root
}

func acquire(t *testing.T, m *Manager, root string) *Candidate {
	t.Helper()
	c, err := m.Acquire(root, catalog.Local)
	if err != nil {
		t.Fatal(err)
	}
	return c
}

func TestLocalInstallIsolatedDataAndUninstallPreservesSourceAndSave(t *testing.T) {
	m := manager(t)
	root := fixture(t, t.TempDir(), "demo", "import os,pathlib; print('GAME'); p=pathlib.Path(os.environ['TUI_ARCADE_DATA_DIR']); (p/'save').write_text('trial')", nil)
	save := m.Roots.GameData("demo")
	os.MkdirAll(save, 0o755)
	os.WriteFile(filepath.Join(save, "save"), []byte("player"), 0o644)
	c := acquire(t, m, root)
	if lines, err := m.Plan(c); err != nil || len(lines) < 5 {
		t.Fatalf("plan %v %v", lines, err)
	}
	record, err := m.Install(c)
	if err != nil {
		t.Fatal(err)
	}
	if record.Status != registry.Installed || record.Python == "" || record.Fingerprint == "" {
		t.Fatal(record)
	}
	if raw, _ := os.ReadFile(filepath.Join(save, "save")); string(raw) != "player" {
		t.Fatal("smoke changed player save")
	}
	entries, err := m.Library()
	if err != nil || len(entries) != 1 || entries[0].Issue != "" {
		t.Fatalf("library %v %v", entries, err)
	}
	game, problem := m.Launch(entries[0])
	if problem != "" || game.Argv[0] != record.Python {
		t.Fatal(problem)
	}
	if _, err := m.CheckRegistered("demo", true); err == nil {
		t.Fatal("check raced active game")
	}
	if err := m.Uninstall("demo"); err == nil {
		t.Fatal("running game must hold its install lock")
	}
	game.Release()
	if err := m.Uninstall("demo"); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(root, "main.py")); err != nil {
		t.Fatal("local source removed")
	}
	if raw, _ := os.ReadFile(filepath.Join(save, "save")); string(raw) != "player" {
		t.Fatal("save removed")
	}
	entries, _ = m.Library()
	if len(entries) != 0 {
		t.Fatal("uninstalled game still in gallery")
	}
}

func TestFailedInstallNeverRegistersAndWritesReport(t *testing.T) {
	for _, body := range []string{"print('crash'); raise RuntimeError('boom')", "import time;time.sleep(30)"} {
		m := manager(t)
		c := acquire(t, m, fixture(t, t.TempDir(), "broken", body, nil))
		if _, err := m.Install(c); err == nil {
			t.Fatal("failed game registered")
		}
		f, _ := registry.Load(m.RecordPath())
		if len(f.Games) != 0 {
			t.Fatal(f)
		}
		raw, err := os.ReadFile(filepath.Join(m.Roots.GameLogs("broken"), "install.log"))
		if err != nil || !strings.Contains(string(raw), "[失败] 试运行") {
			t.Fatalf("report %s %v", raw, err)
		}
	}
}

func TestMissingRuntimeModuleAndUnsupportedHost(t *testing.T) {
	m := manager(t)
	root := fixture(t, t.TempDir(), "modules", "print('GAME')", map[string]any{"version": ">=3.10", "modules": []string{"no_such_tplay_module_xyz"}})
	c := acquire(t, m, root)
	if problem := Problem(m.Check(c.Entry, "", true)); !strings.Contains(problem, "模块") {
		t.Fatal(problem)
	}
	if _, err := m.Install(c); err == nil {
		t.Fatal("missing module installed")
	}
	root = fixture(t, t.TempDir(), "version", "print('GAME')", map[string]any{"version": ">=99"})
	c = acquire(t, m, root)
	if _, err := m.Plan(c); err == nil {
		t.Fatal("unsatisfied version has install plan")
	}
	c.Entry.Issue = "系统不支持"
	if _, err := m.Plan(c); err == nil {
		t.Fatal("unsupported install allowed")
	}
	if _, err := m.Acquire(root, catalog.Source("invalid")); err == nil {
		t.Fatal("invalid source")
	}
}

func TestIDCollisionRepairAndCodeChanges(t *testing.T) {
	m := manager(t)
	root := fixture(t, t.TempDir(), "demo", "print('GAME')", nil)
	if _, err := m.Install(acquire(t, m, root)); err != nil {
		t.Fatal(err)
	}
	other := fixture(t, t.TempDir(), "demo", "print('OTHER')", nil)
	if _, err := m.Plan(acquire(t, m, other)); err == nil {
		t.Fatal("duplicate ID allowed")
	}
	os.WriteFile(filepath.Join(root, "main.py"), []byte("print('UPDATED')"), 0o644)
	entries, err := m.Library()
	if err != nil || entries[0].Issue != "" {
		t.Fatal(err)
	}
	f, _ := registry.Load(m.RecordPath())
	if f.Find("demo").Fingerprint == "" {
		t.Fatal(f)
	}
	os.Remove(filepath.Join(root, "game.json"))
	entries, err = m.Library()
	if err != nil || entries[0].Issue == "" {
		t.Fatal("broken install hidden")
	}
	f, _ = registry.Load(m.RecordPath())
	if f.Find("demo").Status != registry.NeedsRepair {
		t.Fatal(f)
	}
	if _, problem := m.Launch(entries[0]); problem == "" {
		t.Fatal("broken install launched")
	}
	fixture(t, root, "demo", "print('REPAIRED')", nil)
	c, err := m.Existing("demo")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := m.Install(c); err != nil {
		t.Fatal(err)
	}
	entries, _ = m.Library()
	if entries[0].Issue != "" {
		t.Fatal(entries)
	}
}

func TestGitInstallMoveCancelAndUninstall(t *testing.T) {
	posix(t)
	m := manager(t)
	root := fixture(t, t.TempDir(), "git-demo", "print('GIT GAME')", nil)
	for _, args := range [][]string{{"init", root}, {"-C", root, "add", "game.json", "main.py"}, {"-C", root, "-c", "user.name=test", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture"}} {
		if out, err := exec.Command("git", args...).CombinedOutput(); err != nil {
			t.Fatalf("git %s %v", out, err)
		}
	}
	url := "file://" + root
	c, err := m.Acquire(url, catalog.Git)
	if err != nil {
		t.Fatal(err)
	}
	if c.Commit == "" || c.Stage == "" {
		t.Fatal(c)
	}
	if err := m.CleanStaging(); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(c.Entry.Root); err != nil {
		t.Fatal("another process cleaned active source")
	}
	c.Close(false)
	if _, err := os.Stat(c.Stage); !os.IsNotExist(err) {
		t.Fatal("cancel did not delete clone")
	}
	c, err = m.Acquire(url, catalog.Git)
	if err != nil {
		t.Fatal(err)
	}
	r, err := m.Install(c)
	if err != nil {
		t.Fatal(err)
	}
	if r.Path != filepath.Join(m.Roots.Programs, "games", "git-demo") || r.URL != url {
		t.Fatal(r)
	}
	if _, err := os.Stat(filepath.Join(r.Path, "main.py")); err != nil {
		t.Fatal(err)
	}
	if err := m.Uninstall(r.ID); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(r.Path); !os.IsNotExist(err) {
		t.Fatal("git clone left behind")
	}
	if _, err := os.Stat(root); err != nil {
		t.Fatal("upstream source removed")
	}
	if _, err := m.Acquire("--upload-pack=oops", catalog.Git); err == nil {
		t.Fatal("git option accepted as URL")
	}
}

func TestDependencyEnvironmentRollbackAndSuccessfulRepair(t *testing.T) {
	posix(t)
	m := manager(t)
	root := fixture(t, t.TempDir(), "deps", "print('GAME')", map[string]any{"version": ">=3.10", "modules": []string{"json"}, "packages": "requirements.txt"})
	os.WriteFile(filepath.Join(root, "requirements.txt"), nil, 0o644)
	python, _ := exec.LookPath("python3")
	if python == "" {
		t.Skip("requires Python")
	}
	failPip := false
	commands := []string{}
	m.Execute = func(cmd *exec.Cmd) error {
		commands = append(commands, strings.Join(cmd.Args, " "))
		if cmd.Args[2] == "venv" {
			path := envPython(cmd.Args[3])
			os.MkdirAll(filepath.Dir(path), 0o755)
			return os.Symlink(python, path)
		}
		if failPip {
			return errors.New("dependency failed")
		}
		return nil
	}
	r, err := m.Install(acquire(t, m, root))
	if err != nil {
		t.Fatal(err)
	}
	if r.Env == "" || len(commands) != 2 {
		t.Fatal(r, commands)
	}
	failPip = true
	if _, err := m.Install(acquire(t, m, root)); err == nil {
		t.Fatal("pip failure not reported")
	}
	f, _ := registry.Load(m.RecordPath())
	if f.Find("deps").Env != r.Env {
		t.Fatal("failed repair replaced record")
	}
	if f.Find("deps").Status != registry.NeedsRepair || !strings.Contains(f.Find("deps").Problem, "dependency failed") {
		t.Fatal("failed repair remained playable")
	}
	envs, _ := os.ReadDir(filepath.Dir(r.Env))
	if len(envs) != 1 {
		t.Fatal("failed environment not removed")
	}
	failPip = false
	newRecord, err := m.Install(acquire(t, m, root))
	if err != nil {
		t.Fatal(err)
	}
	if newRecord.Env == r.Env {
		t.Fatal("environment modified in place")
	}
	if _, err := os.Stat(r.Env); !os.IsNotExist(err) {
		t.Fatal("old environment retained")
	}
}

func TestStagingCleanupRetainsExplicitlyKeptAndActiveEnvironments(t *testing.T) {
	m := manager(t)
	stage := filepath.Join(m.Roots.Programs, ".staging", "clone-dead")
	os.MkdirAll(stage, 0o755)
	kept := filepath.Join(m.Roots.Programs, ".staging", "clone-kept")
	os.MkdirAll(kept, 0o755)
	(&Candidate{Stage: kept}).Close(true)
	parent := filepath.Join(m.Roots.Programs, "envs", "demo")
	dead := filepath.Join(parent, "runtime-dead")
	active := filepath.Join(parent, "runtime-active")
	os.MkdirAll(dead, 0o755)
	os.MkdirAll(active, 0o755)
	release, err := registry.Lock(filepath.Join(active, ".lease"))
	if err != nil {
		t.Fatal(err)
	}
	defer release()
	if err := m.CleanStaging(); err != nil {
		t.Fatal(err)
	}
	for _, path := range []string{stage, dead} {
		if _, err := os.Stat(path); !os.IsNotExist(err) {
			t.Fatal("orphan remains", path)
		}
	}
	for _, path := range []string{kept, active} {
		if _, err := os.Stat(path); err != nil {
			t.Fatal("active/kept removed", path)
		}
	}
}

func TestUninstallRejectsUnownedPathsAndUnreadableRecords(t *testing.T) {
	m := manager(t)
	outside := t.TempDir()
	registry.Update(m.RecordPath(), func(f *registry.File) error {
		f.Put(registry.Record{ID: "demo", Source: "git", Path: outside})
		return nil
	})
	if err := m.Uninstall("demo"); err == nil {
		t.Fatal("external directory removed")
	}
	if err := m.Uninstall("../outside"); err == nil {
		t.Fatal("invalid ID removed")
	}
	if err := m.Uninstall("missing"); err == nil {
		t.Fatal("missing uninstall succeeded")
	}
	os.WriteFile(m.RecordPath(), []byte("broken"), 0o644)
	os.WriteFile(m.RecordPath()+".bak", []byte("broken"), 0o644)
	if _, err := m.Library(); err == nil {
		t.Fatal("unreadable record ignored")
	}
	if err := m.CleanStaging(); err == nil {
		t.Fatal("cleanup ignored unreadable registry")
	}
}

func TestBuiltinChoicesAndInvalidEntry(t *testing.T) {
	m := manager(t)
	m.Repo = t.TempDir()
	fixture(t, filepath.Join(m.Repo, "games", "demo"), "demo", "print('GAME')", nil)
	c, err := m.Builtin("demo")
	if err != nil || c.Entry.Source != catalog.Builtin {
		t.Fatal(c, err)
	}
	choices, err := m.Choices()
	if err != nil || choices[0].Status != "可安装" {
		t.Fatal(choices, err)
	}
	if _, err := m.Builtin("missing"); err == nil {
		t.Fatal("missing builtin")
	}
	if _, err := m.Existing("missing"); err == nil {
		t.Fatal("missing installation")
	}
	if _, problem := m.Launch(c.Entry); problem == "" {
		t.Fatal("uninstalled launch")
	}
	if _, err := m.Install(c); err != nil {
		t.Fatal(err)
	}
	choices, _ = m.Choices()
	if choices[0].Status != "已安装" {
		t.Fatal(choices)
	}
	if err := m.Uninstall("demo"); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(c.Entry.Root); err != nil {
		t.Fatal("builtin removed")
	}
	if problem := Problem(m.Check(catalog.Entry{Root: t.TempDir()}, "", false)); problem == "" {
		t.Fatal("missing manifest")
	}
}

func TestCheckMissingExecutableAndDataSymlink(t *testing.T) {
	posix(t)
	m := manager(t)
	root := fixture(t, t.TempDir(), "demo", "print('GAME')", nil)
	c := acquire(t, m, root)
	entry := c.Entry
	entry.Argv = []string{"./missing"}
	raw, _ := os.ReadFile(filepath.Join(root, "game.json"))
	var data map[string]any
	json.Unmarshal(raw, &data)
	data["launch"] = map[string]any{"argv": entry.Argv}
	raw, _ = json.Marshal(data)
	os.WriteFile(filepath.Join(root, "game.json"), raw, 0o644)
	if problem := Problem(m.Check(entry, "", false)); !strings.Contains(problem, "入口") {
		t.Fatal(problem)
	}
	fixture(t, root, "demo", "print('GAME')", nil)
	save := m.Roots.GameData("demo")
	os.MkdirAll(save, 0o755)
	os.Symlink(t.TempDir(), filepath.Join(save, "linked"))
	if problem := Problem(m.Check(c.Entry, "", true)); !strings.Contains(problem, "存档副本") {
		t.Fatal(problem)
	}
}
