import curses
from pathlib import Path
import unittest
from unittest.mock import patch

from support import Screen, colors
from tank_battle.app import App
from tank_battle.glyphs import Glyphs
from tank_battle.levels import LEVELS
from tank_battle.rules import Bullet, Direction, PowerUp, Tank


class TankAppTests(unittest.TestCase):
    def setUp(self):
        patch("tank_battle.app.read_best", return_value=0).start()
        self.save_mock = patch("tank_battle.app.save_record", return_value=(True, None)).start()
        self.flush_mock = patch("arcade_kit.presentation.curses.doupdate").start()
        self.addCleanup(patch.stopall)
        self.screen = Screen()
        self.app = App(self.screen, {"TUI_ARCADE_LAUNCHER": "1"})
        self.app.presenter.flush = self.flush_mock

    def choose(self, action):
        items = self.app.menu_items()
        self.app.menu_index = next(i for i, (_, item) in enumerate(items) if item == action)
        self.app.handle(10)

    def finish(self, result="win"):
        self.app.game.result = result
        self.app.game.reason = "All enemy tanks eliminated!" if result == "win" else "HQ was destroyed."
        self.app.update(0)

    def test_start_on_game_title_and_launcher_exit_label(self):
        self.assertEqual(self.app.mode, "title")
        self.assertFalse(self.app.has_campaign)
        self.app.update(100)
        self.assertEqual(self.app.game.elapsed, 0)
        self.app.draw()
        self.assertIn(" BATTLE CITY / 主菜单 ", self.screen.writes)
        self.assertTrue(any("退出并返回大厅" in line for line in self.screen.writes))
        standalone = App(self.screen, {})
        standalone.draw()
        self.assertTrue(any("退出游戏" in line for line in self.screen.writes))

    def test_title_menu_navigation_wraps_and_starts_game(self):
        self.app.handle(ord("W"))
        self.assertEqual(self.app.menu_index, len(self.app.menu_items()) - 1)
        self.app.handle(ord("s"))
        self.assertEqual(self.app.menu_index, 0)
        self.app.handle(ord("j"))
        self.assertEqual(self.app.mode, "playing")
        self.assertTrue(self.app.has_campaign)
        self.app.handle(ord("A"))
        self.assertEqual(self.app.game.player.x, 14)
        self.app.handle(ord("f"))
        self.assertTrue(self.app.game.auto_fire)

    def test_all_modal_screens_freeze_battle_and_cancel_restores_it(self):
        for key, mode in ((ord("p"), "pause"), (ord("?"), "help"), (ord("l"), "select"), (ord("q"), "confirm")):
            self.app.start()
            self.app.update(0.1)
            game = self.app.game
            elapsed = game.elapsed
            self.app.handle(key)
            self.assertEqual(self.app.mode, mode)
            self.app.update(10)
            self.assertEqual(game.elapsed, elapsed)
            self.app.draw()
            self.app.handle(27)
            self.assertEqual(self.app.mode, "playing")
            self.assertIs(self.app.game, game)

    def test_pause_menu_continue_retry_title_help_and_exit(self):
        self.app.start(4)
        self.app.handle(ord("p"))
        self.choose("help")
        self.app.draw()
        self.app.handle(10)
        self.assertEqual(self.app.mode, "pause")
        self.choose("resume")
        self.assertEqual(self.app.mode, "playing")
        self.app.handle(ord("p"))
        self.choose("retry")
        self.assertEqual(self.app.mode, "confirm")
        self.app.handle(ord("n"))
        self.assertEqual(self.app.mode, "pause")
        self.choose("retry")
        self.app.handle(ord("y"))
        self.assertEqual(self.app.game.level_number, 4)
        self.app.handle(ord("p"))
        game = self.app.game
        self.choose("title")
        self.assertEqual(self.app.mode, "title")
        self.choose("resume")
        self.assertIs(self.app.game, game)
        self.assertFalse(game.paused)
        self.app.handle(ord("q"))
        self.app.draw()
        self.assertIn("结束游戏？已结算的最高分会保留。", self.screen.writes)
        self.app.handle(10)
        self.assertFalse(self.app.running)

    def test_new_campaign_confirmation_and_cancel(self):
        self.app.start(10)
        game = self.app.game
        self.app.title()
        self.choose("new")
        self.app.handle(27)
        self.assertIs(self.app.game, game)
        self.choose("new")
        self.app.handle(10)
        self.assertEqual(self.app.game.level_number, 1)
        self.assertEqual(self.app.checkpoint, (3, 0, 0))

    def test_select_first_and_last_page_bounds(self):
        self.app.open_levels()
        self.app.handle(curses.KEY_UP)
        self.assertEqual(self.app.selection, 0)
        self.app.handle(curses.KEY_NPAGE)
        self.assertEqual(self.app.selection, 5)
        self.app.handle(curses.KEY_END)
        self.assertEqual(self.app.selection, 34)
        self.app.handle(curses.KEY_DOWN)
        self.app.draw()
        self.assertIn("> 35  经典关卡 35    敌军 20", self.screen.writes)
        self.app.handle(curses.KEY_PPAGE)
        self.assertEqual(self.app.selection, 29)
        self.app.handle(curses.KEY_HOME)
        self.app.handle(curses.KEY_DOWN)
        self.app.handle(13)
        self.assertEqual(self.app.game.level_number, 2)
        self.assertEqual(self.app.mode, "playing")

    def test_selection_requires_confirmation_during_existing_campaign(self):
        self.app.start(12)
        game = self.app.game
        self.app.open_levels()
        self.app.handle(curses.KEY_END)
        self.app.handle(10)
        self.app.handle(27)
        self.assertEqual(self.app.mode, "select")
        self.assertIs(self.app.game, game)
        self.app.handle(27)
        self.assertEqual(self.app.mode, "playing")
        self.app.open_levels()
        self.app.handle(curses.KEY_END)
        self.app.handle(10)
        self.app.handle(10)
        self.assertEqual(self.app.game.level_number, 35)
        self.assertEqual(self.app.checkpoint, (3, 0, 0))

    def test_retry_restores_stage_checkpoint_and_does_not_duplicate_score(self):
        self.app.start(3, checkpoint=(2, 4200, 1))
        self.app.game.lives = 1
        self.app.game.points = 5400
        self.app.game.power = 3
        self.finish()
        self.app.handle(ord("r"))
        self.assertEqual((self.app.game.lives, self.app.game.score, self.app.game.power), (2, 4200, 1))
        self.assertEqual(self.app.game.level_number, 3)
        self.assertEqual(self.app.game.tiles, LEVELS[2].make_tiles())

    def test_win_carries_lives_score_and_upgrade_to_next_level(self):
        self.app.start()
        self.app.game.lives, self.app.game.points, self.app.game.power = 2, 2100, 3
        self.finish()
        self.app.handle(10)
        self.assertEqual(self.app.game.level_number, 2)
        self.assertEqual(self.app.checkpoint, (2, 2100, 3))
        self.assertEqual(self.app.game.score, 2100)

    def test_loss_default_action_retries_and_title_can_continue_result(self):
        self.app.start(5)
        self.finish("lose")
        self.app.title()
        self.choose("resume")
        self.assertEqual(self.app.mode, "result")
        self.app.handle(10)
        self.assertEqual(self.app.game.level_number, 5)
        self.assertIsNone(self.app.game.result)

    def test_full_campaign_all_35_transitions_and_final_menu(self):
        self.app.start()
        total = 0
        for number in range(1, 36):
            game = self.app.game
            self.assertEqual(game.level_number, number)
            game.tiles.clear()
            game.spawned = 20
            for kind in game.level.bots:
                enemy = Tank(16, 44, kind=kind)
                game.enemies = [enemy]
                game.command("fire")
                game.player.cooldown = 0
            total += sum({"basic": 100, "fast": 200, "power": 300, "armor": 400}[kind] for kind in game.level.bots)
            self.assertEqual((game.result, game.kills, game.score), ("win", 20, total))
            self.app.update(0)
            self.app.draw()
            if number < 35:
                self.app.handle(10)
            else:
                self.assertIn(" 全部 35 关完成 ", self.screen.writes)
                self.app.next_level()
                self.assertIs(self.app.game, game)
                self.app.handle(10)
                self.assertEqual(self.app.mode, "title")
        self.assertEqual(self.save_mock.call_count, 35)
        self.assertEqual(self.app.best, total)

    def test_result_saved_once_and_failed_record_still_allows_next(self):
        self.app.start()
        self.save_mock.return_value = (False, None)
        self.finish()
        self.app.update(1)
        self.save_mock.assert_called_once()
        self.app.draw()
        self.assertIn("记录保存失败，本局仍可继续操作。", self.screen.writes)
        self.app.handle(10)
        self.assertEqual(self.app.game.level_number, 2)

    def test_corrupt_record_backup_feedback(self):
        self.app.start()
        self.save_mock.return_value = (True, Path("/data/scores.json.corrupt-17"))
        self.finish("lose")
        self.app.draw()
        self.assertIn("原记录无法读取，已另存为 scores.json.corrupt-17", self.screen.writes)
        self.app.handle(ord("r"))
        self.save_mock.return_value = (True, None)
        self.finish("lose")
        self.app.draw()
        self.assertIn("本地最高分 000000", self.screen.writes)

    def test_resize_pauses_until_continue_and_tiny_window_can_quit(self):
        self.app.start()
        self.screen.width = 30
        self.app.update(2)
        self.app.draw()
        self.assertEqual(self.app.mode, "pause")
        self.app.handle(ord("p"))
        self.screen.width = 80
        self.app.update(2)
        self.assertEqual(self.app.game.elapsed, 0)
        self.app.handle(ord("p"))
        self.app.update(0.1)
        self.assertGreater(self.app.game.elapsed, 0)
        self.screen.width = 20
        self.app.handle(ord("q"))
        self.assertFalse(self.app.running)

    def test_render_every_stage_and_menu_in_ascii_and_color_without_overflow(self):
        for rich in (False, True):
            with colors():
                self.app.theme.setup({} if rich else {"ARCADE_ASCII": "1"})
                for height, width in ((24, 80), (40, 120)):
                    self.screen.height, self.screen.width = height, width
                    for number in range(1, 36):
                        self.app.start(number)
                        self.app.game.advance(1)
                        self.app.game.powerups = [PowerUp(0, 4, "star")]
                        for mode in ("title", "playing", "pause", "select", "help", "confirm", "result"):
                            self.app.mode = mode
                            self.app.game.reason = "All enemy tanks eliminated!"
                            self.app.game.result = "win" if mode == "result" else None
                            self.app._draw()
                            self.assertIn("TANK BATTLE", self.screen.writes)

    def test_forest_hides_enemy_and_armor_bonus_and_bullets_render(self):
        self.app.start(1)
        self.app.game.tiles = {(x, y): "forest" for x in range(4) for y in range(4)}
        self.app.game.enemies = [Tank(0, 0), Tank(8, 4, kind="armor", hp=3), Tank(12, 8, carries_bonus=True)]
        self.app.game.bullets = [Bullet(51, 51, Direction.UP, True)]
        self.app.game.effects = [(0, 0, 0.3)]
        self.app._draw()
        self.assertIn(" A3 ", self.screen.writes)
        self.assertEqual(self.screen.writes.count(" ^! "), 1)

    def test_presentation_freezes_and_visible_changes_invalidate(self):
        self.app.start()
        self.app.draw()
        self.app.game.player.cooldown = 0.2
        self.assertFalse(self.app.draw())
        self.app.handle(ord("p"))
        self.assertTrue(self.app.draw())
        self.app.update(10)
        self.assertFalse(self.app.draw())
        self.app.handle(27)
        self.app.update(0.5)
        self.assertTrue(self.app.draw())
        self.app.game.player.x -= 2
        self.assertTrue(self.app.draw())
        self.app.game.tiles.pop(next(iter(self.app.game.tiles)))
        self.assertTrue(self.app.draw())
        self.app.game.enemies.append(Tank(0, 0, hp=4))
        self.assertTrue(self.app.draw())
        self.app.game.enemies[-1].hp -= 1
        self.assertTrue(self.app.draw())

    def test_ignore_resize_and_empty_key_and_menu_space_confirmation(self):
        signature = self.app.frame_signature()
        self.app.handle(-1)
        self.app.handle(curses.KEY_RESIZE)
        self.assertEqual(self.app.frame_signature(), signature)
        self.app.handle(ord(" "))
        self.assertEqual(self.app.mode, "playing")

    def test_help_from_title_and_escape_exit_confirmation(self):
        self.choose("help")
        self.app.handle(ord("q"))
        self.assertEqual(self.app.mode, "title")
        self.app.handle(27)
        self.assertEqual(self.app.pending, "quit")
        self.app.handle(ord("q"))
        self.assertEqual(self.app.mode, "title")

    def test_invalid_next_does_not_skip_an_unfinished_stage(self):
        self.app.start(4)
        game = self.app.game
        self.app.next_level()
        self.assertIs(self.app.game, game)

    def test_fire_win_enters_result_immediately(self):
        self.app.start()
        self.app.game.tiles.clear()
        self.app.game.kills = 19
        self.app.game.enemies = [Tank(16, 44)]
        self.app.handle(ord("j"))
        self.assertEqual(self.app.mode, "result")

    def test_compact_glyphs_preserve_brick_masks_and_ascii_fallback(self):
        for rich in (False, True):
            glyphs = Glyphs(rich)
            self.assertEqual(glyphs.terrain({}, 0, 0), ("  ", "text"))
            for tile in ("brick", "steel", "water", "forest", "ice"):
                for dy in (0, 2):
                    text, role = glyphs.terrain({(0, dy): tile}, 0, 0)
                    self.assertEqual(len(text), 2)
                    self.assertTrue(role)
            if rich:
                self.assertEqual(glyphs.terrain({(0, 0): "brick", (1, 3): "brick"}, 0, 0)[0], chr(0x2881) * 2)
                self.assertEqual(glyphs.terrain({(x, y): "steel" for x in (0, 1) for y in range(4)}, 0, 0)[0], "██")

    def test_game_loop_handles_title_pause_exit_and_stops_reading(self):
        with patch.object(self.app, "setup") as setup, \
             patch.object(self.screen, "getch", side_effect=[10, -1, ord("p"), ord("q"), 10], create=True) as read, \
             patch("tank_battle.app.time.monotonic", side_effect=[0, 0.1, 0.2]), \
             patch("tank_battle.app.time.sleep") as sleep:
            self.app.run()
        setup.assert_called_once()
        self.assertFalse(self.app.running)
        self.assertEqual(read.call_count, 5)
        self.assertEqual(sleep.call_count, 2)

    def test_glyph_directions_shields_lost_icons_and_tile_patterns(self):
        for rich in (False, True):
            glyphs = Glyphs(rich)
            for direction in Direction:
                for friendly in (False, True):
                    for shielded in (False, True):
                        self.assertEqual(len(glyphs.tank(direction, friendly, shielded)[0]), 2)
                    for alive in (False, True):
                        self.assertEqual(len(glyphs.icon(friendly, alive)[0]), 2)
            for tile in ("brick", "steel", "water", "forest", "ice"):
                for phase in (0, 1):
                    self.assertEqual(len(glyphs.tile(tile, 0, phase, phase)[0]), 2)
