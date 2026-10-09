package install

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"tuiarcade/platform/internal/registry"
)

func TestRegisteredCheckRetainsFailureUntilFullRunAndWritesLog(t *testing.T) {
	m := manager(t)
	root := fixture(t, t.TempDir(), "demo", "print('GAME')", nil)
	if _, err := m.Install(acquire(t, m, root)); err != nil {
		t.Fatal(err)
	}
	manifest := filepath.Join(root, "game.json")
	raw, _ := os.ReadFile(manifest)
	os.WriteFile(manifest, []byte("broken"), 0o644)
	checks, err := m.CheckRegistered("demo", false)
	if err != nil || Problem(checks) == "" {
		t.Fatal(checks, err)
	}
	f, _ := registry.Load(m.RecordPath())
	if f.Find("demo").Status != registry.NeedsRepair {
		t.Fatal("failed check enabled game")
	}
	os.WriteFile(manifest, raw, 0o644)
	checks, err = m.CheckRegistered("demo", false)
	f, _ = registry.Load(m.RecordPath())
	if err != nil || Problem(checks) != "" || f.Find("demo").Status != registry.NeedsRepair {
		t.Fatal("static check enabled untested repair", err)
	}
	checks, err = m.CheckRegistered("demo", true)
	f, _ = registry.Load(m.RecordPath())
	if err != nil || Problem(checks) != "" || f.Find("demo").Status != registry.Installed {
		t.Fatal("full check did not repair", err)
	}
	log, err := os.ReadFile(f.Find("demo").LogFile)
	if err != nil || !strings.Contains(string(log), "[失败] 清单") || !strings.Contains(string(log), "[通过] 试运行") {
		t.Fatal("incomplete log", err)
	}
	fixture(t, root, "changed", "print('GAME')", nil)
	checks, err = m.CheckRegistered("demo", true)
	if err != nil || !strings.Contains(Problem(checks), "ID 已改变") {
		t.Fatal(checks, err)
	}
	if _, err := m.CheckRegistered("missing", false); err == nil {
		t.Fatal("missing installation accepted")
	}
	if _, err := m.CheckRegistered("../outside", false); err == nil {
		t.Fatal("invalid ID accepted")
	}
}

func TestGitDetectionAndAcquireErrorsDoNotLeaveStaging(t *testing.T) {
	m := manager(t)
	for _, input := range []string{"https://example.com/game.git", "ssh://example.com/game", "git@example.com:game.git", "file:///game"} {
		if !IsGit(input) {
			t.Fatal(input)
		}
	}
	if IsGit("/local/game") {
		t.Fatal("local treated as remote")
	}
	if _, err := m.Acquire("unsupported", "unknown"); err == nil {
		t.Fatal("unknown source accepted")
	}
	root := fixture(t, t.TempDir(), "demo", "print('GAME')", nil)
	c, err := m.Acquire(filepath.Join(root, "game.json"), "local")
	if err != nil || c.Entry.Root != root {
		t.Fatal(c, err)
	}
}
