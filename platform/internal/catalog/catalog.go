// Package catalog reads and validates game manifests (docs/game-integration.md, protocol 1).
// The platform only lists and launches games; it never executes anything while reading them.
package catalog

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"slices"
	"strings"
	"unicode"

	"tuiarcade/platform/internal/screen"
)

const (
	Manifest    = "game.json"
	CoverWidth  = 11
	CoverHeight = 4
	// Protocol is the newest manifest protocol this platform understands.
	Protocol = 1
)

// Source says where a game was found.
type Source string

const (
	// Dev 来源为仓库 games/ 或 TUI_ARCADE_DEV_GAMES，可用 {python} 从源码运行。
	Dev Source = "dev"
	// Installed 来源为程序目录，必须是自带运行环境的预构建包。
	Installed Source = "installed"
)

var (
	idPattern = regexp.MustCompile(`^[a-z][a-z0-9-]{0,63}$`)
	semver    = regexp.MustCompile(`^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$`)
	hexColor  = regexp.MustCompile(`^#[0-9a-fA-F]{6}$`)
	// Windows 不允许用作文件或目录名，游戏 ID 会成为数据目录名。
	reserved = func() map[string]bool {
		names := map[string]bool{"con": true, "prn": true, "aux": true, "nul": true}
		for i := 1; i <= 9; i++ {
			names[fmt.Sprintf("com%d", i)] = true
			names[fmt.Sprintf("lpt%d", i)] = true
		}
		return names
	}()
	topFields = []string{"manifest_version", "id", "name", "version", "description", "authors", "launch",
		"requirements", "data", "documentation", "metadata"}
	systems  = []string{"macos", "linux", "windows"}
	arches   = []string{"x86_64", "arm64"}
	network  = []string{"none", "optional", "required"}
	colors   = []string{"optional", "16", "256", "truecolor"}
	unicodes = []string{"optional", "required"}
	keyboard = []string{"basic", "kitty-optional"}
	graphics = []string{"none", "kitty-optional"}
	saves    = []string{"none", "records", "progress", "resume"}
)

// CoverCell is one two-column cell of a gallery cover.
type CoverCell struct {
	Text, ASCII string
	FG          screen.RGB
	BG          *screen.RGB
	Bold        bool
}

// Presentation is optional gallery metadata; it never affects how a game runs.
type Presentation struct {
	NameEn     string
	Tags       []string
	Cover      []string
	Cells      map[rune]CoverCell
	Background screen.RGB
}

// Terminal holds the terminal requirements of a game.
type Terminal struct {
	Columns, Rows                      int
	Color, Unicode, Keyboard, Graphics string
}

// DefaultTerminal is what a manifest gets when it states nothing.
var DefaultTerminal = Terminal{80, 24, "optional", "optional", "basic", "none"}

// Entry is a validated game.
type Entry struct {
	ID, Name, Version, Description string
	Authors                        []string
	Argv                           []string
	Root, Cwd                      string
	Terminal                       Terminal
	Network                        string
	ManagedData                    bool
	SaveMode                       string
	Source                         Source
	Presentation                   Presentation
	// Issue 非空时游戏能展示但不能启动：协议版本过新、系统或架构不兼容。
	Issue string
}

// Host is the running system and CPU architecture in manifest terms.
type Host struct{ System, Arch string }

// CurrentHost describes this machine.
func CurrentHost() Host {
	arch := map[string]string{"amd64": "x86_64", "arm64": "arm64"}[runtime.GOARCH]
	if arch == "" {
		arch = runtime.GOARCH
	}
	system := map[string]string{"darwin": "macos", "windows": "windows"}[runtime.GOOS]
	if system == "" {
		system = "linux"
	}
	return Host{system, arch}
}

// Command resolves the launch argv. python is the interpreter used for {python} in development sources.
func (e Entry) Command(python string) ([]string, error) {
	argv := make([]string, len(e.Argv))
	for i, part := range e.Argv {
		if i == 0 && strings.HasPrefix(part, "./") {
			// 包内入口按原样拼接：校验已保证其中没有占位符，也不会越出游戏文件夹。
			argv[0] = filepath.Join(e.Root, filepath.FromSlash(part[2:]))
			continue
		}
		if strings.Contains(part, "{python}") {
			if python == "" {
				return nil, errors.New("找不到 Python（开发来源需要），可设置 TUI_ARCADE_PYTHON")
			}
			part = strings.ReplaceAll(part, "{python}", python)
		}
		argv[i] = strings.ReplaceAll(part, "{dir}", e.Root)
	}
	return argv, nil
}

