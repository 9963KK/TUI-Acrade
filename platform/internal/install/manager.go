package install

import (
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"

	"tuiarcade/platform/internal/catalog"
	"tuiarcade/platform/internal/launcher"
	"tuiarcade/platform/internal/paths"
	"tuiarcade/platform/internal/registry"
)

// Manager 管理安装事务，源码与玩家存档分别管理。
type Manager struct {
	Roots         paths.Roots
	Repo          string
	Host          catalog.Host
	In            io.Reader
	Out           io.Writer
	Env           []string
	Columns, Rows int
	// Execute 允许测试替换前台 git／pip 进程，无需访问网络。
	Execute func(*exec.Cmd) error
}

func New(roots paths.Roots, repo string) *Manager {
	return &Manager{Roots: roots, Repo: repo, Host: catalog.CurrentHost(), In: os.Stdin,
		Out: os.Stdout, Env: os.Environ(), Columns: 80, Rows: 24}
}

func (m *Manager) RecordPath() string { return filepath.Join(m.Roots.Data, "installed.json") }

// Candidate 保存待确认的源码；租约防止另一个 tplay 窗口清理正在确认的克隆。
type Candidate struct {
	Entry              catalog.Entry
	URL, Commit, Stage string
	release            func()
	retained           bool
}

// Choice 对应安装页面的一行；不支持的游戏留在安装页面。
type Choice struct {
	Entry  catalog.Entry
	Status string
	Record *registry.Record
}

func (m *Manager) Choices() ([]Choice, error) {
	f, err := registry.Load(m.RecordPath())
	if err != nil {
		return nil, err
	}
	entries, _ := catalog.BuiltinGames(m.Repo, m.Host)
	seen := map[string]bool{}
	choices := []Choice{}
	appendEntry := func(entry catalog.Entry, record *registry.Record) {
		status := "可安装"
		if record != nil {
			status = "已安装"
			if record.Status == registry.NeedsRepair {
				status = "需要修复"
			}
		}
		if entry.Issue != "" && record == nil {
			status = "本机不支持"
		}
		choices = append(choices, Choice{entry, status, record})
		seen[entry.ID] = true
	}
	for _, entry := range entries {
		if record := f.Find(entry.ID); record != nil && record.Path != entry.Root {
			continue
		}
		appendEntry(entry, f.Find(entry.ID))
	}
	for i := range f.Games {
		r := &f.Games[i]
		if seen[r.ID] {
			continue
		}
		entry, err := catalog.Parse(filepath.Join(r.Path, catalog.Manifest), catalog.Source(r.Source), m.Host)
		if err != nil {
			entry = catalog.Entry{ID: r.ID, Name: r.ID, Root: r.Path, Source: catalog.Source(r.Source), Issue: err.Error()}
		}
		appendEntry(entry, r)
	}
	return choices, nil
}

func (c *Candidate) Close(keep bool) {
	keep = keep || c.retained
	if c.Stage != "" && keep {
		_ = os.WriteFile(filepath.Join(c.Stage, ".keep"), []byte("retained for diagnosis\n"), 0o600)
	}
	if c.release != nil {
		c.release()
		c.release = nil
	}
	if c.Stage != "" && !keep {
		_ = os.RemoveAll(c.Stage)
	}
}

// CleanStaging 恢复中断事务并清理暂存目录，跳过其他窗口持有的租约。
func (m *Manager) CleanStaging() error {
	releaseRecord, err := registry.Lock(m.RecordPath() + ".lock")
	if err != nil {
		return err
	}
	defer releaseRecord()
	f, err := registry.Load(m.RecordPath())
	if err != nil {
		return err
	}
	root := filepath.Join(m.Roots.Programs, ".staging")
	if err := m.safeRemoval(filepath.Join(root, "check")); err != nil {
		return err
	}
	items, err := os.ReadDir(root)
	if errors.Is(err, fs.ErrNotExist) {
		return m.cleanEnvironments(f)
	}
	if err != nil {
		return err
	}
	for _, item := range items {
		if !item.IsDir() {
			continue
		}
		path := filepath.Join(root, item.Name())
		release, err := registry.TryLock(filepath.Join(path, ".lease"))
		if err != nil {
			continue
		}
		if err := m.recoverTransaction(path, f); err != nil {
			release()
			return err
		}
		if _, err := os.Stat(filepath.Join(path, ".keep")); err == nil {
			release()
			continue
		}
		release()
		if err := os.RemoveAll(path); err != nil {
			return err
		}
	}
	return m.cleanEnvironments(f)
}

