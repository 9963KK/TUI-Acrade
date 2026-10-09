package install

import (
	"crypto/sha256"
	"encoding/hex"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
)

// skipped 排除历史记录、缓存与本地环境，避免这些变化触发游戏检查。
var skipped = map[string]bool{".git": true, "__pycache__": true, ".venv": true, "venv": true, "node_modules": true,
	".mypy_cache": true, ".pytest_cache": true, ".ruff_cache": true}

// Fingerprint 对文件相对路径与内容计算摘要，识别 git pull 或源码编辑。
func Fingerprint(root string) (string, error) {
	hash := sha256.New()
	err := filepath.WalkDir(root, func(path string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.IsDir() {
			if path != root && skipped[entry.Name()] {
				return filepath.SkipDir
			}
			return nil
		}
		if strings.HasSuffix(entry.Name(), ".pyc") || !entry.Type().IsRegular() {
			return nil
		}
		relative, _ := filepath.Rel(root, path)
		io.WriteString(hash, filepath.ToSlash(relative)+"\x00")
		file, err := os.Open(path)
		if err != nil {
			return err
		}
		defer file.Close()
		_, err = io.Copy(hash, file)
		io.WriteString(hash, "\x00")
		return err
	})
	if err != nil {
		return "", err
	}
	return hex.EncodeToString(hash.Sum(nil)), nil
}
