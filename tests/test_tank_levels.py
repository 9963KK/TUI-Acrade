from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import support  # noqa: F401
from tank_battle.levels import BASE, HOME, KINDS, LEVELS, SIZE, SPAWNS, STAGES, get_level, load_level
from tank_battle.rules import Battle, Direction, Tank


class LevelTests(unittest.TestCase):
    def test_complete_stage_set_and_metadata(self):
        self.assertEqual(len(LEVELS), 35)
        self.assertEqual(len(list(STAGES.glob("stage-*.json"))), 35)
        self.assertEqual(len({level.layout for level in LEVELS}), 35)
        kinds = set()
        terrain = set()
        for number, level in enumerate(LEVELS, 1):
            self.assertIs(get_level(number), level)
            self.assertEqual(level.number, number)
            self.assertEqual(level.target, 20)
            self.assertEqual(level.max_enemies, 4)
            self.assertIn(level.difficulty, (1, 2, 3, 4))
            self.assertTrue(level.description)
            kinds.update(level.bots)
            terrain.update(level.make_tiles().values())
        self.assertEqual(kinds, set(KINDS))
        self.assertEqual(terrain, {"brick", "steel", "water", "forest", "ice"})

    def test_lookup_rejects_bad_numbers(self):
        for number in (0, -1, 36, "1", 1.0, True, None):
            with self.subTest(number=number), self.assertRaises(ValueError):
                get_level(number)
            with self.assertRaises(ValueError):
                Battle(level=number)

    def test_source_data_matches_pinned_upstream_digest(self):
        # 固定整个数据集的内容与顺序，防止遗漏关卡或误改原始地图。
        content = b"".join((STAGES / f"stage-{i}.json").read_bytes() for i in range(1, 36))
        self.assertEqual(hashlib.sha256(content).hexdigest(), "17abe1d298376ebae4897a34d97101efd061b3662c41b993004099c6d8d0df01")

    def test_all_maps_preserve_geometry_and_spawns(self):
        for level in LEVELS:
            tiles = level.make_tiles()
            self.assertTrue(all(0 <= x < 52 and 0 <= y < 52 for x, y in tiles))
            for x, y in (BASE, HOME, *SPAWNS):
                self.assertTrue(all(tiles.get((x + dx, y + dy)) not in ("brick", "steel", "water")
                                    for dx in range(SIZE) for dy in range(SIZE)))

    def test_first_map_has_original_base_shelter_and_partial_bricks(self):
        tiles = LEVELS[0].make_tiles()
        # Ba 在基地左边：仅右半块；B5 在右边：仅左半块。
        for y in range(48, 52):
            self.assertNotIn((20, y), tiles)
            self.assertEqual(tiles[22, y], "brick")
            self.assertEqual(tiles[28, y], "brick")
            self.assertNotIn((30, y), tiles)
        self.assertEqual(sum(kind == "brick" for kind in tiles.values()), 880)
        self.assertEqual(sum(kind == "steel" for kind in tiles.values()), 32)

    def map_with(self, token):
        rows = [" ".join(["X"] * 13) for _ in range(13)]
        rows[3] = token + " " + " ".join(["X"] * 12)
        rows[-1] = " ".join(["X"] * 6 + ["E"] + ["X"] * 6)
        return replace(LEVELS[0], layout=tuple(rows))

    def test_short_and_full_hex_use_correct_quadrant_order(self):
        expected = {(0, 12), (1, 12), (0, 13), (1, 13)}
        self.assertEqual(set(self.map_with("B1").make_tiles()), expected)
        self.assertEqual(set(self.map_with("BF000").make_tiles()), expected)
        self.assertEqual(set(self.map_with("B1000").make_tiles()), {(0, 12)})
        self.assertEqual(set(self.map_with("T8").make_tiles()), {(2, 14), (3, 14), (2, 15), (3, 15)})

    def test_invalid_map_dimensions_terrain_and_hq(self):
        for token in ("?", "B", "BG", "BFF", "TFF", "X1", "R1"):
            with self.subTest(token=token), self.assertRaises(ValueError):
                self.map_with(token).make_tiles()
        for layout in (LEVELS[0].layout[:-1], ("X",) + LEVELS[0].layout[1:],
                       tuple(row.replace(" E ", " X ") for row in LEVELS[0].layout)):
            with self.assertRaises(ValueError):
                replace(LEVELS[0], layout=layout).make_tiles()
        rows = list(LEVELS[0].layout)
        rows[0] = "Bf " + " ".join(["X"] * 12)
        with self.assertRaises(ValueError):
            replace(LEVELS[0], layout=tuple(rows)).make_tiles()

    def test_invalid_enemy_queue_and_metadata(self):
        data = json.loads((STAGES / "stage-1.json").read_text(encoding="utf-8-sig"))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "stage.json"
            for bots in (["20*bogus"], ["100*basic"], ["19*basic"], ["-1*basic"], ["1e309*basic"]):
                path.write_text(json.dumps({**data, "bots": bots}))
                with self.assertRaises(ValueError):
                    load_level(path, 1)
            for change in ({"name": "2"}, {"difficulty": 5}):
                path.write_text(json.dumps({**data, **change}))
                with self.assertRaises(ValueError):
                    load_level(path, 1)

    def test_destroying_terrain_does_not_change_templates(self):
        for number in range(1, 36):
            first, second = Battle(level=number), Battle(level=number)
            first.tiles.pop(next(iter(first.tiles)))
            self.assertEqual(second.tiles, get_level(number).make_tiles())
            self.assertNotEqual(first.tiles, second.tiles)

    def test_enemy_queue_order_health_and_bonus_carriers(self):
        for number in range(1, 36):
            game = Battle(level=number)
            game.tiles.clear()
            game.freeze = 100
            for index, kind in enumerate(game.level.bots):
                game.enemies.clear()
                game.spawn_wait = 0
                game.advance(game.STEP)
                enemy = game.enemies[0]
                self.assertEqual(enemy.kind, kind)
                self.assertEqual(enemy.hp, 4 if kind == "armor" else 1)
                self.assertEqual(enemy.carries_bonus, index in (3, 10, 17))
                self.assertEqual(game.spawn_wait, game.level.spawn_interval)
            game.enemies.clear()
            game.spawn_wait = 0
            game.advance(game.STEP)
            self.assertFalse(game.enemies)

    def test_spawn_cap_and_blocked_spawn(self):
        game = Battle()
        game.enemies = [Tank(x, 0, cooldown=100, move_wait=100) for x in (0, 12, 24, 48)]
        game.advance(game.STEP)
        self.assertEqual(game.spawned, 0)
        game.enemies.pop(1)
        game.advance(game.STEP)
        self.assertEqual(game.spawned, 0)
        game.enemies.clear()
        game.advance(game.STEP)
        self.assertEqual(game.spawned, 1)

    def test_spawn_interval_matches_classic_formula(self):
        self.assertAlmostEqual(LEVELS[0].spawn_interval, 3.1)
        self.assertAlmostEqual(LEVELS[-1].spawn_interval, 5 / 6)
        self.assertTrue(all(a.spawn_interval > b.spawn_interval for a, b in zip(LEVELS, LEVELS[1:])))

    def test_fast_tanks_move_faster_and_power_tanks_have_fast_shells(self):
        games = [Battle(seed=5) for _ in range(2)]
        for game, kind in zip(games, ("basic", "fast")):
            game.tiles.clear()
            game.enemies = [Tank(0, 0, Direction.DOWN, kind=kind)]
            game.spawned = 20
            game.advance(0.05)
        self.assertAlmostEqual(games[0].enemies[0].move_wait, games[1].enemies[0].move_wait * 2)
        game = games[0]
        game.bullets.clear()
        enemy = game.enemies[0]
        enemy.kind, enemy.cooldown = "power", 0
        game._fire(enemy, False)
        self.assertEqual(game.bullets[0].speed, 2)