func (m *Manager) command(cmd *exec.Cmd) error {
	cmd.Stdin, cmd.Stdout, cmd.Stderr = m.In, m.Out, m.Out
	cmd.Env = m.Env
	if m.Execute != nil {
		return m.Execute(cmd)
	}
	return cmd.Run()
}

// Acquire 获取源码，只克隆认可的 git 协议，其余来源按本地目录读取。
func (m *Manager) Acquire(input string, source catalog.Source) (*Candidate, error) {
	c := &Candidate{}
	path := input
	if source == catalog.Git {
		if !(strings.HasPrefix(input, "https://") || strings.HasPrefix(input, "ssh://") ||
			strings.HasPrefix(input, "git@") || strings.HasPrefix(input, "file://")) {
			return nil, errors.New("git 地址须使用 https://、ssh://、git@ 或 file://")
		}
		root := filepath.Join(m.Roots.Programs, ".staging")
		stage, release, err := m.leasedDirectory(root, "clone-")
		if err != nil {
			return nil, err
		}
		c.Stage, c.URL = stage, input
		c.release = release
		path = filepath.Join(stage, "source")
		fmt.Fprintln(m.Out, "[1/4] 获取游戏源码：", input)
		if err := m.command(exec.Command("git", "clone", "--depth", "1", "--", input, path)); err != nil {
			c.Close(false)
			return nil, fmt.Errorf("git clone 失败：%w", err)
		}
		cmd := exec.Command("git", "-C", path, "rev-parse", "HEAD")
		out, err := cmd.Output()
		if err != nil {
			c.Close(false)
			return nil, err
		}
		c.Commit = strings.TrimSpace(string(out))
	} else {
		if source != catalog.Builtin && source != catalog.Local {
			return nil, errors.New("未知游戏来源")
		}
		if input == "~" || strings.HasPrefix(input, "~/") {
			home, err := os.UserHomeDir()
			if err != nil {
				return nil, err
			}
			path = home
			if input != "~" {
				path = filepath.Join(home, strings.TrimPrefix(input, "~/"))
			}
		}
		if filepath.Base(path) == catalog.Manifest {
			path = filepath.Dir(path)
		}
	}
	entry, err := catalog.Parse(filepath.Join(path, catalog.Manifest), source, m.Host)
	if err != nil {
		c.Close(false)
		return nil, err
	}
	c.Entry = entry
	return c, nil
}

func IsGit(input string) bool {
	return strings.HasPrefix(input, "https://") || strings.HasPrefix(input, "ssh://") ||
		strings.HasPrefix(input, "git@") || strings.HasPrefix(input, "file://")
}

func (m *Manager) Builtin(id string) (*Candidate, error) {
	entries, _ := catalog.BuiltinGames(m.Repo, m.Host)
	for _, entry := range entries {
		if entry.ID == id {
			return &Candidate{Entry: entry}, nil
		}
	}
	return nil, fmt.Errorf("找不到内置游戏 %q", id)
}

// Existing 加载待修复的安装记录，不重新克隆源码。
func (m *Manager) Existing(id string) (*Candidate, error) {
	f, err := registry.Load(m.RecordPath())
	if err != nil {
		return nil, err
	}
	r := f.Find(id)
	if r == nil {
		return nil, fmt.Errorf("游戏 %q 尚未安装", id)
	}
	entry, err := catalog.Parse(filepath.Join(r.Path, catalog.Manifest), catalog.Source(r.Source), m.Host)
	if err != nil {
		return nil, err
	}
	if entry.ID != id {
		return nil, errors.New("游戏 ID 已改变，请卸载旧登记后重新添加")
	}
	return &Candidate{Entry: entry, URL: r.URL, Commit: r.Commit}, nil
}

func (m *Manager) collision(f *registry.File, c *Candidate) error {
	if existing := f.Find(c.Entry.ID); existing != nil {
		same := existing.Path == c.Entry.Root && existing.Source == string(c.Entry.Source)
		if c.Stage != "" {
			same = existing.Source == string(catalog.Git) && existing.URL == c.URL
		}
		if !same {
			return fmt.Errorf("ID %q 已由另一来源登记：%s", c.Entry.ID, existing.Path)
		}
	}
	return nil
}

