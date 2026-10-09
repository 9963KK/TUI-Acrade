"""Exercise the standalone tank game in a real terminal, without building the Go platform."""

import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time
import unittest

import support  # noqa: F401
from tank_battle.levels import LEVELS

if os.name == "posix":
    import pty
    import termios

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "posix", "Requires a POSIX terminal")
class TankTerminalTests(unittest.TestCase):
    def setUp(self):
        self.master, self.slave = pty.openpty()
        termios.tcsetwinsize(self.slave, (24, 80))
        self.original = termios.tcgetattr(self.slave)
        self.data = tempfile.TemporaryDirectory()
        self.addCleanup(self.data.cleanup)
        self.process = None

    def tearDown(self):
        if self.process and self.process.poll() is None:
            self.process.kill()
            self.process.wait()
        os.close(self.master)
        os.close(self.slave)

    def start(self, script=None, ascii=False):
        inherited = {k: v for k, v in os.environ.items() if not k.startswith(("TUI_ARCADE_", "ARCADE_"))}
        self.process = subprocess.Popen(
            [sys.executable, "-c", script] if script else [sys.executable, "-m", "tank_battle"],
            stdin=self.slave, stdout=self.slave, stderr=self.slave, cwd=ROOT / "games/tank",
            start_new_session=True,
            env={**inherited, "TERM": "xterm-256color", "LC_ALL": "en_US.UTF-8",
                 "TUI_ARCADE_HOME": self.data.name, "XDG_DATA_HOME": self.data.name,
                 "ARCADE_ASCII": "1" if ascii else "0"},
        )

    def expect(self, text):
        output = b""
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            if select.select([self.master], [], [], 0.1)[0]:
                output += os.read(self.master, 65536)
                if text.encode() in output:
                    return
            if self.process.poll() is not None:
                break
        self.fail(f"Missing terminal text {text!r}; output: {output!r}")

    def send(self, keys):
        # 排空上一帧，但密集战斗持续输出时也要及时发送按键。
        deadline = time.monotonic() + 0.25
        while time.monotonic() < deadline and select.select([self.master], [], [], 0.05)[0]:
            os.read(self.master, 65536)
        os.write(self.master, keys.encode())

    def quit(self):
        self.send("q")
        self.expect("确认退出")
        self.send("\r")
        # 退出时仍会重绘并恢复终端；持续读取，避免输出管道满后阻塞子进程。
        deadline = time.monotonic() + 4
        while self.process.poll() is None and time.monotonic() < deadline:
            if select.select([self.master], [], [], 0.1)[0]:
                os.read(self.master, 65536)
        self.assertEqual(self.process.returncode, 0)
        restored = termios.tcgetattr(self.slave)
        restored[3] &= ~getattr(termios, "PENDIN", 0)
        original = list(self.original)
        original[3] &= ~getattr(termios, "PENDIN", 0)
        self.assertEqual(restored, original)

    def test_select_second_and_third_levels_and_restore_terminal(self):
        self.start()
        self.expect("1 PLAYER")
        self.send("l")
        self.expect("选择关卡")
        self.send("s\r")
        self.send("p")
        self.expect("第 02 关")
        self.send("p")
        self.send("l")
        self.expect("选择关卡")
        self.send("s\r")
        self.expect("确认重新开始")
        self.send("\r")
        self.send("p")
        self.expect("第 03 关")
        # 暂停中返回游戏自己的主菜单，继续当前战役仍回到第三关。
        self.send("sss\r")
        self.expect("1 PLAYER")
        self.send("s\r")
        self.send("p")
        self.expect("第 03 关")
        self.quit()
        self.assertFalse(list(Path(self.data.name).rglob("scores.json")))

    def test_ascii_selection_and_help_work(self):
        self.start(ascii=True)
        self.expect("1 PLAYER")
        self.send("l")
        self.expect("选择关卡")
        self.send("ss\r")
        self.send("?")
        self.expect("每关消灭 20 辆敌军")
        self.send("\r")
        self.send("p")
        self.expect("第 03 关")
        self.send("s\r")
        self.expect("确认重新开始")
        self.send("\r")
        self.send("p")
        self.expect("第 03 关")
        self.quit()

    def test_victory_can_advance_to_next_level_in_real_terminal(self):
        # 让真实规则在首帧结算，验证终端中的下一关操作与最高分保存。
        script = (
            "import tank_battle.__main__\n"
            "import curses\n"
            "from tank_battle.app import App\n"
            "from tank_battle.rules import Tank\n"
            "def play(screen):\n"
            "    app = App(screen)\n"
            "    app.start()\n"
            "    app.game.tiles.clear()\n"
            "    app.game.kills = 19\n"
            "    app.game.enemies = [Tank(16, 44)]\n"
            "    app.handle(ord('j'))\n"
            "    app.run()\n"
            "curses.wrapper(play)\n"
        )
        self.start(script)
        self.expect("任务完成")
        self.send("\r")
        self.send("p")
        self.expect("第 02 关")
        self.quit()
        self.assertEqual(len(list(Path(self.data.name).rglob("scores.json"))), 1)

    def test_scroll_to_final_level_and_return_to_first(self):
        self.start()
        self.expect("1 PLAYER")
        self.send("l")
        self.expect("选择关卡")
        self.send("s" * (len(LEVELS) - 1))
        # curses 差分输出不保证包含完整选中行；进入后从暂停标题验证实际关卡。
        self.send("\r")
        self.send("p")
        self.expect("第 35 关")
        self.send("p")
        self.send("?")
        self.expect(f"消灭 {LEVELS[-1].target} 辆敌军")
        self.send("\r")
        self.send("l")
        self.expect("选择关卡")
        self.send("w" * (len(LEVELS) - 1))
        self.send("\r")
        self.expect("确认重新开始")
        self.send("\r")
        self.send("p")
        self.expect("第 01 关")
        self.quit()


if __name__ == "__main__":
    unittest.main()
