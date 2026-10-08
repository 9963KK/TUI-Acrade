import curses
from pathlib import Path
import unittest
from unittest.mock import patch

from support import Screen, colors

from tank_battle.app import App
from tank_battle.levels import LEVELS


class TankAppTests(unittest.TestCase):
    def setUp(self):
        patch("tank_battle.app.read_best", return_value=0).start()
        self.save_mock = patch("tank_battle.app.save_record", return_value=(True, None)).start()
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
        self.save_mock.return_value = (True, Path("/data/scores.json.corrupt-17"))
        app = App(self.screen, {"TUI_ARCADE_LAUNCHER": "1"})
        app.game.result, app.game.reason = "lose", "HQ was destroyed."
        app.update(0)
        app._draw()
        self.assertIn("原记录无法读取，已另存为 scores.json.corrupt-17", self.screen.writes)
        self.save_mock.return_value = (True, None)
        app.handle(ord("r"))
        app.game.result, app.game.reason = "lose", "HQ was destroyed."
        app.update(0)
        app._draw()
        self.assertIn("本地最高分 00000", self.screen.writes)

    def test_failed_save_still_allows_leaving(self):
        self.save_mock.return_value = (False, None)
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

    def finish(self, result="win"):
        self.app.game.result = result
        self.app.game.reason = ("All enemy tanks eliminated!" if result == "win"
                                else "HQ was destroyed.")
        self.app.update(0)

    def test_level_selection_freezes_battle_and_cancel_preserves_progress(self):
        self.app.update(0.1)
        game = self.app.game
        elapsed, tiles = game.elapsed, dict(game.tiles)
        self.app.handle(ord("L"))
        self.app.handle(curses.KEY_DOWN)
        self.app.update(10)
        self.assertEqual(game.elapsed, elapsed)
        self.assertEqual(game.tiles, tiles)
        self.app.draw()
        self.assertIn(f" 选择关卡 2/{len(LEVELS)} ", self.screen.writes)
        self.app.handle(27)
        self.assertIs(self.app.game, game)
        self.assertFalse(self.app.selecting)
        self.app.update(0.1)
        self.assertGreater(game.elapsed, elapsed)

    def test_selector_bounds_and_start_selected_level(self):
        self.app.open_levels()
        self.app.handle(ord("w"))
        self.assertEqual(self.app.selection, 0)
        for _ in range(10):
            self.app.handle(ord("s"))
        self.assertEqual(self.app.selection, len(LEVELS) - 1)
        self.app.handle(13)
        self.assertEqual(self.app.game.level_number, len(LEVELS))
        self.assertFalse(self.app.selecting)
        self.assertEqual(self.app.game.TARGET, LEVELS[-1].target)
        self.assertEqual(self.app.game.elapsed, 0)
        self.assertEqual(self.app.game.lives, 3)

    def test_cancelling_selector_preserves_pause(self):
        self.app.handle(ord("p"))
        self.app.handle(ord("l"))
        self.app.handle(ord("q"))
        self.assertTrue(self.app.game.paused)
        self.assertTrue(self.app.running)
        self.assertFalse(self.app.selecting)

    def test_win_advances_and_retry_stays_on_current_level(self):
        for number in range(1, len(LEVELS)):
            self.app.start(number)
            self.app.game.tiles.clear()
            self.finish()
            self.app.handle(ord("r"))
            self.assertEqual(self.app.game.level_number, number)
            self.assertTrue(self.app.game.tiles)
            self.finish()
            self.app.handle(10)
            self.assertEqual(self.app.game.level_number, number + 1)
            self.assertIsNone(self.app.game.result)
            self.assertFalse(self.app.saved)
            self.assertEqual(self.app.game.score, 0)
            self.assertEqual(self.app.game.lives, 3)

    def test_defeat_retries_current_level(self):
        self.app.start(2)
        self.finish("lose")
        self.app.handle(10)
        self.assertEqual(self.app.game.level_number, 2)
        self.assertIsNone(self.app.game.result)

    def test_final_level_returns_to_selector_and_can_be_replayed(self):
        self.app.start(len(LEVELS))
        self.finish()
        self.app.draw()
        self.assertIn(" 最终关完成 ", self.screen.writes)
        self.app.handle(10)
        self.assertTrue(self.app.selecting)
        self.assertEqual(self.app.selection, len(LEVELS) - 1)
        self.app.handle(27)
        self.assertEqual(self.app.game.result, "win")
        self.app.handle(ord("r"))
        self.assertEqual(self.app.game.level_number, len(LEVELS))
        self.assertIsNone(self.app.game.result)

    def test_finished_game_can_select_any_level_without_losing_best(self):
        self.app.game.kills = 12
        self.finish()
        best = self.app.best
        self.app.handle(ord("l"))
        self.app.handle(ord("s"))
        self.app.handle(10)
        self.assertEqual(self.app.game.level_number, 2)
        self.assertEqual(self.app.best, best)
        self.save_mock.assert_called_once()

    def test_selector_frames_are_static_and_keys_do_not_control_tank(self):
        self.app.open_levels()
        self.app.handle(ord("f"))
        self.app.handle(ord(" "))
        self.assertFalse(self.app.game.auto_fire)
        self.assertFalse(self.app.game.bullets)
        self.assertTrue(self.app.draw())
        self.app.update(10)
        self.assertFalse(self.app.draw())
        self.app.handle(curses.KEY_RIGHT)
        self.assertTrue(self.app.draw())

    def test_every_level_renders_target_help_and_results(self):
        for number, level in enumerate(LEVELS, 1):
            with self.subTest(number=number):
                self.app.start(number)
                self.app.draw()
                self.assertIn(f"第 {number}/{len(LEVELS)} 关  {level.name}", self.screen.writes)
                self.app.handle(ord("?"))
                self.app.draw()
                self.assertIn(f"消灭 {level.target} 辆敌军或守满 3 分钟获胜。", self.screen.writes)
                self.app.handle(27)
                self.app.game.kills = level.target
                self.finish()
                self.app.draw()
                self.assertIn(f"击毁 {level.target}/{level.target}     得分 {self.app.game.score:05d}",
                              self.screen.writes)

    def test_all_level_dialogs_fit_smallest_supported_window(self):
        for number in range(1, len(LEVELS) + 1):
            for height, width in ((24, 80), (40, 120)):
                self.screen.height, self.screen.width = height, width
                self.app.start(number)
                for rich in (False, True):
                    with colors():
                        self.app.theme.setup({} if rich else {"ARCADE_ASCII": "1"})
                        self.app.open_levels()
                        self.app.draw()
                        ox, oy = self.app.origin()
                        borders = [(y, x) for y, x, text in self.screen.positions if text.startswith(("╭", "+"))]
                        self.assertTrue(all(oy + 2 <= y <= oy + 22 and x + 54 <= ox + 61
                                            for y, x in borders))
                        self.app.handle(27)
                        self.app.help = True
                        self.app.draw()
                        self.app.help = False
                        self.finish()
                        self.app.draw()

    def test_selector_scrolls_when_more_levels_are_added(self):
        expanded = LEVELS * 4
        with patch("tank_battle.app.LEVELS", expanded):
            self.app.open_levels()
            for _ in expanded:
                self.app.handle(curses.KEY_DOWN)
            self.assertEqual(self.app.selection, len(expanded) - 1)
            self.app.draw()
            self.assertIn(f" 选择关卡 {len(expanded)}/{len(expanded)} ", self.screen.writes)
            self.assertTrue(any(text.startswith(f"> {len(expanded):02}") for text in self.screen.writes))
            self.assertFalse(any(text.startswith("  01") for text in self.screen.writes))
            self.assertTrue(all(0 <= y < 24 for y, _, _ in self.screen.positions))


if __name__ == "__main__":
    unittest.main()