// Problem is a manifest that could not be read.
type Problem struct{ Path, Reason string }

type object map[string]any

func fail(format string, args ...any) error { return fmt.Errorf(format, args...) }

func sanitize(text string) string {
	// 展示文本中不得带入终端控制序列与隐藏的格式字符。
	return strings.Map(func(r rune) rune {
		if unicode.Is(unicode.Cc, r) || unicode.Is(unicode.Cf, r) {
			return -1
		}
		return r
	}, text)
}

func only(o object, context string, allowed ...string) error {
	for key := range o {
		if !slices.Contains(allowed, key) {
			return fail("%s: unknown field %q", context, key)
		}
	}
	return nil
}

func child(o object, key, context string) (object, error) {
	value, ok := o[key]
	if !ok {
		return object{}, nil
	}
	nested, ok := value.(map[string]any)
	if !ok {
		return nil, fail("%s.%s must be an object", context, key)
	}
	return nested, nil
}

func text(o object, key, context string, required bool) (string, error) {
	value, ok := o[key]
	if !ok {
		if required {
			return "", fail("%s.%s is required", context, key)
		}
		return "", nil
	}
	s, ok := value.(string)
	if !ok || strings.TrimSpace(s) == "" {
		return "", fail("%s.%s must be a non-empty string", context, key)
	}
	return sanitize(s), nil
}

func choice(o object, key, fallback, context string, allowed []string) (string, error) {
	value, ok := o[key]
	if !ok {
		return fallback, nil
	}
	s, _ := value.(string)
	if !slices.Contains(allowed, s) {
		return "", fail("%s.%s must be one of %v", context, key, allowed)
	}
	return s, nil
}

func positive(o object, key string, fallback int, context string) (int, error) {
	value, ok := o[key]
	if !ok {
		return fallback, nil
	}
	number, ok := value.(json.Number)
	n, err := number.Int64()
	if !ok || err != nil || n <= 0 || n > 10000 {
		return 0, fail("%s.%s must be a positive integer", context, key)
	}
	return int(n), nil
}

func stringList(o object, key, context string, allowed []string, nonEmpty bool) ([]string, error) {
	value, ok := o[key]
	if !ok {
		if nonEmpty {
			return nil, fail("%s.%s is required", context, key)
		}
		return nil, nil
	}
	items, ok := value.([]any)
	if !ok || (nonEmpty && len(items) == 0) {
		return nil, fail("%s.%s must be a list", context, key)
	}
	result := make([]string, 0, len(items))
	for _, item := range items {
		s, ok := item.(string)
		if !ok || strings.TrimSpace(s) == "" || (allowed != nil && !slices.Contains(allowed, s)) {
			return nil, fail("%s.%s has an invalid element %v", context, key, item)
		}
		result = append(result, sanitize(s))
	}
	return result, nil
}

func within(root, path string) bool {
	rel, err := filepath.Rel(root, path)
	return err == nil && rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator)) && !filepath.IsAbs(rel)
}

// inside confines a manifest-relative path to the game folder, textually and after resolving symlinks.
func inside(root, relative, context string) (string, error) {
	// 冒号在 Windows 上可表示盘符或 NTFS 备用数据流；IsLocal 另外拒绝 Windows 设备名。
	if relative == "" || strings.ContainsAny(relative, "\\{}:") || strings.HasPrefix(relative, "/") ||
		filepath.IsAbs(relative) || filepath.VolumeName(relative) != "" || !filepath.IsLocal(filepath.FromSlash(relative)) {
		return "", fail("%s must be a relative path inside the game folder", context)
	}
	path := filepath.Join(root, filepath.FromSlash(relative))
	if !within(root, path) {
		return "", fail("%s escapes the game folder", context)
	}
	realRoot, err := filepath.EvalSymlinks(root)
	if err != nil {
		return "", fail("%s: %v", context, err)
	}
	// 从已存在的最近一级开始解析符号链接，防止借包内链接指向包外。
	existing, rest := path, ""
	for {
		if _, err := os.Lstat(existing); err == nil {
			break
		}
		parent := filepath.Dir(existing)
		if parent == existing {
			break
		}
		rest = filepath.Join(filepath.Base(existing), rest)
		existing = parent
	}
	real, err := filepath.EvalSymlinks(existing)
	if err != nil || !within(realRoot, filepath.Join(real, rest)) {
		return "", fail("%s escapes the game folder", context)
	}
	return path, nil
}

