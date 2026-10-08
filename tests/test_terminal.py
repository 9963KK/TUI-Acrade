"""Exercise the actual curses process through a real pseudoterminal."""

import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

if os.name == "posix":
    import fcntl
    import pty
    import termios

ROOT = Path(__file__).resolve().parents[1]
BUILD = tempfile.TemporaryDirectory()
BINARY = Path(BUILD.name) / "tplay"


def build_platform():
    # 平台为 Go 程序：每次测试从源码构建一次，放在仓库之外；它不会从当前目录发现游戏，开发来源由测试显式指定。
    if not BINARY.exists():
        subprocess.run([shutil.which("go"), "build", "-o", str(BINARY), "./cmd/tplay"],
                       cwd=ROOT / "platform", check=True, capture_output=True)
    return BINARY


@unittest.skipUnless(os.name == "posix" and shutil.which("go"), "Requires a POSIX terminal and Go")
class TerminalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = build_platform()

    def setUp(self):
        self.master, self.slave = pty.openpty()
        self.original = termios.tcgetattr(self.slave)
        termios.tcsetwinsize(self.slave, (24, 80))
        self.data = tempfile.TemporaryDirectory()
        self.addCleanup(self.data.cleanup)
        self.process = None

    def tearDown(self):
        if self.process and self.process.poll() is None:
            self.process.kill()
            self.process.wait()
        os.close(self.master)
        os.close(self.slave)

    def start(self, controlling=False, **env):
        # 所有程序、存档与日志目录都隔离在临时目录中；XDG_DATA_HOME 同时隔离坦克旧存档的迁移来源。
        home = Path(self.data.name)
        # 不继承开发者本机的 TUI_ARCADE_* 设置，避免展位顺序或目录被改变。
        inherited = {k: v for k, v in os.environ.items() if not k.startswith("TUI_ARCADE_")}
        def controlling_terminal():
            # 像真实终端一样：新会话以这个伪终端为控制终端，Ctrl-C 才会作为 SIGINT 发给前台进程组。
            # 会话首进程退出后 macOS 会回收该终端，所以只有需要 Ctrl-C 的测试这样启动。
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

        self.process = subprocess.Popen(
            [str(self.binary)], stdin=self.slave, stdout=self.slave, stderr=self.slave, cwd=ROOT,
            start_new_session=not controlling, preexec_fn=controlling_terminal if controlling else None,
            env={**inherited, "TERM": "xterm-256color", "LC_ALL": "en_US.UTF-8", "TUI_ARCADE_HOME": str(home),
                 "XDG_DATA_HOME": str(home / "xdg"), "TUI_ARCADE_PYTHON": sys.executable,
                 # 测试用的平台构建在仓库之外，不会自动找到仓库的 games/，须显式指定开发来源。
                 "TUI_ARCADE_DEV_GAMES": str(ROOT / "games"), **env},
        )

    def expect(self, text):
        output = b""
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            if select.select([self.master], [], [], 0.1)[0]:
                chunk = os.read(self.master, 65536)
                self.answer(chunk)
                output += chunk
                if text.encode() in output:
                    return output
            if self.process.poll() is not None:
                break
        self.fail(f"Missing terminal text {text!r}; output: {output!r}")

    def answer(self, chunk):
        # 扮演终端：Bubble Tea 启动时询问背景色与光标位置（OSC 11 与 DSR），真实终端会立即回应，
        # 不回应时它要等 5 秒超时。
        if b"\x1b[6n" in chunk:
            os.write(self.master, b"\x1b]11;rgb:0000/0000/0000\x1b\\\x1b[1;1R")

    def drain(self):
        while select.select([self.master], [], [], 0.05)[0]:
            self.answer(os.read(self.master, 65536))

    def quit_and_check_terminal(self, modes=True):
        os.write(self.master, b"q")
        deadline = time.monotonic() + 4
        while self.process.poll() is None and time.monotonic() < deadline:
            if select.select([self.master], [], [], 0.1)[0]:
                os.read(self.master, 65536)
        self.assertEqual(self.process.poll(), 0)
        if not modes:
            return
        restored = termios.tcgetattr(self.slave)
        # macOS 内核可临时设置 PENDIN，表示待重显输入，并非模式变更。
        restored[3] &= ~getattr(termios, "PENDIN", 0)
        original = list(self.original)
        original[3] &= ~getattr(termios, "PENDIN", 0)
        self.assertEqual(restored, original)

    def test_lobby_launches_tank_in_same_terminal_and_returns(self):
        self.start()
        self.expect("终端游戏厅")
        # 排空首帧剩余字节；静止大厅不应再发送任何刷新数据。
        self.drain()
        self.assertFalse(select.select([self.master], [], [], 0.15)[0])
        os.write(self.master, b"\r")
        self.expect("TANK BATTLE")
        os.write(self.master, b"\r")
        os.write(self.master, b"p")
        self.expect("PAUSED")
        os.write(self.master, b"?")
        self.expect("WASD / ")
        os.write(self.master, b"\r")
        self.expect("PAUSED")
        termios.tcsetwinsize(self.slave, (18, 60))
        os.killpg(self.process.pid, signal.SIGWINCH)
        self.expect("窗口太小")
        termios.tcsetwinsize(self.slave, (24, 80))
        os.killpg(self.process.pid, signal.SIGWINCH)
        self.expect("PAUSED")
        os.write(self.master, b"q")
        self.expect("确认退出")
        os.write(self.master, b"\r")
        self.expect("终端游戏厅")
        self.quit_and_check_terminal()

    def install_echo(self):
        # 模拟已安装的预构建包：包内可执行入口，读取同一终端的输入后以非零状态退出。
        folder = Path(self.data.name) / "programs" / "echo"
        (folder / "bin").mkdir(parents=True)
        entry = folder / "bin" / "echo-game"
        entry.write_text('#!/bin/sh\necho "HELLO FROM $TUI_ARCADE_GAME_ID"\nread line\nexit 3\n')
        entry.chmod(0o755)
        (folder / "game.json").write_text(json.dumps({
            "manifest_version": 1, "id": "echo", "name": "回声", "version": "1.0.0", "authors": ["测试"],
            "launch": {"argv": ["./bin/echo-game"]}}), encoding="utf-8")

    def test_ctrl_c_goes_to_the_game_not_the_platform(self):
        self.install_echo()
        self.start(controlling=True)
        self.expect("回声")
        os.write(self.master, b"d")
        self.drain()
        os.write(self.master, b"\r")
        self.expect("HELLO FROM echo")
        # 游戏与平台同处前台进程组：Ctrl-C 结束游戏，平台留在原处且不提示异常。
        os.write(self.master, b"\x03")
        frame = self.expect("终端游戏厅")
        self.assertNotIn("游戏异常退出".encode(), frame)
        self.assertIsNone(self.process.poll())
        self.quit_and_check_terminal(modes=False)

    def test_installed_package_runs_in_same_terminal_and_failure_is_reported(self):
        self.install_echo()
        self.start()
        self.expect("回声")
        os.write(self.master, b"d")
        self.drain()
        os.write(self.master, b"\r")
        self.expect("HELLO FROM echo")
        os.write(self.master, b"\r")
        # 游戏退出后大厅整屏重画，并提示非零退出状态。
        frame = self.expect("游戏异常退出")
        self.assertIn("终端游戏厅".encode(), frame)
        os.write(self.master, b"\r")
        self.drain()
        self.quit_and_check_terminal()

    def test_sample_game_saves_into_assigned_data_dir(self):
        self.start(TUI_ARCADE_DEV_GAMES=os.pathsep.join((str(ROOT / "games"), str(ROOT / "templates"))))
        self.expect("猜数字")
        os.write(self.master, b"d")
        self.drain()
        os.write(self.master, b"\r")
        self.expect("1 到 100")
        # 输入非数字，回应确定，同时证明游戏在同一终端里读取了输入。
        os.write(self.master, b"abc\r")
        self.expect("请输入")
        os.write(self.master, b"q\r")
        self.expect("终端游戏厅")
        stats = Path(self.data.name) / "data" / "games" / "minimal-game" / "stats.json"
        self.assertEqual(json.loads(stats.read_text())["plays"], 1)
        self.quit_and_check_terminal()

    def test_working_directory_never_adds_games(self):
        # 装在仓库之外的平台即使在仓库目录里运行，也不加载这里的 games/（只认可执行文件所在的仓库）。
        self.start(TUI_ARCADE_DEV_GAMES="")
        self.expect("已收录 0 款")
        self.quit_and_check_terminal()

    def test_noninteractive_launch_has_clear_error(self):
        for command, cwd in (([str(self.binary)], ROOT), ([sys.executable, "-m", "tank_battle"], ROOT / "games" / "tank")):
            result = subprocess.run(command, capture_output=True, text=True, cwd=cwd, stdin=subprocess.DEVNULL)
            self.assertEqual(result.returncode, 1)
            self.assertIn("interactive terminal", result.stderr)


if __name__ == "__main__":
    unittest.main()
