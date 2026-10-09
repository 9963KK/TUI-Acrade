package install

import (
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"

	"tuiarcade/platform/internal/catalog"
)

func script(t *testing.T, dir, name, body string) string {
	t.Helper()
	path := filepath.Join(dir, name)
	if err := os.WriteFile(path, []byte("#!/bin/sh\n"+body+"\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	return path
}

func posix(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("POSIX shell")
	}
}

func fast(t *testing.T) {
	old := [3]time.Duration{firstOutput, settle, exitWait}
	firstOutput, settle, exitWait = 800*time.Millisecond, 200*time.Millisecond, 500*time.Millisecond
	t.Cleanup(func() { firstOutput, settle, exitWait = old[0], old[1], old[2] })
}

func TestSmokeVerdicts(t *testing.T) {
	posix(t)
	fast(t)
	dir := t.TempDir()
	cases := []struct {
		name, body string
		ok         bool
		detail     string
	}{
		{"good", "printf 'TANK BATTLE'; sleep 30", true, "Ctrl-C 可以退出"},
		{"done", "printf 'bye'", true, "自行正常结束"},
		{"crash", "printf 'Traceback'; exit 3", false, "启动后崩溃（退出码 3）"},
		{"silent-exit", "exit 1", false, "还没有画面就结束了（退出码 1）"},
		{"no-output", "sleep 30", false, "秒内没有画面输出"},
		{"term-only", "trap '' INT; printf 'hi'; sleep 30", true, "SIGTERM 可以退出"},
		{"stuck", "trap '' INT TERM; printf 'hi'; while :; do sleep 1; done", false, "无法用 Ctrl-C 或 SIGTERM 退出"},
	}
	for _, c := range cases {
		result := Smoke([]string{script(t, dir, c.name, c.body)}, os.Environ(), dir, 80, 24)
		if result.OK != c.ok || !strings.Contains(result.Detail, c.detail) {
			t.Errorf("%s: %+v", c.name, result)
		}
	}
	if r := Smoke([]string{filepath.Join(dir, "missing")}, nil, dir, 80, 24); r.OK || !strings.Contains(r.Detail, "无法启动") {
		t.Errorf("missing program: %+v", r)
	}
	if r := Smoke([]string{script(t, dir, "tail", "printf '\\033[31mError: boom\\033[0m'; exit 2")}, nil, dir, 80, 24); !strings.Contains(r.Output, "Error: boom") {
		t.Errorf("output tail without escapes: %q", r.Output)
	}
}

func TestTranscriptAnswersTerminalQueries(t *testing.T) {
	var answers []string
	out := &transcript{first: make(chan struct{}), answer: func(b []byte) { answers = append(answers, string(b)) }}
	out.Write([]byte("\x1b]11;?\x1b\\\x1b[6n"))
	if len(answers) != 2 {
		t.Errorf("answers %q", answers)
	}
	select {
	case <-out.first:
		t.Error("queries alone are not a picture")
	default:
	}
	out.Write([]byte("\x1b[2J hello"))
	select {
	case <-out.first:
	default:
		t.Error("visible text counts as a picture")
	}
}

func TestFindPython(t *testing.T) {
	posix(t)
	real, _ := exec.LookPath("python3")
	dir := t.TempDir()
	script(t, dir, "python3", "echo 3.9.18")
	script(t, dir, "python3.12", "echo 3.12.2")
	t.Setenv("PATH", dir)
	want, _ := catalog.ParseConstraint(">=3.10")
	none := func(string) string { return "" }
	if found, problem := FindPython(want, none); problem != "" || found.Path != filepath.Join(dir, "python3.12") || found.Version.String() != "3.12.2" {
		t.Errorf("%+v %q", found, problem)
	}
	strict, _ := catalog.ParseConstraint(">=3.13")
	if _, problem := FindPython(strict, none); !strings.Contains(problem, "3.9.18") || !strings.Contains(problem, "3.12.2") {
		t.Errorf("problem lists what was found: %q", problem)
	}
	configured := script(t, dir, "custom", "echo 3.13.0")
	if found, _ := FindPython(strict, func(k string) string { return map[string]string{"TUI_ARCADE_PYTHON": configured}[k] }); found.Path != configured {
		t.Errorf("TUI_ARCADE_PYTHON wins: %+v", found)
	}
	t.Setenv("PATH", t.TempDir())
	if _, problem := FindPython(want, none); !strings.Contains(problem, "未找到") {
		t.Errorf("no python: %q", problem)
	}
	if real == "" {
		t.Skip("python3 not available for module checks")
	}
	missing, err := MissingModules(real, []string{"json", "no_such_module_xyz"})
	if err != nil || len(missing) != 1 || missing[0] != "no_such_module_xyz" {
		t.Errorf("%v %v", missing, err)
	}
}

func TestFingerprintIgnoresHistoryAndCaches(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "main.py"), []byte("print(1)"), 0o644)
	first, _ := Fingerprint(dir)
	for _, noise := range []string{".git/HEAD", "__pycache__/main.cpython-311.pyc", "x.pyc"} {
		os.MkdirAll(filepath.Dir(filepath.Join(dir, noise)), 0o755)
		os.WriteFile(filepath.Join(dir, noise), []byte("noise"), 0o644)
	}
	if second, _ := Fingerprint(dir); second != first {
		t.Error("history and caches do not change the fingerprint")
	}
	os.WriteFile(filepath.Join(dir, "main.py"), []byte("print(2)"), 0o644)
	if third, _ := Fingerprint(dir); third == first {
		t.Error("an edit changes the fingerprint")
	}
}
