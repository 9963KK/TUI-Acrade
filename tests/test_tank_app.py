import curses
import unittest
from unittest.mock import patch

from support import Screen, colors

from tank_battle.app import App


class TankAppTests(unittest.TestCase):
    def setUp(self):
        patch("tank_battle.app.read_best", return_value=0).start()
        self.corrupt = patch("tank_battle.app.is_corrupt", return_value=False).start()
        self.save_mock = patch("tank_battle.app.save_best", return_value=True).start()
        self.flush_mock = patch("arcade_kit.presentation.curses.doupdate").start()
        self.addCleanup(patch.stopall)
        self.screen = Screen()
        self.app = App(self.screen, {"TUI_ARCADE_LAUNCHER": "1"})
        self.app.presenter.flush = self.flush_mock

    def test_play_help_pause_and_leave(self):
        self.app.draw()
        self.assertIn("TANK BATTLE", self.screen.writes)
        self.app.handle(ord("A"))
        self.assertEqual(self.app.game.player.x, 11)
        self.app.handle(ord("f"))
        self.assertTrue(self.app.game.auto_fire)
        self.app.handle(ord("?"))
        self.app.update(10)
        self.assertEqual(self.app.game.elapsed, 0)
        self.app.draw()
        self.app.handle(27)
        self.app.handle(ord("p"))
        self.app.update(10)
        self.assertTrue(self.app.game.paused)
        self.app.draw()
        self.app.handle(27)
        self.app.handle(ord("q"))
        self.app.update(10)
        self.assertEqual(self.app.game.elapsed, 0)
        self.app.draw()
        self.assertIn("结束本局？当前战绩不会保存。", self.screen.writes)
        self.app.handle(27)
        self.assertFalse(self.app.confirm_leave)
        self.assertTrue(self.app.running)
        self.app.handle(ord("q"))
        self.app.handle(10)
        self.assertFalse(self.app.running)

    def test_leave_wording_depends_on_launcher(self):
        self.app.draw()
        self.assertIn("返回", self.screen.writes)
        standalone = App(self.screen, {})
        standalone.draw()
        self.assertIn("退出", self.screen.writes)

    def test_dialogs_stay_inside_field(self):
        self.app.help = True
        self.app.draw()
        border = [x for y, x, text in self.screen.positions if text.startswith(("╭", "+"))]
        self.assertTrue(border and max(border) + 54 <= 61)

    def test_ascii_hud_shows_lost_lives(self):
        self.app.game.lives = 1
        self.app.draw()
        self.assertEqual(self.screen.writes.count(". "), 2)
        self.assertNotIn("▟▙", self.screen.writes)

    def test_rich_glyphs_render_without_overflow(self):
        with colors():
            self.app.theme.setup({})
            self.assertTrue(self.app.rich)
            for height, width in ((24, 80), (40, 120)):
                self.screen.height, self.screen.width = height, width
                self.app.start()
                self.app.game.advance(12)
                self.app._draw()
                self.assertIn("HQ", self.screen.writes)
                self.assertIn("▝▀", self.screen.writes)
                self.assertNotIn("##", self.screen.writes)

    def test_water_animates_only_while_time_runs(self):
        self.app.draw()
        self.app.game.advance(0.5)
        self.assertTrue(self.app.draw())
        self.app.handle(ord("p"))
        self.app.draw()
        self.app.update(5)
        self.assertFalse(self.app.draw())

    def test_resize_pauses_and_quit_is_accessible(self):
        self.screen.width = 30
        self.app.update(2)
        self.app.draw()
        self.assertTrue(self.app.game.paused)
        self.app.handle(ord("p"))
        self.assertTrue(self.app.game.paused)
        self.screen.width = 80
        self.app.update(2)
        self.assertEqual(self.app.game.elapsed, 0)
        self.app.handle(ord("p"))
        self.app.update(0.1)
        self.assertGreater(self.app.game.elapsed, 0)
        self.screen.width = 20
        self.app.handle(ord("q"))
        self.assertFalse(self.app.running)

    def test_result_saved_once_and_restart(self):
        self.app.game.elapsed = 179.95
        self.app.update(0.1)
        self.app.update(1)
        self.assertEqual(self.app.game.result, "win")
        self.save_mock.assert_called_once()
        self.app.draw()
        self.app.handle(ord("r"))
        self.assertIsNone(self.app.game.result)
        self.assertEqual(self.app.game.elapsed, 0)

    def test_unreadable_record_is_reported_after_saving(self):
        self.corrupt.return_value = True
        app = App(self.screen, {"TUI_ARCADE_LAUNCHER": "1"})
        app.game.result, app.game.reason = "lose", "HQ was destroyed."
        app.update(0)
        app._draw()
        self.assertIn("原记录无法读取，已另存为 scores.json.corrupt", self.screen.writes)
        app.handle(ord("r"))
        app.game.result, app.game.reason = "lose", "HQ was destroyed."
        app.update(0)
        app._draw()
        self.assertIn("本地最高分 00000", self.screen.writes)

    def test_failed_save_still_allows_leaving(self):
        self.save_mock.return_value = False
        self.app.game.result = "lose"
        self.app.game.reason = "HQ was destroyed."
        self.app.update(0)
        self.assertTrue(self.app.save_failed)
        self.app.draw()
        self.app.handle(ord("q"))
        self.assertFalse(self.app.running)

    def test_render_all_sizes_without_overflow(self):
        for height, width in ((1, 1), (10, 30), (24, 80), (40, 120)):
            self.screen.height, self.screen.width = height, width
            self.app.start()
            self.app.update(1)
            self.app.draw()
            self.app.help = True
            self.app.draw()

    def test_paused_frames_are_not_redrawn(self):
        self.app.handle(ord("p"))
        self.assertTrue(self.app.draw())
        self.app.update(10)
        self.assertFalse(self.app.draw())
        self.assertEqual(self.flush_mock.call_count, 1)

    def test_visible_changes_invalidate_frame_but_cooldowns_do_not(self):
        self.app.draw()
        self.app.game.player.cooldown = 0.2
        self.assertFalse(self.app.draw())
        self.app.game.player.x -= 1
        self.assertTrue(self.app.draw())
        self.app.game.tiles.pop(next(iter(self.app.game.tiles)))
        self.assertTrue(self.app.draw())
        self.app.game.elapsed = 1
        self.assertTrue(self.app.draw())
        self.screen.width = 100
        self.assertTrue(self.app.draw())
        self.app.help = True
        self.assertTrue(self.app.draw())

    def test_background_only_change_can_restore_a_closed_modal(self):
        self.app.help = True
        self.app.draw()
        self.app.help = False
        self.assertTrue(self.app.draw())


if __name__ == "__main__":
    unittest.main()
