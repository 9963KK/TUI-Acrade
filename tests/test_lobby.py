import curses
from dataclasses import replace
import signal
import unittest
from unittest.mock import Mock, patch

from support import Screen, colors

from arcade import catalog
from arcade.ui import App
from arcade_kit.canvas import cell_width, fit

TANK = catalog.parse(catalog.ROOT / "games" / "tank" / catalog.MANIFEST)


class LobbyTests(unittest.TestCase):
    def setUp(self):
        self.screen = Screen()
        self.launcher = Mock(return_value=(0, None))
        self.app = App(self.screen, [TANK], self.launcher)
        self.flush = patch("arcade_kit.presentation.curses.doupdate").start()
        self.addCleanup(patch.stopall)
        self.app.presenter.flush = self.flush

    def test_unicode_clipping(self):
        self.assertEqual(cell_width("坦克 A"), 6)
        self.assertEqual(fit("坦克 ABC", 5), "坦克 ")
        self.assertEqual(cell_width("é"), 1)

    def test_lists_manifest_games_and_launches_selection(self):
        self.app.draw()
        for text in ("终端游戏厅", "坦克大战", "TANK BATTLE", " 3 分钟 ", "开发来源 · v0.2.0"):
            self.assertIn(text, self.screen.writes)
        self.app.handle(10)
        self.launcher.assert_called_once_with(TANK)
        self.assertIsNone(self.app.notice)
        self.assertTrue(self.app.running)
        self.app.handle(ord("q"))
        self.assertFalse(self.app.running)

    def test_gallery_moves_in_grid_and_ignores_empty_slots(self):
        self.app.handle(curses.KEY_UP)
        self.app.handle(curses.KEY_LEFT)
        self.assertEqual(self.app.selection, 0)
        self.app.handle(curses.KEY_RIGHT)
        self.app.handle(ord("s"))
        self.assertEqual(self.app.selection, 4)
        self.app.handle(curses.KEY_DOWN)
        self.app.handle(ord("d"))
        self.app.handle(ord("d"))
        self.assertEqual(self.app.selection, 5)
        self.app.draw()
        self.assertIn("06 号展位", self.screen.writes)
        self.app.handle(10)
        self.launcher.assert_not_called()
        self.app.selection = 2
        self.app.handle(curses.KEY_RIGHT)
        self.assertEqual(self.app.selection, 2)
        self.app.selection = 3
        self.app.handle(curses.KEY_LEFT)
        self.assertEqual(self.app.selection, 3)

    def test_more_games_than_a_page_are_paged(self):
        games = [replace(TANK, id=f"g{i}", name=f"游戏{i}") for i in range(7)]
        app = App(self.screen, games, self.launcher)
        self.assertEqual(app.slots, 12)
        app._draw()
        self.assertIn("已收录 7 款 · 第 1/2 页", self.screen.writes)
        for _ in range(2):
            app.handle(curses.KEY_DOWN)
        self.assertEqual(app.selection, 6)
        app._draw()
        self.assertIn("游戏6", self.screen.writes)
        self.assertNotIn("游戏0", self.screen.writes)

    def test_too_small_window_blocks_launch_with_notice(self):
        app = App(self.screen, [replace(TANK, terminal=catalog.Terminal(100, 30))], self.launcher)
        app._draw()
        self.assertIn("需要 100 x 30 窗口", self.screen.writes)
        app.handle(10)
        self.launcher.assert_not_called()
        self.assertEqual(app.notice[0], "窗口太小")
        app.handle(ord("s"))
        self.assertEqual(app.selection, 0)
        app.handle(10)
        self.assertIsNone(app.notice)

    def test_blocked_games_explain_why_and_bad_manifests_are_counted(self):
        blocked = replace(TANK, issue="需要更新平台（清单协议 2）", network="required")
        app = App(self.screen, [blocked], self.launcher, problems=[("x/game.json", "bad")])
        app._draw()
        self.assertIn("需要更新平台（清单协议 2）", self.screen.writes)
        self.assertIn(" 需要联网 ", self.screen.writes)
        self.assertIn("已收录 1 款 · 1 份清单无效", self.screen.writes)
        app.handle(10)
        self.launcher.assert_not_called()
        self.assertEqual(app.notice[0], "无法启动")

    def test_capability_hints_do_not_block_launch(self):
        wants = replace(TANK, terminal=catalog.Terminal(color="256", unicode="required"))
        app = App(self.screen, [wants], self.launcher)
        app._draw()
        self.assertIn("建议使用 256 色终端", self.screen.writes)
        with colors():
            app.theme.setup({})
            app._draw()
        self.assertIn("开发来源 · v0.2.0", self.screen.writes)
        with patch.dict("os.environ", {"COLORTERM": ""}):
            app.games = [replace(TANK, terminal=catalog.Terminal(color="truecolor"))]
            app._draw()
        self.assertIn("建议使用真彩色终端", self.screen.writes)
        app.handle(10)
        self.launcher.assert_called_once()

    def test_exit_status_and_launch_errors_are_reported(self):
        for result, title in (((3, None), "游戏异常退出"), ((None, "No such file"), "无法启动"),
                              ((-signal.SIGINT, None), None), ((130, None), None)):
            self.launcher.return_value = result
            self.app.handle(10)
            self.assertEqual(self.app.notice and self.app.notice[0], title)
            self.app.draw()
            self.app.handle(27)
            self.assertIsNone(self.app.notice)

    def test_run_game_hands_over_terminal_and_forces_full_redraw(self):
        app = App(self.screen, [TANK])
        app.presenter.flush = self.flush
        app.draw()
        with patch("arcade.ui.curses.endwin") as endwin, patch("arcade.ui.launch", return_value=(0, None)) as run, \
             patch("arcade.ui.prepare", return_value=({"E": "1"}, "")), \
             patch("arcade.ui.curses.is_term_resized", return_value=False):
            app.handle(10)
        endwin.assert_called_once()
        run.assert_called_once_with(TANK, {"E": "1"})
        self.assertTrue(app.draw())
        # 检查未通过时不交出终端，直接在大厅提示。
        with patch("arcade.ui.curses.endwin") as endwin, patch("arcade.ui.prepare", return_value=({}, "入口缺失")):
            app.handle(10)
        endwin.assert_not_called()
        self.assertEqual(app.notice[1][0], "坦克大战：入口缺失")

    def test_static_lobby_is_not_redrawn(self):
        self.assertTrue(self.app.draw())
        self.assertFalse(self.app.draw())
        self.app.handle(ord("?"))
        self.assertTrue(self.app.draw())
        self.assertIn("游戏厅说明", " ".join(self.screen.writes))
        self.app.handle(27)
        self.assertTrue(self.app.draw())
        self.assertEqual(self.flush.call_count, 3)

    def test_covers_render_rich_or_ascii_without_overflow(self):
        for rich in (False, True):
            with colors():
                self.app.theme.setup({} if rich else {"ARCADE_ASCII": "1"})
                self.assertEqual(self.app.rich, rich)
                for height, width in ((1, 1), (10, 30), (24, 80), (40, 120)):
                    self.screen.height, self.screen.width = height, width
                    self.app._draw()
                    self.app.help = True
                    self.app._draw()
                    self.app.help = False
                self.screen.height, self.screen.width = 24, 80
                self.app._draw()
            self.assertIn("▟▙" if rich else "^P", self.screen.writes)
            self.assertEqual("─" * 78 in self.screen.writes, rich)


if __name__ == "__main__":
    unittest.main()