// Plan 在执行依赖安装或游戏代码之前生成可确认的操作计划。
func (m *Manager) Plan(c *Candidate) ([]string, error) {
	f, err := registry.Load(m.RecordPath())
	if err != nil {
		return nil, err
	}
	if err := m.collision(&f, c); err != nil {
		return nil, err
	}
	if c.Entry.Issue != "" {
		return nil, errors.New(c.Entry.Issue)
	}
	lines := []string{c.Entry.Name + " v" + c.Entry.Version, "作者：" + strings.Join(c.Entry.Authors, "、"),
		"来源：" + string(c.Entry.Source), "目录：" + c.Entry.Root}
	if c.URL != "" {
		lines = append(lines, "git："+c.URL, "提交："+c.Commit)
	}
	if c.Entry.Python != nil {
		python, problem := FindPython(c.Entry.Python.Version, os.Getenv)
		if problem != "" {
			return nil, errors.New(problem)
		}
		lines = append(lines, "解释器："+python.Path+"（"+python.Version.String()+"）")
		if c.Entry.Python.Packages != "" {
			lines = append(lines, "执行：python -m venv <独立环境>", "执行：<环境>/python -m pip install -r "+c.Entry.Python.Packages)
		}
	}
	argv, _ := c.Entry.Command("<所选 Python>")
	lines = append(lines, "试运行："+strings.Join(argv, " "), "通过后登记；卸载始终保留存档。")
	return lines, nil
}

// Check 执行静态检查，可选用存档副本进行终端试运行。
func (m *Manager) Check(entry catalog.Entry, python string, run bool) []registry.Check {
	checks := []registry.Check{}
	add := func(name, detail string, ok bool) {
		checks = append(checks, registry.Check{Name: name, OK: ok, Detail: detail})
	}
	parsed, err := catalog.Parse(filepath.Join(entry.Root, catalog.Manifest), entry.Source, m.Host)
	if err != nil {
		add("清单", err.Error(), false)
		return checks
	}
	entry = parsed
	add("清单", "格式与路径有效", true)
	add("系统与架构", entry.Issue, entry.Issue == "")
	if entry.Issue != "" {
		return checks
	}
	if entry.Python != nil {
		problem := ""
		if python == "" {
			selected, issue := FindPython(entry.Python.Version, os.Getenv)
			python, problem = selected.Path, issue
		} else {
			version, err := probe(python)
			if err != nil {
				problem = "解释器无法运行：" + python
			} else if !entry.Python.Version.Allows(version) {
				problem = "Python 版本不满足 " + entry.Python.Version.String()
			}
		}
		add("解释器", python+" "+problem, problem == "")
		if problem != "" {
			return checks
		}
		missing, err := MissingModules(python, entry.Python.Modules)
		if err != nil {
			add("模块", err.Error(), false)
		} else {
			add("模块", strings.Join(missing, "、"), len(missing) == 0)
		}
	}
	argv, err := entry.Command(python)
	if err == nil {
		_, err = exec.LookPath(argv[0])
	}
	if err != nil {
		add("入口", err.Error(), false)
	} else {
		add("入口", argv[0], true)
	}
	if !run || Problem(checks) != "" {
		return checks
	}
	temp, err := os.MkdirTemp("", "tplay-check-")
	if err != nil {
		add("试运行", err.Error(), false)
		return checks
	}
	defer os.RemoveAll(temp)
	isolated := paths.Roots{Programs: m.Roots.Programs, Data: filepath.Join(temp, "data"), Logs: filepath.Join(temp, "logs"), Cache: filepath.Join(temp, "cache")}
	if err := copyData(m.Roots.GameData(entry.ID), isolated.GameData(entry.ID)); err != nil {
		add("存档副本", err.Error(), false)
		return checks
	}
	env := make([]string, 0, len(m.Env)+2)
	for _, pair := range m.Env {
		key, _, _ := strings.Cut(pair, "=")
		if !strings.EqualFold(key, "TUI_ARCADE_HOME") && !strings.EqualFold(key, "XDG_DATA_HOME") {
			env = append(env, pair)
		}
	}
	env = append(env, "TUI_ARCADE_HOME="+temp, "XDG_DATA_HOME="+filepath.Join(temp, "xdg"))
	game, problem := launcher.Prepare(entry, env, isolated, python)
	if problem != "" {
		add("试运行", problem, false)
		return checks
	}
	result := Smoke(game.Argv, game.Env, game.Dir, max(80, m.Columns), max(24, m.Rows))
	checks = append(checks, registry.Check{Name: "试运行", OK: result.OK, Skipped: result.Skipped, Detail: result.Detail})
	if result.Output != "" {
		fmt.Fprintln(m.Out, result.Output)
	}
	return checks
}

