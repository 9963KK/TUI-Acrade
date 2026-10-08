import math
import unittest

import support  # noqa: F401
from tank_battle.levels import SCORES
from tank_battle.rules import Battle, Bullet, Direction, PowerUp, Tank


class BattleTests(unittest.TestCase):
    def arena(self, **kwargs):
        game = Battle(seed=42, **kwargs)
        game.tiles.clear()
        game.spawned = game.TARGET
        game.shield = 0
        return game

    def test_new_game_and_campaign_state(self):
        game = Battle(level=35, lives=5, score=9100, power=2)
        self.assertEqual((game.lives, game.score, game.power, game.TARGET), (5, 9100, 2, 20))
        self.assertEqual((game.WIDTH, game.HEIGHT, game.SIZE), (52, 52, 4))
        for kwargs in ({"lives": 0}, {"lives": True}, {"score": -1}, {"score": 1.0}, {"power": 4}, {"power": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Battle(**kwargs)

    def test_moves_turns_cooldown_and_full_footprint_obstacles(self):
        game = self.arena()
        x, y = game.HOME
        game.command(Direction.LEFT)
        self.assertEqual(game.player.x, x - 2)
        game.command(Direction.RIGHT)
        self.assertEqual(game.player.x, x - 2)
        self.assertEqual(game.player.direction, Direction.RIGHT)
        game.advance(0.1)
        game.tiles[x + 3, y + 3] = "steel"
        game.command(Direction.RIGHT)
        self.assertEqual(game.player.x, x - 2)
        game.player.x, game.player.y = 0, 0
        game.player.move_wait = 0
        game.command(Direction.LEFT)
        self.assertEqual(game.player.x, 0)

    def test_tanks_cannot_overlap_or_enter_base(self):
        game = self.arena()
        game.player.x, game.player.y = 24, 44
        game.command(Direction.DOWN)
        self.assertEqual(game.player.y, 44)
        game.player.move_wait = 0
        game.enemies = [Tank(24, 40)]
        game.command(Direction.UP)
        self.assertEqual(game.player.y, 44)

    def test_fire_cooldown_projectile_limits_and_auto(self):
        game = self.arena()
        game.command("fire")
        game.command("fire")
        self.assertEqual(len(game.bullets), 1)
        game.advance(0.35)
        game.command("fire")
        self.assertEqual(len(game.bullets), 1)
        game.power = 2
        game.command("auto")
        game.advance(0.35)
        self.assertEqual(len(game.bullets), 2)
        game.command("auto")
        self.assertFalse(game.auto_fire)

    def test_terrain_projectile_behavior(self):
        for tile, remains in (("brick", False), ("steel", True), ("water", True), ("forest", True), ("ice", True)):
            with self.subTest(tile=tile):
                game = self.arena()
                game.tiles[17, 47] = tile
                game.command("fire")
                self.assertEqual((17, 47) in game.tiles, remains)
                self.assertEqual(len(game.bullets), 0 if tile in ("brick", "steel") else 1)

    def test_maximum_upgrade_breaks_steel_and_fast_shots_do_not_tunnel(self):
        game = self.arena(power=3)
        game.tiles[17, 46] = "steel"
        game.command("fire")
        game.advance(0.05)
        self.assertNotIn((17, 46), game.tiles)
        self.assertFalse(game.bullets)

    def test_repeated_shots_make_a_tank_width_opening(self):
        game = self.arena()
        game.tiles = {(x, y): "brick" for x in range(16, 20) for y in range(44, 48)}
        for _ in range(2):
            game.command("fire")
            game.advance(0.3)
        self.assertFalse(game.tiles)
        game.command(Direction.UP)
        self.assertEqual(game.player.y, 46)

    def test_enemy_kinds_hit_points_and_scores(self):
        for kind, score in SCORES.items():
            game = self.arena()
            enemy = Tank(16, 44, cooldown=100, move_wait=100, kind=kind, hp=4 if kind == "armor" else 1)
            game.enemies = [enemy]
            hits = enemy.hp
            for _ in range(hits - 1):
                game.command("fire")
                game.advance(0.3)
                self.assertEqual(game.kills, 0)
            game.command("fire")
            self.assertEqual((game.kills, game.score, game.kill_counts[kind]), (1, score, 1))
            self.assertFalse(game.enemies)

    def test_last_enemy_wins_and_finished_state_freezes(self):
        game = self.arena(score=1900)
        game.kills = 19
        game.enemies = [Tank(16, 44)]
        game.command("fire")
        self.assertEqual((game.kills, game.result, game.score), (20, "win", 2000))
        game.advance(1000)
        game.command("pause")
        game.command("auto")
        self.assertEqual(game.elapsed, 0)
        self.assertFalse(game.paused)
        self.assertFalse(game.auto_fire)

    def test_no_timeout_victory(self):
        game = self.arena()
        game.advance(240)
        self.assertIsNone(game.result)
        self.assertAlmostEqual(game.elapsed, 240)

    def test_player_hit_respawn_upgrade_loss_and_shield(self):
        game = self.arena(power=3)
        game.bullets = [Bullet(17, 47, Direction.DOWN, False)]
        game.advance(0.05)
        self.assertEqual((game.lives, game.power, game.shield), (2, 0, 3.0))
        self.assertEqual((game.player.x, game.player.y), game.HOME)
        game.bullets = [Bullet(17, 47, Direction.DOWN, False)]
        game.advance(0.05)
        self.assertEqual(game.lives, 2)
        self.assertFalse(game.bullets)

    def test_respawn_avoids_occupied_home(self):
        game = self.arena()
        game.player.x, game.player.y = 10, 10
        game.enemies = [Tank(*game.HOME, cooldown=10, move_wait=10)]
        game.bullets = [Bullet(11, 9, Direction.DOWN, False)]
        game.advance(0.05)
        self.assertFalse(game._occupied(game.player.x, game.player.y, exclude=game.player))
        self.assertEqual(game.lives, 2)

    def test_last_life_and_no_safe_respawn(self):
        game = self.arena(lives=1)
        game.bullets = [Bullet(17, 47, Direction.DOWN, False)]
        game.advance(0.05)
        self.assertEqual(game.reason, "No tanks remaining.")
        game = self.arena()
        game.tiles = {(x, y): "steel" for x in range(52) for y in range(52)}
        game._hit_tank(game.player)
        self.assertEqual(game.reason, "No safe respawn position.")

    def test_all_shots_can_destroy_hq(self):
        for friendly in (True, False):
            game = self.arena()
            game.bullets = [Bullet(25, 47, Direction.DOWN, friendly)]
            game.advance(0.05)
            self.assertEqual((game.result, game.reason), ("lose", "HQ was destroyed."))

    def test_projectiles_cross_meet_and_leave_arena(self):
        for x in (6, 7):
            game = self.arena()
            game.bullets = [Bullet(5, 5, Direction.RIGHT, True), Bullet(x, 5, Direction.LEFT, False)]
            game.advance(0.05)
            self.assertFalse(game.bullets)
        game = self.arena()
        game.bullets = [Bullet(0, 0, Direction.UP, True)]
        game.advance(0.05)
        self.assertFalse(game.bullets)

    def test_fire_cancels_opposite_bullet(self):
        game = self.arena()
        game.bullets = [Bullet(17, 47, Direction.DOWN, False)]
        game.power = 2
        game.command("fire")
        self.assertFalse(game.bullets)

    def test_entering_bullet_hits_any_part_of_tank(self):
        game = self.arena()
        game.bullets = [Bullet(14, 50, Direction.DOWN, False)]
        game.command(Direction.LEFT)
        self.assertEqual(game.lives, 2)

    def test_pause_fractional_time_and_invalid_time(self):
        game = Battle(seed=3)
        game.command("pause")
        game.command(Direction.LEFT)
        game.command("fire")
        game.advance(300)
        self.assertEqual(game.elapsed, 0)
        self.assertEqual(game.spawned, 0)
        self.assertFalse(game.bullets)
        game.command("pause")
        game.advance(0.02)
        self.assertEqual(game.elapsed, 0)
        game.advance(0.03)
        self.assertAlmostEqual(game.elapsed, 0.05)
        self.assertEqual(game.spawned, 1)
        for value in (-1, math.inf, math.nan):
            with self.assertRaises(ValueError):
                game.advance(value)

    def test_forest_and_ice_are_passable_but_water_is_not(self):
        for kind in ("forest", "ice", "water"):
            game = self.arena()
            game.tiles = {(x, y): kind for x in range(12, 16) for y in range(48, 52)}
            game.command(Direction.LEFT)
            self.assertEqual(game.player.x, 16 if kind == "water" else 14)
            if kind == "ice":
                game.advance(0.2)
                self.assertLess(game.player.x, 14)

    def test_ice_stops_sliding_at_wall(self):
        game = self.arena()
        game.tiles[14, 48] = "ice"
        game.command(Direction.LEFT)
        game.tiles[12, 48] = "steel"
        game.advance(0.1)
        self.assertEqual((game.player.x, game.slide), (14, 0))

    def test_pickup_lifetime_and_all_six_bonuses(self):
        for kind in ("star", "tank", "helmet", "clock", "grenade", "shovel"):
            with self.subTest(kind=kind):
                game = self.arena()
                game.powerups = [PowerUp(12, 48, kind)]
                if kind == "grenade":
                    game.enemies = [Tank(0, 0, hp=4, kind="armor")]
                game.command(Direction.LEFT)
                self.assertFalse(game.powerups)
                self.assertGreaterEqual(game.score, 500)
                if kind == "star":
                    self.assertEqual(game.power, 1)
                elif kind == "tank":
                    self.assertEqual(game.lives, 4)
                elif kind == "helmet":
                    self.assertEqual(game.shield, 10)
                elif kind == "clock":
                    self.assertEqual(game.freeze, 10)
                elif kind == "grenade":
                    self.assertFalse(game.enemies)
                else:
                    self.assertEqual(game.fortify, 10)
                    self.assertEqual(game.tiles[22, 48], "steel")
        game = self.arena()
        game.powerups = [PowerUp(0, 0, "star", 0.05)]
        game.advance(0.05)
        self.assertFalse(game.powerups)

    def test_bonus_carrier_drops_on_first_hit_only_and_max_upgrade(self):
        game = self.arena()
        enemy = Tank(16, 44, hp=4, kind="armor", carries_bonus=True)
        game.enemies = [enemy]
        game.command("fire")
        self.assertEqual(len(game.powerups), 1)
        original = list(game.powerups)
        game.advance(0.3)
        game.command("fire")
        self.assertEqual(game.powerups, original)
        game.power = 3
        game._collect("star")
        self.assertEqual(game.power, 3)

    def test_bonus_has_no_spawn_when_entire_field_blocked(self):
        game = self.arena()
        game.tiles = {(x, y): "steel" for x in range(52) for y in range(52)}
        game._drop_bonus()
        self.assertFalse(game.powerups)

    def test_clock_freezes_tanks_and_shovel_restores_original_terrain(self):
        game = self.arena()
        game.enemies = [Tank(0, 0, Direction.DOWN)]
        game.tiles[22, 48] = "brick"
        original = dict(game.tiles)
        game._collect("clock")
        game._collect("shovel")
        game.advance(1)
        self.assertEqual((game.enemies[0].x, game.enemies[0].y), (0, 0))
        self.assertFalse(game.bullets)
        game._collect("shovel")
        game.enemies.clear()
        game.advance(10.1)
        self.assertEqual(game.tiles, original)
        self.assertEqual(game.fortify, 0)

    def test_extra_life_every_ten_thousand_points(self):
        game = self.arena(score=9900)
        game.enemies = [Tank(16, 44, kind="power")]
        game.command("fire")
        self.assertEqual((game.score, game.lives), (10200, 4))
        game._collect("star")
        self.assertEqual(game.lives, 4)

    def test_deterministic_simulation_across_frame_sizes(self):
        first, second = Battle(seed=12, level=35), Battle(seed=12, level=35)
        first.advance(8)
        for _ in range(160):
            second.advance(0.05)
        for attr in ("enemies", "bullets", "tiles", "powerups", "score", "result"):
            self.assertEqual(getattr(first, attr), getattr(second, attr))

    def test_generated_playthroughs_preserve_invariants_in_every_stage(self):
        import random
        rng = random.Random(5)
        for number in range(1, 36):
            game = Battle(seed=number, level=number)
            game.command("auto")
            for _ in range(100):
                game.command(rng.choice(list(Direction)))
                game.advance(0.1)
                tanks = [game.player, *game.enemies]
                for tank in tanks:
                    self.assertTrue(game._inside(tank.x, tank.y, 4))
                    self.assertFalse(game._blocked(tank.x, tank.y))
                    self.assertFalse(game._occupied(tank.x, tank.y, exclude=tank))
                self.assertLessEqual(len(game.enemies), 4)
                self.assertLessEqual(game.spawned, 20)
                if game.result:
                    break
