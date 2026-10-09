package install

// Smoke 在 Windows 上尚未接入 ConPTY，检查报告注明未试运行。
func Smoke(argv, env []string, dir string, columns, rows int) SmokeResult {
	return SmokeResult{OK: true, Skipped: true, Detail: "Windows 暂不支持试运行"}
}
