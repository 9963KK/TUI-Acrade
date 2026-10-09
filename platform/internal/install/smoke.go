package install

import (
	"bytes"
	"regexp"
	"strings"
	"sync"
	"time"
)

// 试运行时限见 docs/game-installation.md §4.2；测试可缩短等待时间。
var (
	firstOutput = 5 * time.Second
	settle      = time.Second
	exitWait    = 3 * time.Second
)

// SmokeResult 保存试运行结果。
type SmokeResult struct {
	OK      bool
	Skipped bool
	Detail  string
	// Output 为去掉转义序列后的最后一段输出，写入日志便于排查。
	Output string
}

var escapes = regexp.MustCompile(`\x1b(\[[0-9;?<>=]*[ -/]*[@-~]|\][^\x07\x1b]*(\x07|\x1b\\)|[@-_])`)

// transcript 收集输出并应答光标、背景色与设备属性查询，避免终端库等待应答。
type transcript struct {
	mu     sync.Mutex
	buf    bytes.Buffer
	first  chan struct{}
	seen   bool
	answer func([]byte)
}

func (t *transcript) Write(p []byte) (int, error) {
	t.mu.Lock()
	defer t.mu.Unlock()
	if t.buf.Len() < 1<<20 {
		t.buf.Write(p)
	}
	for _, reply := range []struct{ query, response string }{
		{"\x1b[6n", "\x1b[1;1R"},
		{"\x1b]11;?", "\x1b]11;rgb:1414/1414/1414\x1b\\"},
		{"\x1b[c", "\x1b[?62;22c"},
		{"\x1b[0c", "\x1b[?62;22c"},
	} {
		if bytes.Contains(p, []byte(reply.query)) && t.answer != nil {
			t.answer([]byte(reply.response))
		}
	}
	if !t.seen && len(bytes.TrimSpace([]byte(escapes.ReplaceAllString(string(p), "")))) > 0 {
		t.seen = true
		close(t.first)
	}
	return len(p), nil
}

func (t *transcript) tail() string {
	t.mu.Lock()
	defer t.mu.Unlock()
	text := escapes.ReplaceAllString(t.buf.String(), "")
	text = strings.Map(func(r rune) rune {
		if r == '\n' || r >= ' ' {
			return r
		}
		return ' '
	}, text)
	if len(text) > 2000 {
		text = text[len(text)-2000:]
	}
	return strings.TrimSpace(text)
}
