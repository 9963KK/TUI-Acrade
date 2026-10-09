package main

import (
	"bufio"
	"errors"
	"fmt"
	"io"
	"path/filepath"
	"strings"

	"tuiarcade/platform/internal/catalog"
	"tuiarcade/platform/internal/install"
	"tuiarcade/platform/internal/registry"
)

type options struct {
	target         string
	yes, run, keep bool
}

// 选项可以位于目标之前或之后，例如 tplay check ID --run。
func parseOptions(args []string) (options, error) {
	o := options{}
	for _, arg := range args {
		switch arg {
		case "--yes", "-y":
			o.yes = true
		case "--run":
			o.run = true
		case "--keep":
			o.keep = true
		default:
			if strings.HasPrefix(arg, "-") || o.target != "" {
				return o, fmt.Errorf("未知参数：%s", arg)
			}
			o.target = arg
		}
	}
	return o, nil
}

func confirmed(in *bufio.Reader, out io.Writer, yes bool) bool {
	if yes {
		return true
	}
	fmt.Fprint(out, "确认执行？[y/N] ")
	answer, err := in.ReadString('\n')
	return err == nil && strings.EqualFold(strings.TrimSpace(answer), "y")
}

func candidate(m *install.Manager, target string) (*install.Candidate, error) {
	if install.IsGit(target) {
		return m.Acquire(target, catalog.Git)
	}
	f, err := registry.Load(m.RecordPath())
	if err != nil {
		return nil, err
	}
	if f.Find(target) != nil {
		return m.Existing(target)
	}
	if c, err := m.Builtin(target); err == nil {
		return c, nil
	}
	return m.Acquire(target, catalog.Local)
}

func command(m *install.Manager, args []string, in io.Reader, out, errorOut io.Writer) int {
	o, err := parseOptions(args[1:])
	if err != nil {
		fmt.Fprintln(errorOut, err)
		return 2
	}
	if err := m.CleanStaging(); err != nil {
		fmt.Fprintln(errorOut, err)
		return 1
	}
	reader := bufio.NewReader(in)
	fail := func(err error) int { fmt.Fprintln(errorOut, err); return 1 }
	switch args[0] {
	case "install":
		if o.target == "" {
			return fail(errors.New("请指定内置游戏 ID、本地目录或 git 地址"))
		}
		if install.IsGit(o.target) {
			fmt.Fprintln(out, "将执行 git clone --depth 1：", o.target)
			if !confirmed(reader, out, o.yes) {
				fmt.Fprintln(out, "已取消")
				return 0
			}
		}
		c, err := candidate(m, o.target)
		if err != nil {
			return fail(err)
		}
		defer c.Close(o.keep)
		lines, err := m.Plan(c)
		if err != nil {
			return fail(err)
		}
		for _, line := range lines {
			fmt.Fprintln(out, line)
		}
		if !confirmed(reader, out, o.yes) {
			fmt.Fprintln(out, "已取消")
			return 0
		}
		worker := *m
		worker.In = reader
		record, err := worker.Install(c)
		if err != nil {
			return fail(err)
		}
		fmt.Fprintln(out, "安装完成：", record.ID)
		return 0
	case "uninstall":
		if o.target == "" {
			return fail(errors.New("请指定已安装游戏 ID"))
		}
		fmt.Fprintln(out, "卸载", o.target, "，移除登记、运行环境与 git 克隆，保留内置／本地源码及游戏存档。")
		if !confirmed(reader, out, o.yes) {
			fmt.Fprintln(out, "已取消")
			return 0
		}
		if err := m.Uninstall(o.target); err != nil {
			return fail(err)
		}
		fmt.Fprintln(out, "卸载完成；存档保留在", m.Roots.GameData(o.target))
		return 0
	case "list":
		entries, err := m.Library()
		if err != nil {
			return fail(err)
		}
		for _, entry := range entries {
			status := "已安装"
			if entry.Issue != "" {
				status = "需要修复：" + entry.Issue
			}
			fmt.Fprintf(out, "%s\t%s\t%s\n", entry.ID, entry.Name, status)
		}
		if len(entries) == 0 {
			fmt.Fprintln(out, "尚未安装游戏；运行 tplay install tank 或打开安装游戏页面。")
		}
		return 0
	case "check":
		return check(m, o, out, errorOut)
	}
	return 2
}

func check(m *install.Manager, o options, out, errorOut io.Writer) int {
	f, err := registry.Load(m.RecordPath())
	if err != nil {
		fmt.Fprintln(errorOut, err)
		return 1
	}
	targets := []string{}
	if o.target != "" {
		targets = append(targets, o.target)
	} else {
		for _, r := range f.Games {
			targets = append(targets, r.ID)
		}
	}
	if len(targets) == 0 {
		fmt.Fprintln(out, "尚未安装游戏，没有检查对象。")
		return 0
	}
	code := 0
	for _, target := range targets {
		var entry catalog.Entry
		record := f.Find(target)
		if record != nil {
			checks, err := m.CheckRegistered(target, o.run)
			fmt.Fprintln(out, "检查：", target)
			for _, line := range install.Report(checks) {
				fmt.Fprintln(out, line)
			}
			if err != nil {
				fmt.Fprintln(errorOut, err)
			}
			if err != nil || install.Problem(checks) != "" {
				code = 1
			}
			continue
		}
		path := target
		if filepath.Base(path) != catalog.Manifest {
			path = filepath.Join(path, catalog.Manifest)
		}
		entry, err = catalog.Parse(path, catalog.Local, m.Host)
		checks := []registry.Check{}
		if err != nil {
			checks = append(checks, registry.Check{Name: "清单", Detail: err.Error()})
		} else {
			checks = m.Check(entry, "", o.run)
		}
		fmt.Fprintln(out, "检查：", target)
		for _, line := range install.Report(checks) {
			fmt.Fprintln(out, line)
		}
		problem := install.Problem(checks)
		if problem != "" {
			code = 1
		}
	}
	return code
}
