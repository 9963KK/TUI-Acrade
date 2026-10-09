package catalog

import (
	"encoding/json"
	"maps"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

var mac = Host{"macos", "arm64"}

func valid() map[string]any {
	return map[string]any{
		"manifest_version": 1, "id": "demo", "name": "演示", "version": "1.0.0", "description": "说明",
		"authors": []any{"作者"}, "launch": map[string]any{"argv": []any{"{python}", "main.py"}, "cwd": "."},
		"requirements": map[string]any{"os": []any{}, "arch": []any{}, "network": "none",
			"terminal": map[string]any{"columns": 40, "rows": 10}},
		"data":          map[string]any{"managed_directory": true, "save_mode": "none"},
		"documentation": map[string]any{"readme": "README.md"},
	}
}

func write(t *testing.T, root, folder string, changes map[string]any) string {
	t.Helper()
	data := valid()
	maps.Copy(data, changes)
	dir := filepath.Join(root, folder)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	os.WriteFile(filepath.Join(dir, "README.md"), []byte("说明"), 0o644)
	raw, _ := json.Marshal(data)
	path := filepath.Join(dir, Manifest)
	if err := os.WriteFile(path, raw, 0o644); err != nil {
		t.Fatal(err)
	}
	return path
}

func repo(t *testing.T) string {
	root := FindRepo(".")
	if root == "" {
		t.Fatal("repository not found")
	}
	return root
}

func TestBundledManifestsAreValid(t *testing.T) {
	root := repo(t)
	entries, problems := Load([]Dir{{filepath.Join(root, "games"), Builtin}, {filepath.Join(root, "templates"), Local}}, mac)
	if len(problems) != 0 || len(entries) != 2 {
		t.Fatalf("entries %v problems %v", entries, problems)
	}
	tank := entries[0]
	if tank.ID != "tank" || tank.Terminal.Columns != 80 || tank.SaveMode != "records" || len(tank.Presentation.Cover) != CoverHeight {
		t.Errorf("tank: %+v", tank)
	}
	argv, err := tank.Command("/usr/bin/python3")
	if err != nil || argv[0] != "/usr/bin/python3" {
		t.Errorf("command %v %v", argv, err)
	}
	if _, err := tank.Command(""); err == nil {
		t.Error("missing interpreter must be reported")
	}
	if entries[1].ID != "minimal-game" {
		t.Errorf("sample: %+v", entries[1])
	}
}

func TestRejectsMalformedManifests(t *testing.T) {
	root := t.TempDir()
	cases := map[string]map[string]any{
		"no-version": {"manifest_version": nil}, "float-version": {"manifest_version": 1.5},
		"bad-id": {"id": "Demo"}, "reserved": {"id": "con"}, "com": {"id": "com3"}, "unknown": {"extra": 1},
		"semver": {"version": "1.0"}, "authors": {"authors": []any{}},
		"argv":          {"launch": map[string]any{"argv": []any{}}},
		"cwd":           {"launch": map[string]any{"argv": []any{"{python}"}, "cwd": "../.."}},
		"absolute":      {"launch": map[string]any{"argv": []any{"./bin/game"}, "cwd": "/tmp"}},
		"escape":        {"launch": map[string]any{"argv": []any{"./../../evil"}}},
		"empty":         {"launch": map[string]any{"argv": []any{"./"}}},
		"launch-typo":   {"launch": map[string]any{"argv": []any{"{python}"}, "cwdd": "."}},
		"network":       {"requirements": map[string]any{"network": "sometimes"}},
		"color":         {"requirements": map[string]any{"terminal": map[string]any{"color": "millions"}}},
		"size":          {"requirements": map[string]any{"terminal": map[string]any{"columns": 0}}},
		"terminal-typo": {"requirements": map[string]any{"terminal": map[string]any{"colums": 80}}},
		"os":            {"requirements": map[string]any{"os": []any{"darwin"}}},
		"arch-type":     {"requirements": map[string]any{"arch": []any{"arm64", 5}}},
		"save":          {"data": map[string]any{"save_mode": "cloud"}},
		"managed":       {"data": map[string]any{"managed_directory": "yes"}},
		"docs":          {"documentation": map[string]any{"license": "LICENSE"}},
		"docs-typo":     {"documentation": map[string]any{"manual": "README.md"}},
	}
	for folder, change := range cases {
		if _, err := Parse(write(t, root, folder, change), Local, mac); err == nil {
			t.Errorf("%s: expected rejection", folder)
		}
	}
	nested := filepath.Join(root, "deep", Manifest)
	os.MkdirAll(filepath.Dir(nested), 0o755)
	// 括号成对闭合，确保拒绝来自深度上限而不是语法错误。
	os.WriteFile(nested, []byte(strings.Repeat("[", 100000)+strings.Repeat("]", 100000)), 0o644)
	if _, err := Parse(nested, Local, mac); err == nil {
		t.Error("deeply nested JSON must be rejected, not crash")
	}
}

func TestPlaceholdersCannotEscapeThePackage(t *testing.T) {
	root := t.TempDir()
	for folder, argv := range map[string][]any{
		"dir-in-entry": {"./{dir}/../victim/bin/tool"},
		"dir-as-entry": {"{dir}/../victim/bin/tool"},
		"python-entry": {"./bin/{python}"},
	} {
		for _, source := range []Source{Local, Git} {
			if _, err := Parse(write(t, root, folder+string(source), map[string]any{"launch": map[string]any{"argv": argv}}), source, mac); err == nil {
				t.Errorf("%s/%s: expected rejection", folder, source)
			}
		}
	}
	// 包内名为 {dir} 的符号链接同样无法利用：入口中出现花括号即拒绝。
	manifest := write(t, root, "link", map[string]any{"launch": map[string]any{"argv": []any{"./{dir}/../../../usr/bin/python3"}}})
	os.Symlink(filepath.Dir(manifest), filepath.Join(filepath.Dir(manifest), "{dir}"))
	if _, err := Parse(manifest, Git, mac); err == nil {
		t.Error("braces in entry must be rejected")
	}
	for folder, argv := range map[string][]any{
		"control": {"./bin/game", "--name=a\tb"}, "format": {"./bin/game", "x\u200dy"},
		"colon": {"./bin/game:stream"}, "device": {"./NUL"},
	} {
		if _, err := Parse(write(t, root, folder, map[string]any{"launch": map[string]any{"argv": argv}}), Git, mac); err == nil &&
			(folder != "device" || runtime.GOOS == "windows") {
			t.Errorf("%s: expected rejection", folder)
		}
	}
}

func TestSymlinksCannotMoveThePackageRoot(t *testing.T) {
	root := t.TempDir()
	outside := write(t, root, "outside", map[string]any{"launch": map[string]any{"argv": []any{"./bin/x"}}})
	programs := filepath.Join(root, "programs", "x")
	os.MkdirAll(programs, 0o755)
	os.Symlink(outside, filepath.Join(programs, Manifest))
	if _, err := Parse(filepath.Join(programs, Manifest), Git, mac); err == nil {
		t.Error("symlinked manifest in a clone must be rejected")
	}
	// 包内指向包外的符号链接不能作为入口或工作目录。
	pkg := filepath.Dir(write(t, root, "pkg", map[string]any{"launch": map[string]any{"argv": []any{"./bin/game"}}}))
	os.Symlink(t.TempDir(), filepath.Join(pkg, "out"))
	for _, launch := range []map[string]any{{"argv": []any{"./out/game"}}, {"argv": []any{"./bin/game"}, "cwd": "out"}} {
		manifest := filepath.Join(pkg, Manifest)
		data := valid()
		data["launch"] = launch
		raw, _ := json.Marshal(data)
		os.WriteFile(manifest, raw, 0o644)
		if _, err := Parse(manifest, Git, mac); err == nil {
			t.Errorf("%v: symlink escape must be rejected", launch)
		}
	}
}

func TestEverySourceIsSourceCode(t *testing.T) {
	root := t.TempDir()
	// 玩家是程序员：任何来源都可以用 {python} 或 PATH 中的命令启动，运行环境由安装检查把关。
	for _, source := range []Source{Builtin, Git, Local} {
		entry, err := Parse(write(t, root, string(source), nil), source, mac)
		if err != nil || entry.Source != source || entry.Python == nil {
			t.Fatalf("%s: %v %+v", source, err, entry.Python)
		}
	}
	packaged := write(t, root, "b", map[string]any{"launch": map[string]any{"argv": []any{"./bin/game", "--data={dir}/x"}}})
	entry, err := Parse(packaged, Git, mac)
	if err != nil || entry.Python != nil {
		t.Fatal(err, entry.Python)
	}
	argv, _ := entry.Command("")
	folder := filepath.Dir(packaged)
	if argv[0] != filepath.Join(folder, "bin", "game") || argv[1] != "--data="+folder+"/x" {
		t.Errorf("argv %v", argv)
	}
}

func TestPythonRequirements(t *testing.T) {
	root := t.TempDir()
	os.MkdirAll(filepath.Join(root, "deps"), 0o755)
	os.WriteFile(filepath.Join(root, "deps", "requirements.txt"), []byte("rich\n"), 0o644)
	python := map[string]any{"version": ">=3.10,<4", "modules": []any{"curses", "xml.dom"}, "packages": "requirements.txt"}
	manifest := write(t, root, "deps", map[string]any{"requirements": map[string]any{"python": python}})
	entry, err := Parse(manifest, Local, mac)
	if err != nil {
		t.Fatal(err)
	}
	p := entry.Python
	if p.Version.String() != ">=3.10,<4" || len(p.Modules) != 2 || p.Packages != filepath.Join(filepath.Dir(manifest), "requirements.txt") {
		t.Errorf("%+v", p)
	}
	for folder, bad := range map[string]map[string]any{
		"op": {"version": "3.10"}, "num": {"version": ">=three"}, "module": {"modules": []any{"os; rm"}},
		"missing": {"packages": "none.txt"}, "escape": {"packages": "../x.txt"}, "typo": {"verison": ">=3"},
	} {
		if _, err := Parse(write(t, root, folder, map[string]any{"requirements": map[string]any{"python": bad}}), Local, mac); err == nil {
			t.Errorf("%s: expected rejection", folder)
		}
	}
}

func TestConstraints(t *testing.T) {
	c, _ := ParseConstraint(">=3.10, <4")
	for text, want := range map[string]bool{"3.10.0": true, "3.14.7": true, "3.9.18": false, "4.0.0": false} {
		v, _ := ParseVersion(text)
		if c.Allows(v) != want {
			t.Errorf("%s: %v", text, !want)
		}
	}
	if any := (Constraint{}); !any.Allows(Version{2, 7, 0}) || any.String() != "任意版本" {
		t.Error("empty constraint allows everything")
	}
}

func TestNewerProtocolAndForeignPlatformAreListedButBlocked(t *testing.T) {
	root := t.TempDir()
	future, err := Parse(write(t, root, "a", map[string]any{"manifest_version": 2, "surprise": true}), Local, mac)
	if err != nil || !strings.Contains(future.Issue, "需要更新平台") {
		t.Errorf("future: %v %v", future.Issue, err)
	}
	foreign := write(t, root, "b", map[string]any{"requirements": map[string]any{"os": []any{"windows"}, "arch": []any{"x86_64"}}})
	if e, _ := Parse(foreign, Local, mac); !strings.Contains(e.Issue, "本机不支持") {
		t.Errorf("foreign: %q", e.Issue)
	}
	if e, _ := Parse(foreign, Local, Host{"windows", "x86_64"}); e.Issue != "" {
		t.Errorf("native: %q", e.Issue)
	}
}

func TestPresentationIsOptionalAndSanitized(t *testing.T) {
	root := t.TempDir()
	broken, _ := Parse(write(t, root, "a", map[string]any{"metadata": map[string]any{
		"presentation": map[string]any{"cover": map[string]any{"cells": map[string]any{"X": map[string]any{"text": "宽"}}}}, "anything": 1}}), Local, mac)
	if broken.Presentation.Cells != nil || broken.Presentation.NameEn != "" {
		t.Errorf("malformed presentation must be ignored: %+v", broken.Presentation)
	}
	shown, _ := Parse(write(t, root, "b", map[string]any{"name": "危\x1b[31m险", "metadata": map[string]any{
		"presentation": map[string]any{"tags": []any{"单人"}}}}), Local, mac)
	if shown.Name != "危[31m险" || len(shown.Presentation.Tags) != 1 {
		t.Errorf("sanitize: %q %v", shown.Name, shown.Presentation.Tags)
	}
}

func TestLoadSkipsInvalidAndDuplicates(t *testing.T) {
	first, second := t.TempDir(), t.TempDir()
	write(t, first, "a", map[string]any{"name": "甲"})
	write(t, first, "b", map[string]any{"id": "b", "version": "x"})
	write(t, second, "a", map[string]any{"name": "重复", "launch": map[string]any{"argv": []any{"./game"}}})
	write(t, second, "c", map[string]any{"id": "c", "launch": map[string]any{"argv": []any{"./game"}}})
	entries, problems := Load([]Dir{{first, Local}, {second, Git}, {filepath.Join(first, "none"), Local}}, mac)
	if len(entries) != 2 || entries[0].Name != "甲" || entries[1].ID != "c" {
		t.Errorf("entries %+v", entries)
	}
	if len(problems) != 1 || !strings.Contains(problems[0].Reason, "version") {
		t.Errorf("problems %+v", problems)
	}
}

func TestBuiltinGamesAndRepo(t *testing.T) {
	games, problems := BuiltinGames(repo(t), mac)
	if len(games) != 1 || games[0].Source != Builtin || len(problems) != 0 {
		t.Errorf("%+v %v", games, problems)
	}
	if games, _ := BuiltinGames("", mac); games != nil {
		t.Error("no repository, no builtin games")
	}
	if FindRepo(t.TempDir()) != "" {
		t.Error("no repository outside the checkout")
	}
}