func Problem(checks []registry.Check) string {
	for _, check := range checks {
		if !check.OK {
			return check.Name + "：" + check.Detail
		}
	}
	return ""
}

func Report(checks []registry.Check) []string {
	lines := []string{}
	for _, check := range checks {
		status := "通过"
		if !check.OK {
			status = "失败"
		}
		if check.Skipped {
			status = "跳过"
		}
		lines = append(lines, "["+status+"] "+check.Name+" "+check.Detail)
	}
	return lines
}

func copyData(source, dest string) error {
	if _, err := os.Stat(source); errors.Is(err, fs.ErrNotExist) {
		return nil
	} else if err != nil {
		return err
	}
	return filepath.WalkDir(source, func(path string, item fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		rel, err := filepath.Rel(source, path)
		if err != nil {
			return err
		}
		target := filepath.Join(dest, rel)
		if item.IsDir() {
			return os.MkdirAll(target, 0o755)
		}
		if !item.Type().IsRegular() {
			return fmt.Errorf("存档包含不支持的文件：%s", rel)
		}
		in, err := os.Open(path)
		if err != nil {
			return err
		}
		defer in.Close()
		out, err := os.OpenFile(target, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
		if err != nil {
			return err
		}
		_, err = io.Copy(out, in)
		closeErr := out.Close()
		if err != nil {
			return err
		}
		return closeErr
	})
}

func envPython(path string) string {
	if runtime.GOOS == "windows" {
		return filepath.Join(path, "Scripts", "python.exe")
	}
	return filepath.Join(path, "bin", "python")
}

// Install 只登记完整检查通过的游戏；修复失败时保留旧运行环境。
func (m *Manager) Install(c *Candidate) (result registry.Record, failure error) {
	releaseGame, err := m.gameLock(c.Entry.ID)
	if err != nil {
		return registry.Record{}, err
	}
	defer releaseGame()
	fresh, err := catalog.Parse(filepath.Join(c.Entry.Root, catalog.Manifest), c.Entry.Source, m.Host)
	if err != nil {
		return registry.Record{}, err
	}
	if fresh.ID != c.Entry.ID {
		return registry.Record{}, errors.New("确认后游戏 ID 已改变，请重新添加")
	}
	c.Entry = fresh
	if _, err := m.Plan(c); err != nil {
		return registry.Record{}, err
	}
	logDir := m.Roots.GameLogs(c.Entry.ID)
	if err := os.MkdirAll(logDir, 0o755); err != nil {
		return registry.Record{}, err
	}
	logPath := filepath.Join(logDir, "install.log")
	log, err := os.OpenFile(logPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		return registry.Record{}, err
	}
	defer log.Close()
	var checks []registry.Check
	defer func() {
		if failure != nil {
			fmt.Fprintln(log, failure)
			_, _ = registry.Update(m.RecordPath(), func(f *registry.File) error {
				r := f.Find(c.Entry.ID)
				if r == nil || r.Path != c.Entry.Root || r.Source != string(c.Entry.Source) {
					return nil
				}
				r.Status, r.Problem, r.LogFile, r.CheckedAt = registry.NeedsRepair, failure.Error(), logPath, time.Now().UTC()
				r.Checks = checks
				if len(checks) == 0 {
					r.Checks = []registry.Check{{Name: "运行环境", Detail: failure.Error()}}
				}
				return nil
			})
			failure = fmt.Errorf("%w；日志：%s", failure, logPath)
		}
	}()
	worker := *m
	worker.Out = io.MultiWriter(m.Out, log)
	fmt.Fprintln(worker.Out, "[2/4] 准备运行环境：", c.Entry.Name)
	python, environment := "", ""
	committed := false
	var releaseEnv func()
	defer func() {
		if releaseEnv != nil {
			releaseEnv()
		}
		if !committed && environment != "" {
			_ = os.RemoveAll(environment)
		}
	}()
	if spec := c.Entry.Python; spec != nil {
		selected, problem := FindPython(spec.Version, os.Getenv)
		if problem != "" {
			return registry.Record{}, errors.New(problem)
		}
		python = selected.Path
		if spec.Packages != "" {
			root := filepath.Join(m.Roots.Programs, "envs", c.Entry.ID)
			environment, releaseEnv, err = m.leasedDirectory(root, "runtime-")
			if err != nil {
				return registry.Record{}, err
			}
			if err := worker.command(exec.Command(python, "-m", "venv", environment)); err != nil {
				return registry.Record{}, fmt.Errorf("创建环境失败：%w", err)
			}
			python = envPython(environment)
			cmd := exec.Command(python, "-m", "pip", "install", "-r", spec.Packages)
			cmd.Dir = c.Entry.Root
			if err := worker.command(cmd); err != nil {
				return registry.Record{}, fmt.Errorf("安装依赖失败：%w", err)
			}
		}
	}
	fmt.Fprintln(worker.Out, "[3/4] 检查并试运行")
	checks = worker.Check(c.Entry, python, true)
	for _, line := range Report(checks) {
		fmt.Fprintln(worker.Out, line)
	}
	if problem := Problem(checks); problem != "" {
		return registry.Record{}, errors.New(problem)
	}
	fingerprint, err := Fingerprint(c.Entry.Root)
	if err != nil {
		return registry.Record{}, err
	}
	now := time.Now().UTC()
	if c.Entry.Source == catalog.Git {
		if out, err := exec.Command("git", "-C", c.Entry.Root, "rev-parse", "HEAD").Output(); err == nil {
			c.Commit = strings.TrimSpace(string(out))
		}
	}
	record := registry.Record{ID: c.Entry.ID, Source: string(c.Entry.Source), Path: c.Entry.Root, URL: c.URL,
		Commit: c.Commit, Python: python, Env: environment, Fingerprint: fingerprint, Status: registry.Installed,
		Checks: checks, LogFile: logPath, CheckedAt: now, InstalledAt: now}
	fmt.Fprintln(worker.Out, "[4/4] 登记游戏")
	moved := false
	oldEnv := ""
	_, err = registry.Update(m.RecordPath(), func(f *registry.File) error {
		if err := m.collision(f, c); err != nil {
			return err
		}
		if old := f.Find(c.Entry.ID); old != nil {
			oldEnv = old.Env
		}
		if c.Stage != "" {
			final := filepath.Join(m.Roots.Programs, "games", c.Entry.ID)
			if _, err := os.Lstat(final); err == nil {
				return errors.New("克隆目录已存在，请先卸载旧游戏")
			}
			if err := os.MkdirAll(filepath.Dir(final), 0o755); err != nil {
				return err
			}
			if err := m.safeRemoval(final); err != nil {
				return err
			}
			if err := writeTransaction(c.Stage, c.Entry.ID, "install"); err != nil {
				return err
			}
			if err := os.Rename(c.Entry.Root, final); err != nil {
				return err
			}
			record.Path, moved = final, true
		}
		f.Put(record)
		return nil
	})
	if err != nil {
		if moved {
			if recoveryErr := os.Rename(record.Path, c.Entry.Root); recoveryErr != nil {
				c.retained = true
				return registry.Record{}, errors.Join(err, recoveryErr)
			}
		}
		return registry.Record{}, err
	}
	committed = true
	if oldEnv != "" && oldEnv != environment && m.ownedEnv(oldEnv, c.Entry.ID) && m.safeRemoval(oldEnv) == nil {
		_ = os.RemoveAll(oldEnv)
	}
	c.Close(false)
	return record, nil
}

// Uninstall 只删除平台拥有的克隆和环境，保留本地／内置源码与存档。
func (m *Manager) Uninstall(id string) error {
	if !validID(id) {
		return errors.New("非法游戏 ID")
	}
	releaseGame, err := m.gameLock(id)
	if err != nil {
		return err
	}
	defer releaseGame()
	stage, releaseStage, err := m.leasedDirectory(filepath.Join(m.Roots.Programs, ".staging"), "uninstall-")
	if err != nil {
		return err
	}
	clean := false
	defer func() {
		releaseStage()
		if clean {
			_ = os.RemoveAll(stage)
		}
	}()
	var record registry.Record
	_, err = registry.Update(m.RecordPath(), func(f *registry.File) error {
		r := f.Find(id)
		if r == nil {
			return fmt.Errorf("游戏 %q 尚未安装", id)
		}
		record = *r
		if record.Source == string(catalog.Git) && record.Path != filepath.Join(m.Roots.Programs, "games", id) {
			return errors.New("克隆目录不属于平台，拒绝删除")
		}
		if record.Source == string(catalog.Git) {
			if err := m.safeRemoval(record.Path); err != nil {
				return err
			}
		}
		if err := m.safeRemoval(filepath.Join(m.Roots.Programs, "envs", id)); err != nil {
			return err
		}
		if err := writeTransaction(stage, id, "uninstall"); err != nil {
			return err
		}
		if record.Source == string(catalog.Git) {
			if err := m.restoreMove(record.Path, filepath.Join(stage, "game")); err != nil {
				return err
			}
		}
		if err := m.restoreMove(filepath.Join(m.Roots.Programs, "envs", id), filepath.Join(stage, "envs")); err != nil {
			return err
		}
		f.Remove(id)
		return nil
	})
	if err != nil {
		// 保存记录失败时恢复原目录；恢复失败则保留事务，供下一次启动重试。
		f, loadErr := registry.Load(m.RecordPath())
		if loadErr == nil {
			if recoveryErr := m.recoverTransaction(stage, f); recoveryErr != nil {
				return errors.Join(err, recoveryErr)
			}
			clean = true
		}
		return err
	}
	clean = true
	releaseStage()
	releaseStage = func() {}
	return os.RemoveAll(stage)
}

// Library 只读取已登记游戏；失效的安装仍显示为需要修复。
func (m *Manager) Library() ([]catalog.Entry, error) {
	f, err := registry.Load(m.RecordPath())
	if err != nil {
		return nil, err
	}
	entries := []catalog.Entry{}
	for _, record := range f.Games {
		if !validID(record.ID) {
			return nil, errors.New("安装记录包含非法游戏 ID")
		}
		entry, parseErr := catalog.Parse(filepath.Join(record.Path, catalog.Manifest), catalog.Source(record.Source), m.Host)
		if parseErr != nil || entry.ID != record.ID {
			entry = catalog.Entry{ID: record.ID, Name: record.ID, Root: record.Path, Source: catalog.Source(record.Source), Terminal: catalog.DefaultTerminal}
			entry.Issue = "清单失效，请重新安装"
			if parseErr != nil {
				entry.Issue += "：" + parseErr.Error()
			}
		} else {
			entry.Issue = Problem(m.Check(entry, record.Python, false))
		}
		fingerprint, hashErr := Fingerprint(record.Path)
		if hashErr != nil {
			entry.Issue = "无法读取游戏目录：" + hashErr.Error()
		}
		if record.Status == registry.NeedsRepair && entry.Issue == "" {
			entry.Issue = "需要重新安装并通过试运行"
		}
		if entry.Issue != "" || fingerprint != record.Fingerprint {
			_, err = registry.Update(m.RecordPath(), func(current *registry.File) error {
				r := current.Find(record.ID)
				if r == nil || r.InstalledAt != record.InstalledAt {
					return nil
				}
				r.Fingerprint, r.CheckedAt = fingerprint, time.Now().UTC()
				r.Checks = m.Check(entry, record.Python, false)
				if entry.Issue != "" {
					r.Status, r.Problem = registry.NeedsRepair, entry.Issue
				}
				return nil
			})
			if err != nil {
				return nil, err
			}
		}
		entries = append(entries, entry)
	}
	return entries, nil
}

// Launch 使用安装时记录的解释器，在交接终端之前重新检查。
func (m *Manager) Launch(entry catalog.Entry) (*launcher.Game, string) {
	release, err := m.gameLock(entry.ID)
	if err != nil {
		return nil, err.Error()
	}
	ready := false
	defer func() {
		if !ready {
			release()
		}
	}()
	f, err := registry.Load(m.RecordPath())
	if err != nil {
		return nil, err.Error()
	}
	r := f.Find(entry.ID)
	if r == nil {
		return nil, "游戏尚未安装"
	}
	if r.Status != registry.Installed {
		return nil, "需要修复：" + r.Problem
	}
	fresh, err := catalog.Parse(filepath.Join(r.Path, catalog.Manifest), catalog.Source(r.Source), m.Host)
	if err != nil {
		return nil, err.Error()
	}
	if fresh.ID != entry.ID {
		return nil, "游戏 ID 已改变，请重新安装"
	}
	entry = fresh
	if problem := Problem(m.Check(entry, r.Python, false)); problem != "" {
		return nil, problem
	}
	game, problem := launcher.Prepare(entry, m.Env, m.Roots, r.Python)
	if problem != "" {
		return nil, problem
	}
	game.Release, ready = release, true
	return game, ""
}