func color(value any, fallback screen.RGB) (screen.RGB, error) {
	if value == nil {
		return fallback, nil
	}
	s, _ := value.(string)
	if !hexColor.MatchString(s) {
		return screen.RGB{}, fail("invalid color %v", value)
	}
	var c [3]uint8
	for i := range c {
		fmt.Sscanf(s[1+2*i:3+2*i], "%02x", &c[i])
	}
	return screen.RGB{R: c[0], G: c[1], B: c[2]}, nil
}

// presentation 只影响画廊展示；格式有误时整体忽略，不影响游戏本身。
func presentation(data object) Presentation {
	empty := Presentation{Background: screen.RGB{R: 28, G: 28, B: 28}}
	metadata, err := child(data, "metadata", "manifest")
	if err != nil {
		return empty
	}
	spec, err := child(metadata, "presentation", "metadata")
	if err != nil {
		return empty
	}
	result := empty
	if value, ok := spec["name_en"]; ok {
		s, ok := value.(string)
		if !ok {
			return empty
		}
		result.NameEn = sanitize(s)
	}
	if result.Tags, err = stringList(spec, "tags", "presentation", nil, false); err != nil {
		return empty
	}
	cover, err := child(spec, "cover", "presentation")
	if err != nil {
		return empty
	}
	if result.Background, err = color(cover["background"], empty.Background); err != nil {
		return empty
	}
	rows, err := stringList(cover, "rows", "cover", nil, false)
	if err != nil {
		return empty
	}
	for i, row := range rows {
		if i == CoverHeight {
			break
		}
		runes := []rune(row)
		result.Cover = append(result.Cover, string(runes[:min(len(runes), CoverWidth)]))
	}
	cells, err := child(cover, "cells", "cover")
	if err != nil {
		return empty
	}
	result.Cells = map[rune]CoverCell{}
	for key, value := range cells {
		spec, ok := value.(map[string]any)
		keys := []rune(key)
		if !ok || len(keys) != 1 {
			return empty
		}
		glyph, _ := spec["text"].(string)
		if _, present := spec["text"]; !present {
			glyph = "  "
		}
		ascii, present := spec["ascii"].(string)
		if _, has := spec["ascii"]; !has {
			ascii, present = glyph, true
		}
		// 每个封面格固定占两列；宽度不符会让整行错位。
		if !present || screen.StringWidth(glyph) != 2 || screen.StringWidth(ascii) != 2 || !isASCII(ascii) {
			return empty
		}
		cell := CoverCell{Text: sanitize(glyph), ASCII: sanitize(ascii)}
		if cell.FG, err = color(spec["fg"], screen.RGB{R: 225, G: 225, B: 225}); err != nil {
			return empty
		}
		if spec["bg"] != nil {
			bg, err := color(spec["bg"], screen.RGB{})
			if err != nil {
				return empty
			}
			cell.BG = &bg
		}
		bold, _ := spec["bold"].(bool)
		cell.Bold = bold
		result.Cells[keys[0]] = cell
	}
	return result
}

func isASCII(s string) bool {
	for _, r := range s {
		if r > unicode.MaxASCII || unicode.IsControl(r) {
			return false
		}
	}
	return true
}

