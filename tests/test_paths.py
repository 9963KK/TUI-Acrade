from pathlib import Path
import unittest

import support  # noqa: F401

from arcade_kit.paths import game_data_dir, game_log_dir, roots, system_name

HOME = Path("/home/u")


class PathTests(unittest.TestCase):
    def test_system_names(self):
        # Cygwin 属于 POSIX 环境，沿用 XDG 目录规则。
        self.assertEqual([system_name(p) for p in ("darwin", "linux", "win32", "cygwin")],
                         ["macos", "linux", "windows", "linux"])

    def test_linux_follows_xdg(self):
        base = roots({}, "linux", HOME)
        self.assertEqual(base.data, HOME / ".local/share/tui-arcade")
        self.assertEqual(base.programs, HOME / ".local/share/tui-arcade/programs")
        self.assertEqual(base.logs, HOME / ".local/state/tui-arcade/logs")
        self.assertEqual(base.cache, HOME / ".cache/tui-arcade")
        custom = roots({"XDG_DATA_HOME": "/d", "XDG_STATE_HOME": "/s", "XDG_CACHE_HOME": "/c"}, "linux", HOME)
        self.assertEqual((custom.data, custom.logs, custom.cache),
                         (Path("/d/tui-arcade"), Path("/s/tui-arcade/logs"), Path("/c/tui-arcade")))

    def test_macos_uses_library_unless_xdg_is_set(self):
        base = roots({}, "macos", HOME)
        self.assertEqual(base.data, HOME / "Library/Application Support/TUI Arcade")
        self.assertEqual(base.logs, HOME / "Library/Logs/TUI Arcade")
        self.assertEqual(base.cache, HOME / "Library/Caches/TUI Arcade")
        self.assertEqual(roots({"XDG_DATA_HOME": "/d"}, "macos", HOME).data, Path("/d/tui-arcade"))

    def test_windows_uses_local_app_data(self):
        base = roots({"LOCALAPPDATA": "/L"}, "windows", HOME)
        self.assertEqual(base.programs, Path("/L/Programs/tui-arcade"))
        self.assertEqual(base.data, Path("/L/tui-arcade"))
        self.assertEqual(base.logs, Path("/L/tui-arcade/logs"))

    def test_single_home_override_and_injected_dirs_win(self):
        env = {"TUI_ARCADE_HOME": "/t", "XDG_DATA_HOME": "/ignored"}
        self.assertEqual(game_data_dir("tank", env, system="linux"), Path("/t/data/games/tank"))
        self.assertEqual(game_log_dir("tank", env, system="linux"), Path("/t/logs/tank"))
        injected = {**env, "TUI_ARCADE_DATA_DIR": "/given", "TUI_ARCADE_LOG_DIR": "/logs"}
        self.assertEqual((game_data_dir("tank", injected), game_log_dir("tank", injected)),
                         (Path("/given"), Path("/logs")))


if __name__ == "__main__":
    unittest.main()
