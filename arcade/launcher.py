"""Hand the current terminal to a game process, then take it back (docs/game-integration.md §3)."""

import os
from pathlib import Path
import signal
import subprocess
import sys

from arcade_kit.paths import roots

from .catalog import PROTOCOLS

try:
    import termios
except ImportError:  # pragma: no cover - 非 POSIX 平台
    termios = None

# 游戏可能异常退出而未还原终端：复位颜色、关闭鼠标上报与括号粘贴、弹出 Kitty 键盘协议、显示光标、离开备用屏幕。
RESET = (b"\x1b[0m\x1b[?1000l\x1b[?1002l\x1b[?1003l\x1b[?1006l\x1b[?2004l"
         b"\x1b[<u\x1b[?25h\x1b[?1049l")
PLATFORM_KEYS = ("TUI_ARCADE_LAUNCHER", "TUI_ARCADE_PROTOCOL", "TUI_ARCADE_GAME_ID",
                 "TUI_ARCADE_DATA_DIR", "TUI_ARCADE_LOG_DIR")


def game_env(entry, env=None):
    """游戏进程的环境变量；外层遗留的同名变量一律以本次分配为准。"""
    env = {key: value for key, value in (os.environ if env is None else env).items() if key not in PLATFORM_KEYS}
    base = roots(env)
    env.update(TUI_ARCADE_LAUNCHER="1", TUI_ARCADE_PROTOCOL=str(max(PROTOCOLS)), TUI_ARCADE_GAME_ID=entry.id,
               TUI_ARCADE_LOG_DIR=str(base.logs / entry.id))
    if entry.managed_data:
        env["TUI_ARCADE_DATA_DIR"] = str(base.data / "games" / entry.id)
    return env


def prepare(entry, env=None):
    """交出终端之前的检查：入口存在、专属目录可用。返回 (环境变量, 错误信息)。"""
    env = game_env(entry, env)
    if entry.issue:
        return env, entry.issue
    if entry.argv[0].startswith("./") and not Path(entry.command()[0]).is_file():
        return env, "游戏入口缺失，请重新安装"
    try:
        for key in ("TUI_ARCADE_DATA_DIR", "TUI_ARCADE_LOG_DIR"):
            if key in env:
                Path(env[key]).mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return env, f"无法创建数据目录：{error.strerror or error}"
    return env, ""


def launch(entry, env, stdin=None, stdout=None):
    """在当前终端前台运行游戏，返回 (退出码, 错误信息)。调用前须先 prepare 并结束 curses。"""
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    saved = None
    if termios and stdin.isatty():
        saved = termios.tcgetattr(stdin.fileno())
    # 游戏与平台同属一个前台进程组，Ctrl-C、Ctrl-Z 与窗口变化都会直接送达游戏。
    # 不能用 SIG_IGN 忽略 Ctrl-C：被忽略的信号会跨 exec 继承给游戏；自定义处理函数在 exec 时恢复为默认行为。
    previous = signal.signal(signal.SIGINT, lambda *_: None)
    try:
        return subprocess.run(entry.command(), cwd=entry.cwd, env=env).returncode, None
    except OSError as error:
        return None, error.strerror or str(error)
    finally:
        signal.signal(signal.SIGINT, previous)
        if stdout.isatty():
            stdout.flush()
            os.write(stdout.fileno(), RESET)
        if saved is not None:
            # TCSAFLUSH 同时丢弃游戏退出时残留的按键，避免误触大厅操作。
            termios.tcsetattr(stdin.fileno(), termios.TCSAFLUSH, saved)