// Parse validates one manifest. A newer protocol or a foreign system yields an Entry with Issue set.
func Parse(path string, source Source, host Host) (Entry, error) {
	absolute, err := filepath.Abs(path)
	if err != nil {
		return Entry{}, err
	}
	// 包根目录取清单所在的目录，不跟随清单文件本身的符号链接。
	root := filepath.Dir(absolute)
	if info, err := os.Lstat(absolute); err != nil {
		return Entry{}, err
	} else if source == Installed && info.Mode()&os.ModeSymlink != 0 {
		return Entry{}, fail("installed manifests must not be symlinks")
	}
	raw, err := os.ReadFile(absolute)
	if err != nil {
		return Entry{}, err
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	var data object
	if err := decoder.Decode(&data); err != nil {
		return Entry{}, fail("invalid JSON: %v", err)
	}
	if decoder.More() {
		return Entry{}, fail("invalid JSON: trailing data")
	}
	version, ok := data["manifest_version"].(json.Number)
	protocol, err := version.Int64()
	if !ok || err != nil || protocol < 1 {
		return Entry{}, fail("manifest_version must be a positive integer")
	}
	id, _ := data["id"].(string)
	if !idPattern.MatchString(id) || reserved[id] {
		return Entry{}, fail("id must match [a-z][a-z0-9-]{0,63} and not be a reserved name")
	}
	name, err := text(data, "name", "manifest", true)
	if err != nil {
		return Entry{}, err
	}
	entry := Entry{ID: id, Name: name, Root: root, Cwd: root, Source: source, Terminal: DefaultTerminal,
		Network: "none", SaveMode: "none", Presentation: presentation(data)}
	if protocol != Protocol {
		// 协议更新的清单不猜测解析，只保留可展示的信息并禁止启动。
		entry.Presentation = Presentation{Background: entry.Presentation.Background}
		entry.Issue = fmt.Sprintf("需要更新平台（清单协议 %d）", protocol)
		return entry, nil
	}
	if err := only(data, "manifest", topFields...); err != nil {
		return Entry{}, err
	}
	if entry.Version, err = text(data, "version", "manifest", true); err != nil {
		return Entry{}, err
	}
	if !semver.MatchString(entry.Version) {
		return Entry{}, fail("version must be MAJOR.MINOR.PATCH")
	}
	if entry.Description, err = text(data, "description", "manifest", false); err != nil {
		return Entry{}, err
	}
	if entry.Authors, err = stringList(data, "authors", "manifest", nil, true); err != nil {
		return Entry{}, err
	}
	if err := parseLaunch(data, source, &entry); err != nil {
		return Entry{}, err
	}
	if err := parseRequirements(data, host, &entry); err != nil {
		return Entry{}, err
	}
	if err := parseData(data, &entry); err != nil {
		return Entry{}, err
	}
	documentation, err := child(data, "documentation", "manifest")
	if err != nil {
		return Entry{}, err
	}
	if err := only(documentation, "documentation", "readme", "license", "credits"); err != nil {
		return Entry{}, err
	}
	for key, value := range documentation {
		relative, _ := value.(string)
		file, err := inside(root, relative, "documentation."+key)
		if err != nil {
			return Entry{}, err
		}
		if info, err := os.Stat(file); err != nil || !info.Mode().IsRegular() {
			return Entry{}, fail("documentation.%s does not exist", key)
		}
	}
	return entry, nil
}

func parseLaunch(data object, source Source, entry *Entry) error {
	launch, err := child(data, "launch", "manifest")
	if err != nil {
		return err
	}
	if _, ok := data["launch"]; !ok {
		return fail("launch is required")
	}
	if err := only(launch, "launch", "argv", "cwd"); err != nil {
		return err
	}
	// 启动参数不做清洗：含控制或格式字符的参数直接拒绝，而不是悄悄改写后执行。
	if items, ok := launch["argv"].([]any); ok {
		for _, item := range items {
			if s, ok := item.(string); ok && sanitize(s) != s {
				return fail("launch.argv must not contain control or format characters")
			}
		}
	}
	if entry.Argv, err = stringList(launch, "argv", "launch", nil, true); err != nil {
		return err
	}
	first := entry.Argv[0]
	for _, part := range entry.Argv {
		// 预构建包不得依赖玩家电脑上的解释器；{python} 只允许用于开发来源。
		if source != Dev && strings.Contains(part, "{python}") {
			return fail("{python} is only allowed for development sources")
		}
	}
	switch {
	case strings.HasPrefix(first, "./"):
		if _, err := inside(entry.Root, first[2:], "launch.argv[0]"); err != nil {
			return err
		}
	case source != Dev:
		return fail("launch.argv[0] must be an entry inside the package (./...)")
	case strings.Contains(first, "{dir}"):
		// 占位符只能出现在参数里；入口要么是 ./ 包内路径，要么是 {python}。
		return fail("launch.argv[0] must not use {dir}; use ./ for entries inside the package")
	}
	cwd := "."
	if value, ok := launch["cwd"]; ok {
		cwd, _ = value.(string)
	}
	if cwd == "." {
		entry.Cwd = entry.Root
		return nil
	}
	entry.Cwd, err = inside(entry.Root, cwd, "launch.cwd")
	return err
}

func parseRequirements(data object, host Host, entry *Entry) error {
	requirements, err := child(data, "requirements", "manifest")
	if err != nil {
		return err
	}
	if err := only(requirements, "requirements", "os", "arch", "network", "terminal"); err != nil {
		return err
	}
	terminal, err := child(requirements, "terminal", "requirements")
	if err != nil {
		return err
	}
	if err := only(terminal, "requirements.terminal", "columns", "rows", "color", "unicode", "keyboard", "graphics"); err != nil {
		return err
	}
	t := &entry.Terminal
	context := "requirements.terminal"
	if t.Columns, err = positive(terminal, "columns", 80, context); err != nil {
		return err
	}
	if t.Rows, err = positive(terminal, "rows", 24, context); err != nil {
		return err
	}
	for _, field := range []struct {
		key     string
		target  *string
		allowed []string
	}{{"color", &t.Color, colors}, {"unicode", &t.Unicode, unicodes}, {"keyboard", &t.Keyboard, keyboard}, {"graphics", &t.Graphics, graphics}} {
		if *field.target, err = choice(terminal, field.key, *field.target, context, field.allowed); err != nil {
			return err
		}
	}
	if entry.Network, err = choice(requirements, "network", "none", "requirements", network); err != nil {
		return err
	}
	wantSystems, err := stringList(requirements, "os", "requirements", systems, false)
	if err != nil {
		return err
	}
	wantArches, err := stringList(requirements, "arch", "requirements", arches, false)
	if err != nil {
		return err
	}
	if (len(wantSystems) > 0 && !slices.Contains(wantSystems, host.System)) ||
		(len(wantArches) > 0 && !slices.Contains(wantArches, host.Arch)) {
		describe := func(values []string, fallback string) string {
			if len(values) == 0 {
				return fallback
			}
			return strings.Join(values, "/")
		}
		entry.Issue = fmt.Sprintf("本机不支持（%s，%s）", describe(wantSystems, "任意系统"), describe(wantArches, "任意架构"))
	}
	return nil
}

func parseData(data object, entry *Entry) error {
	spec, err := child(data, "data", "manifest")
	if err != nil {
		return err
	}
	if err := only(spec, "data", "managed_directory", "save_mode"); err != nil {
		return err
	}
	entry.ManagedData = true
	if value, ok := spec["managed_directory"]; ok {
		managed, ok := value.(bool)
		if !ok {
			return fail("data.managed_directory must be a boolean")
		}
		entry.ManagedData = managed
	}
	entry.SaveMode, err = choice(spec, "save_mode", "none", "data", saves)
	return err
}

// Dir is a folder whose subfolders each hold one game.
type Dir struct {
	Path   string
	Source Source
}

// Load reads every <dir>/<folder>/game.json. Duplicate IDs keep the first one found (development first).
func Load(dirs []Dir, host Host) ([]Entry, []Problem) {
	var entries []Entry
	var problems []Problem
	seen := map[string]bool{}
	for _, dir := range dirs {
		folders, err := os.ReadDir(dir.Path)
		if err != nil {
			continue
		}
		for _, folder := range folders {
			manifest := filepath.Join(dir.Path, folder.Name(), Manifest)
			if _, err := os.Lstat(manifest); err != nil {
				continue
			}
			entry, err := Parse(manifest, dir.Source, host)
			if err != nil {
				problems = append(problems, Problem{manifest, err.Error()})
				continue
			}
			if !seen[entry.ID] {
				seen[entry.ID] = true
				entries = append(entries, entry)
			}
		}
	}
	return entries, problems
}

// Dirs lists development sources (the repository games/ plus TUI_ARCADE_DEV_GAMES) and the installed programs.
func Dirs(repo, devGames, programs string) []Dir {
	var dirs []Dir
	if repo != "" {
		dirs = append(dirs, Dir{filepath.Join(repo, "games"), Dev})
	}
	for _, path := range filepath.SplitList(devGames) {
		if path != "" {
			dirs = append(dirs, Dir{path, Dev})
		}
	}
	return append(dirs, Dir{programs, Installed})
}

// FindRepo walks up from each start directory to the checkout that contains platform/go.mod.
func FindRepo(starts ...string) string {
	for _, start := range starts {
		dir, err := filepath.Abs(start)
		if err != nil || start == "" {
			continue
		}
		for {
			if _, err := os.Stat(filepath.Join(dir, "platform", "go.mod")); err == nil {
				if info, err := os.Stat(filepath.Join(dir, "games")); err == nil && info.IsDir() {
					return dir
				}
			}
			parent := filepath.Dir(dir)
			if parent == dir {
				break
			}
			dir = parent
		}
	}
	return ""
}
