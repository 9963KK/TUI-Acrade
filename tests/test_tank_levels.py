from collections import deque
from dataclasses import replace
import unittest

import support  # noqa: F401
from tank_battle.levels import BASE, HEIGHT, HOME, LEVELS, SPAWNS, WIDTH, get_level
from tank_battle.rules import Battle, Direction, Tank


class LevelTests(unittest.TestCase):
    def test_lookup_and_invalid_numbers(self):
        for number, level in enumerate(LEVELS, 1):
            self.assertIs(get_level(number), level)
        for number in (0, -1, len(LEVELS) + 1, "1", 1.0, True, None):
            with self.subTest(number=number), self.assertRaises(ValueError):
                get_level(number)
            with self.assertRaises(ValueError):
                Battle(level=number)

    def test_maps_have_valid_terrain_and_open_spawns(self):
        layouts = set()
        for level in LEVELS:
            with self.subTest(level=level.name):
                tiles = level.make_tiles()
                self.assertEqual({"brick", "steel", "water"}, set(tiles.values()))
                self.assertTrue(all(0 <= x < WIDTH and 0 <= y < HEIGHT for x, y in tiles))
                for pos in (BASE, HOME, *SPAWNS):
                    self.assertNotIn(pos, tiles)
                layouts.add(level.layout)
        self.assertEqual(len(layouts), len(LEVELS))

    def test_all_spawns_can_reach_base_through_destructible_terrain(self):
        for level in LEVELS:
            tiles = level.make_tiles()
            for start in (HOME, *SPAWNS):
                with self.subTest(level=level.name, start=start):
                    seen, queue = {start}, deque([start])
                    while queue:
                        x, y = queue.popleft()
                        for direction in Direction:
                            dx, dy = direction.value
                            pos = x + dx, y + dy
                            if (0 <= pos[0] < WIDTH and 0 <= pos[1] < HEIGHT and pos not in seen
                                    and tiles.get(pos) not in ("steel", "water")):
                                seen.add(pos)
                                queue.append(pos)
                    self.assertIn(BASE, seen)

    def test_invalid_layouts_fail_clearly(self):
        original = LEVELS[0]
        bad_layouts = [original.layout[:-1], ("." * (WIDTH - 1),) + original.layout[1:],
                       ("?" + "." * (WIDTH - 1),) + original.layout[1:]]
        for pos in (BASE, HOME, *SPAWNS):
            rows = list(original.layout)
            x, y = pos
            rows[y] = rows[y][:x] + "#" + rows[y][x + 1:]
            bad_layouts.append(tuple(rows))
        for layout in bad_layouts:
            with self.subTest(layout=layout), self.assertRaises(ValueError):
                replace(original, layout=layout).make_tiles()

    def test_first_level_preserves_existing_map(self):
        expected = {(x, y): "brick" for y in (3, 4, 8, 9, 13, 14)
                    for x in range(2, 27) if x % 6 in (2, 3, 4)}
        expected.update({(x, y): "steel" for x in (8, 20) for y in (6, 7, 11, 12)})
        expected.update({(x, 10): "water" for x in (5, 6, 22, 23)})
        expected.update({pos: "brick" for pos in ((13, 17), (14, 17), (15, 17), (13, 18), (15, 18))})
        self.assertEqual(Battle().tiles, expected)

    def test_destroying_terrain_does_not_change_another_battle(self):
        for number in range(1, len(LEVELS) + 1):
            first, second = Battle(level=number), Battle(level=number)
            first.command(Direction.RIGHT)
            first.command("fire")
            self.assertNotIn((13, 17), first.tiles)
            self.assertEqual(second.tiles[13, 17], "brick")
            self.assertEqual(Battle(level=number).tiles, second.tiles)

    def test_each_level_has_its_own_target_and_spawn_interval(self):
        for number, level in enumerate(LEVELS, 1):
            game = Battle(seed=42, level=number)
            game.advance(game.STEP)
            self.assertEqual(game.TARGET, level.target)
            self.assertEqual(game.spawned, 1)
            self.assertEqual(game.spawn_wait, level.spawn_interval)
            self.assertEqual(game.lives, 3)
            self.assertEqual(game.remaining, 180)

    def test_spawn_limits_are_respected(self):
        for number, level in enumerate(LEVELS, 1):
            with self.subTest(number=number):
                game = Battle(level=number)
                game.enemies = [Tank(x, 1, cooldown=100, move_wait=100) for x in range(level.max_enemies)]
                game.spawned = len(game.enemies)
                game.advance(game.STEP)
                self.assertEqual(len(game.enemies), level.max_enemies)
                game.enemies.pop()
                game.advance(game.STEP)
                self.assertEqual(len(game.enemies), level.max_enemies)
                game.enemies.clear()
                game.spawned = level.target
                game.spawn_wait = 0
                game.advance(game.STEP)
                self.assertFalse(game.enemies)

    def test_enemy_speed_and_fire_interval_follow_level(self):
        for number, level in enumerate(LEVELS, 1):
            game = Battle(seed=42, level=number)
            enemy = Tank(0, 0, Direction.DOWN)
            game.enemies = [enemy]
            game.spawned = game.TARGET
            game.advance(game.STEP)
            self.assertTrue(level.move_delay[0] <= enemy.move_wait <= level.move_delay[1])
            self.assertTrue(level.fire_delay[0] <= enemy.cooldown <= level.fire_delay[1])

    def test_victory_uses_current_level_target(self):
        for number in range(1, len(LEVELS) + 1):
            game = Battle(level=number)
            game.tiles.clear()
            game.kills = game.TARGET - 1
            game.enemies = [Tank(12, 16)]
            game.command("fire")
            self.assertEqual(game.result, "win")
            self.assertEqual(game.kills, game.TARGET)
            self.assertEqual(game.score, game.TARGET * 100 + 1500)

    def test_all_levels_are_deterministic(self):
        for number in range(1, len(LEVELS) + 1):
            first, second = Battle(seed=12, level=number), Battle(seed=12, level=number)
            first.advance(8)
            for _ in range(160):
                second.advance(0.05)
            self.assertEqual(first.enemies, second.enemies)
            self.assertEqual(first.bullets, second.bullets)
            self.assertEqual(first.tiles, second.tiles)

    def test_difficulty_increases_without_exceeding_hud_capacity(self):
        for previous, current in zip(LEVELS, LEVELS[1:]):
            self.assertGreaterEqual(current.target, previous.target)
            self.assertLess(current.spawn_interval, previous.spawn_interval)
            self.assertGreaterEqual(current.max_enemies, previous.max_enemies)
            self.assertTrue(all(new <= old for new, old in zip(current.move_delay, previous.move_delay)))
            self.assertTrue(all(new < old for new, old in zip(current.fire_delay, previous.fire_delay)))
        self.assertTrue(all(level.target <= 24 for level in LEVELS))

    def test_river_valley_has_three_crossings_and_no_edge_bypass(self):
        tiles = get_level(5).make_tiles()
        for row in (5, 6, 10, 11):
            crossings = {x for x in range(WIDTH) if tiles.get((x, row)) != "water"}
            self.assertEqual(crossings, {6, 7, 14, 15, 21, 22})


if __name__ == "__main__":
    unittest.main()
