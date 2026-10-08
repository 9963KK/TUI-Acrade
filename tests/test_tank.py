import math
import random
from itertools import product
import unittest

import support  # noqa: F401
from tank_battle.rules import Battle, Bullet, Direction, Tank
from tank_battle.levels import LEVELS


class BattleTests(unittest.TestCase):
    def arena(self):
        game = Battle(seed=42)
        game.tiles.clear()
        game.spawned = game.TARGET
        game.shield = 0
        return game

    def test_new_game(self):
        game = Battle(seed=1)
        self.assertEqual((game.lives, game.remaining, game.score), (3, 180, 0))
        self.assertNotIn(game.HOME, game.tiles)
        self.assertNotIn(game.BASE, game.tiles)
        self.assertEqual({"brick", "water", "steel"}, set(game.tiles.values()))

    def test_moves_turns_cooldown_and_obstacles(self):
        game = self.arena()
        game.command(Direction.LEFT)
        self.assertEqual(game.player.x, 11)
        game.command(Direction.RIGHT)
        self.assertEqual(game.player.x, 11)
        self.assertEqual(game.player.direction, Direction.RIGHT)
        game.advance(0.1)
        game.tiles[12, 17] = "steel"
        game.command(Direction.RIGHT)
        self.assertEqual(game.player.x, 11)
        game.player.x, game.player.y = 0, 0
        game.advance(0.1)
        game.command(Direction.LEFT)
        self.assertEqual(game.player.x, 0)

    def test_tanks_cannot_overlap_or_enter_base(self):
        game = self.arena()
        game.player.x, game.player.y = 14, 17
        game.command(Direction.DOWN)
        self.assertEqual(game.player.y, 17)
        game.player.move_wait = 0
        game.enemies = [Tank(14, 16)]
        game.command(Direction.UP)
        self.assertEqual(game.player.y, 17)

    def test_fire_cooldown_and_auto(self):
        game = self.arena()
        game.command("fire")
        game.command("fire")
        self.assertEqual(len(game.bullets), 1)
        game.advance(0.35)
        game.command("fire")
        self.assertEqual(len(game.bullets), 2)
        game.command("auto")
        game.advance(0.35)
        self.assertEqual(len(game.bullets), 3)
        game.command("auto")
        self.assertFalse(game.auto_fire)

    def test_brick_destroyed_steel_stops_water_passes(self):
        for tile, expected in (("brick", False), ("steel", True), ("water", True)):
            with self.subTest(tile=tile):
                game = self.arena()
                game.tiles[12, 16] = tile
                game.command("fire")
                self.assertEqual((12, 16) in game.tiles, expected)
                self.assertEqual(len(game.bullets), 1 if tile == "water" else 0)

    def test_enemy_hit_and_early_victory(self):
        game = self.arena()
        game.kills = 11
        game.enemies = [Tank(12, 16)]
        game.command("fire")
        self.assertEqual((game.kills, game.result, game.score), (12, "win", 2700))
        self.assertFalse(game.enemies)

    def test_enemy_killed_by_travelling_bullet(self):
        game = self.arena()
        game.enemies = [Tank(12, 14, move_wait=1, cooldown=1)]
        game.command("fire")
        game.advance(0.1)
        self.assertEqual(game.kills, 1)

    def test_player_damage_respawn_and_shield(self):
        game = self.arena()
        game.bullets = [Bullet(12, 16, Direction.DOWN, False)]
        game.advance(0.05)
        self.assertEqual(game.lives, 2)
        self.assertEqual(game.shield, 3.0)
        game.bullets = [Bullet(12, 16, Direction.DOWN, False)]
        game.advance(0.05)
        self.assertEqual(game.lives, 2)
        self.assertFalse(game.bullets)

    def test_respawn_avoids_occupied_home(self):
        game = self.arena()
        game.player.x, game.player.y = 10, 10
        game.enemies = [Tank(*game.HOME, cooldown=2, move_wait=2)]
        game.bullets = [Bullet(10, 9, Direction.DOWN, False)]
        game.advance(0.05)
        self.assertNotEqual((game.player.x, game.player.y), game.HOME)
        self.assertEqual(game.lives, 2)

    def test_last_life_ends_game(self):
        game = self.arena()
        game.lives = 1
        game.bullets = [Bullet(12, 16, Direction.DOWN, False)]
        game.advance(0.05)
        self.assertEqual(game.result, "lose")
        self.assertEqual(game.reason, "No tanks remaining.")

    def test_base_hostile_damage_and_friendly_immunity(self):
        for friendly in (True, False):
            game = self.arena()
            game.bullets = [Bullet(14, 17, Direction.DOWN, friendly)]
            game.advance(0.05)
            self.assertEqual(game.result, None if friendly else "lose")

    def test_bullet_collision_crossing_and_meeting(self):
        for x in (6, 7):
            game = self.arena()
            game.bullets = [Bullet(5, 5, Direction.RIGHT, True), Bullet(x, 5, Direction.LEFT, False)]
            game.advance(0.05)
            self.assertFalse(game.bullets)

    def test_shot_cancels_existing_opposite_bullet(self):
        game = self.arena()
        game.bullets = [Bullet(12, 16, Direction.DOWN, False)]
        game.command("fire")
        self.assertFalse(game.bullets)

    def test_entering_bullet_hits_immediately(self):
        game = self.arena()
        game.bullets = [Bullet(11, 17, Direction.DOWN, False)]
        game.command(Direction.LEFT)
        self.assertEqual(game.lives, 2)

    def test_bullets_leave_arena(self):
        game = self.arena()
        game.bullets = [Bullet(0, 0, Direction.UP, True)]
        game.advance(0.05)
        self.assertFalse(game.bullets)

    def test_pause_freezes_all_state_and_blocks_actions(self):
        game = Battle(seed=3)
        game.command("pause")
        game.command(Direction.LEFT)
        game.command("fire")
        game.advance(300)
        self.assertEqual(game.elapsed, 0)
        self.assertEqual(game.spawned, 0)
        self.assertEqual((game.player.x, game.player.y), game.HOME)
        self.assertFalse(game.bullets)
        game.command("pause")
        game.advance(0.1)
        self.assertEqual(game.spawned, 1)

    def test_timeout_and_finished_state_is_frozen(self):
        game = self.arena()
        game.advance(180)
        self.assertEqual((game.result, game.remaining), ("win", 0))
        self.assertEqual(game.score, 600)
        game.advance(1000)
        game.command("pause")
        self.assertFalse(game.paused)
        self.assertEqual(game.elapsed, 180)

    def test_fractional_steps_and_invalid_time(self):
        game = self.arena()
        game.advance(0.02)
        self.assertEqual(game.elapsed, 0)
        game.advance(0.03)
        self.assertAlmostEqual(game.elapsed, 0.05)
        for value in (-1, math.inf, math.nan):
            with self.assertRaises(ValueError):
                game.advance(value)

    def test_deterministic_simulation_across_frame_sizes(self):
        first, second = Battle(seed=12), Battle(seed=12)
        first.advance(8)
        for _ in range(160):
            second.advance(0.05)
        self.assertEqual(first.enemies, second.enemies)
        self.assertEqual(first.bullets, second.bullets)
        self.assertEqual(first.tiles, second.tiles)

    def test_generated_playthroughs_preserve_invariants_and_end_within_limit(self):
        rng = random.Random(5)
        for level, seed in product(range(1, len(LEVELS) + 1), range(10)):
            game = Battle(seed=seed, level=level)
            game.command("auto")
            for _ in range(1800):
                game.command(rng.choice(list(Direction)))
                game.advance(0.1)
                tanks = [game.player, *game.enemies]
                positions = [(tank.x, tank.y) for tank in tanks]
                self.assertEqual(len(positions), len(set(positions)))
                self.assertLessEqual(len(game.enemies), game.level.max_enemies)
                self.assertLessEqual(game.spawned, game.TARGET)
                self.assertTrue(all(0 <= x < game.WIDTH and 0 <= y < game.HEIGHT for x, y in positions))
                self.assertTrue(all(pos not in game.tiles and pos != game.BASE for pos in positions))
                if game.result:
                    break
            self.assertIsNotNone(game.result)
            self.assertLessEqual(game.elapsed, game.LIMIT)


if __name__ == "__main__":
    unittest.main()
