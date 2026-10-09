package registry

import (
	"errors"
	"os"
	"path/filepath"
	"sync"
	"testing"
)

func TestRoundTripAndBackup(t *testing.T) {
	path := filepath.Join(t.TempDir(), "sub", "installed.json")
	f, err := Load(path)
	if err != nil || len(f.Games) != 0 {
		t.Fatal(err)
	}
	f.Put(Record{ID: "tank", Status: Installed})
	if err := Save(path, f); err != nil {
		t.Fatal(err)
	}
	f.Put(Record{ID: "snake", Status: Installed})
	f.Put(Record{ID: "tank", Status: NeedsRepair})
	Save(path, f)
	got, _ := Load(path)
	if len(got.Games) != 2 || got.Find("tank").Status != NeedsRepair || got.Games[0].ID != "tank" {
		t.Errorf("%+v", got)
	}
	backup, _ := read(path + ".bak")
	if len(backup.Games) != 1 {
		t.Errorf("backup keeps the previous record: %+v", backup)
	}
	got.Remove("tank")
	if got.Find("tank") != nil || len(got.Games) != 1 {
		t.Error("remove")
	}
}

func TestDamagedRecordFallsBackAndIsNeverOverwrittenBlindly(t *testing.T) {
	path := filepath.Join(t.TempDir(), "installed.json")
	f := File{}
	f.Put(Record{ID: "tank"})
	Save(path, f)
	f.Put(Record{ID: "snake"})
	Save(path, f)
	os.WriteFile(path, []byte("{broken"), 0o644)
	got, err := Load(path)
	if err != nil || got.Find("tank") == nil {
		t.Fatalf("fallback to .bak: %v %+v", err, got)
	}
	os.WriteFile(path+".bak", []byte("[]"), 0o644)
	if _, err := Load(path); !errors.Is(err, ErrUnreadable) {
		t.Fatalf("both damaged: %v", err)
	}
	if _, err := Update(path, func(*File) error { return nil }); !errors.Is(err, ErrUnreadable) {
		t.Error("an unreadable record must not be replaced")
	}
	if raw, _ := os.ReadFile(path); string(raw) != "{broken" {
		t.Error("damaged file left untouched")
	}
	// 主文件缺失（两次改名之间中断）时读取 .bak。
	os.WriteFile(path+".bak", []byte(`{"version":1,"games":[{"id":"x"}]}`), 0o644)
	os.Remove(path)
	if got, err := Load(path); err != nil || got.Find("x") == nil {
		t.Errorf("missing main file: %v", err)
	}
}

func TestConcurrentUpdatesDoNotLoseWrites(t *testing.T) {
	path := filepath.Join(t.TempDir(), "installed.json")
	var wg sync.WaitGroup
	for i := range 20 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			Update(path, func(f *File) error {
				f.Put(Record{ID: string(rune('a' + i))})
				return nil
			})
		}()
	}
	wg.Wait()
	if got, _ := Load(path); len(got.Games) != 20 {
		t.Errorf("lost updates: %d", len(got.Games))
	}
}

func TestLeaseDoesNotWaitAndKernelReleasesIt(t *testing.T) {
	path := filepath.Join(t.TempDir(), ".lease")
	release, err := TryLock(path)
	if err != nil {
		t.Fatal(err)
	}
	if other, err := TryLock(path); err == nil {
		other()
		t.Fatal("lease acquired twice")
	}
	release()
	other, err := TryLock(path)
	if err != nil {
		t.Fatal(err)
	}
	other()
}

func TestFailedSaveAndCancelledMutationPreserveRecord(t *testing.T) {
	path := filepath.Join(t.TempDir(), "installed.json")
	if _, err := Update(path, func(f *File) error { f.Put(Record{ID: "tank"}); return nil }); err != nil {
		t.Fatal(err)
	}
	want := errors.New("cancelled")
	if _, err := Update(path, func(f *File) error { f.Remove("tank"); return want }); !errors.Is(err, want) {
		t.Fatal(err)
	}
	os.Mkdir(path+".bak", 0o755)
	if err := Save(path, File{}); err == nil {
		t.Fatal("failed backup rename accepted")
	}
	f, err := Load(path)
	if err != nil || f.Find("tank") == nil {
		t.Fatal("failed transaction lost original record", err)
	}
	parent := filepath.Join(t.TempDir(), "file")
	os.WriteFile(parent, []byte("blocking file"), 0o644)
	if _, err := Lock(filepath.Join(parent, "lock")); err == nil {
		t.Fatal("invalid lock parent accepted")
	}
	if err := Save(filepath.Join(parent, "installed.json"), File{}); err == nil {
		t.Fatal("invalid record parent accepted")
	}
}
