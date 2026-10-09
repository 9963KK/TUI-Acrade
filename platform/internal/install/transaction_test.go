package install

import (
	"os"
	"path/filepath"
	"testing"

	"tuiarcade/platform/internal/registry"
)

func TestRecoverInterruptedDirectoryTransactions(t *testing.T) {
	for _, kind := range []string{"install", "uninstall"} {
		for _, registered := range []bool{false, true} {
			t.Run(kind+map[bool]string{true: "-committed", false: "-unregistered"}[registered], func(t *testing.T) {
				m := manager(t)
				game := filepath.Join(m.Roots.Programs, "games", "demo")
				envs := filepath.Join(m.Roots.Programs, "envs", "demo")
				stage, release, err := m.leasedDirectory(filepath.Join(m.Roots.Programs, ".staging"), "interrupted-")
				if err != nil {
					t.Fatal(err)
				}
				if registered {
					_, err := registry.Update(m.RecordPath(), func(f *registry.File) error {
						f.Put(registry.Record{ID: "demo", Path: game, Env: filepath.Join(envs, "runtime-kept"), Status: registry.Installed})
						return nil
					})
					if err != nil {
						t.Fatal(err)
					}
				}
				if err := writeTransaction(stage, "demo", kind); err != nil {
					t.Fatal(err)
				}
				if kind == "install" {
					os.MkdirAll(game, 0o755)
				} else {
					os.MkdirAll(filepath.Join(stage, "game"), 0o755)
					os.MkdirAll(filepath.Join(stage, "envs", "runtime-kept"), 0o755)
				}
				release()
				if err := m.CleanStaging(); err != nil {
					t.Fatal(err)
				}
				_, gameErr := os.Stat(game)
				if (gameErr == nil) != registered {
					t.Fatalf("game present=%v registered=%v", gameErr == nil, registered)
				}
				if kind == "uninstall" {
					_, envErr := os.Stat(envs)
					if (envErr == nil) != registered {
						t.Fatal("environment recovery", envErr)
					}
				}
				if _, err := os.Stat(stage); !os.IsNotExist(err) {
					t.Fatal("transaction was not cleaned", err)
				}
			})
		}
	}
}

func TestTransactionRecoveryRejectsInvalidIDAndDoesNotOverwrite(t *testing.T) {
	m := manager(t)
	stage, release, err := m.leasedDirectory(filepath.Join(m.Roots.Programs, ".staging"), "interrupted-")
	if err != nil {
		t.Fatal(err)
	}
	release()
	writeTransaction(stage, "../outside", "install")
	if err := m.CleanStaging(); err == nil {
		t.Fatal("invalid transaction accepted")
	}
	writeTransaction(stage, "demo", "install")
	os.MkdirAll(filepath.Join(stage, "source"), 0o755)
	os.MkdirAll(filepath.Join(m.Roots.Programs, "games", "demo"), 0o755)
	if err := m.CleanStaging(); err == nil {
		t.Fatal("recovery overwrote source")
	}
	if _, err := os.Stat(stage); err != nil {
		t.Fatal("failed recovery removed journal")
	}
}
