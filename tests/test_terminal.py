"""Exercise the actual curses process through a real pseudoterminal."""

import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import time
import unittest

if os.name == "posix":
    import pty
    import termios

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "posix", "Requires a POSIX terminal")
class TerminalTests(unittest.TestCase):
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

    def start(self, **env):
        # 所有程序、存档与日志目录都隔离在临时目录中；XDG_DATA_HOME 同时隔离坦克旧存档的迁移来源。
        home = Path(self.data.name)
        self.process = subprocess.Popen(
            [sys.executable, "-m", "arcade"], stdin=self.slave, stdout=self.slave, stderr=self.slave,
            cwd=ROOT, start_new_session=True,
            env={**os.environ, "TERM": "xterm-256color", "LC_ALL": "en_US.UTF-8", "TUI_ARCADE_HOME": str(home),
                 "XDG_DATA_HOME": str(home / "xdg"), **env},
        )

    def expect(self, text):
        output = b""
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            if select.select([self.master], [], [], 0.1)[0]:
                output += os.read(self.master, 65536)
                if text.encode() in output:
                    return output
            if self.process.poll() is not None:
                break
        self.fail(f"Missing terminal text {text!r}; output: {output!r}")

    def drain(self):
        while select.select([self.master], [], [], 0.05)[0]:
            os.read(self.master, 65536)

    def quit_and_check_terminal(self):
        os.write(self.master, b"q")
        deadline = time.monotonic() + 4
        while self.process.poll() is None and time.monotonic() < deadline:
            if select.select([self.master], [], [], 0.1)[0]:
                os.read(self.master, 65536)
        self.assertEqual(self.process.poll(), 0)
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
        self.expect("结束本局")
        os.write(self.master, b"\r")
        self.expect("终端游戏厅")
        self.quit_and_check_terminal()

    def test_installed_package_runs_in_same_terminal_and_failure_is_reported(self):
        # 模拟已安装的预构建包：包内可执行入口，读取同一终端的输入后以非零状态退出。
        folder = Path(self.data.name) / "programs" / "echo"
        (folder / "bin").mkdir(parents=True)
        entry = folder / "bin" / "echo-game"
        entry.write_text('#!/bin/sh\necho "HELLO FROM $TUI_ARCADE_GAME_ID"\nread line\nexit 3\n')
        entry.chmod(0o755)
        (folder / "game.json").write_text(json.dumps({
            "manifest_version": 1, "id": "echo", "name": "回声", "version": "1.0.0", "authors": ["测试"],
            "launch": {"argv": ["./bin/echo-game"]}}), encoding="utf-8")
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
        self.start(TUI_ARCADE_DEV_GAMES=str(ROOT / "templates"))
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

    def test_noninteractive_launch_has_clear_error(self):
        for module, cwd in (("arcade", ROOT), ("tank_battle", ROOT / "games" / "tank")):
            result = subprocess.run([sys.executable, "-m", module], capture_output=True, text=True, cwd=cwd)
            self.assertEqual(result.returncode, 1)
            self.assertIn("interactive terminal", result.stderr)


if __name__ == "__main__":
    unittest.main()
