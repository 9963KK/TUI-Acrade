"""Terminal-independent tank battle rules."""

from collections import deque
from dataclasses import dataclass
from enum import Enum
import math
import random


class Direction(Enum):
    UP = (0, -1)
    RIGHT = (1, 0)
    DOWN = (0, 1)
    LEFT = (-1, 0)


@dataclass
class Tank:
    x: int
    y: int
    direction: Direction = Direction.UP
    cooldown: float = 0.0
    move_wait: float = 0.0


@dataclass
class Bullet:
    x: int
    y: int
    direction: Direction
    friendly: bool


class Battle:
    WIDTH = 29
    HEIGHT = 19
    LIMIT = 180.0
    TARGET = 12
    STEP = 0.05
    BASE = (14, 18)
    HOME = (12, 17)
    SPAWNS = ((2, 0), (14, 0), (26, 0))

    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.tiles = self._make_map()
        self.player = Tank(*self.HOME)
        self.enemies = []
        self.bullets = []
        self.effects = []
        self.lives = 3
        self.kills = 0
        self.spawned = 0
        self.elapsed = 0.0
        self.spawn_wait = 0.0
        self.shield = 3.0
        self.paused = False
        self.auto_fire = False
        self.result = None
        self.reason = ""
        self._accumulator = 0.0

    def _make_map(self):
        tiles = {}
        for y in (3, 4, 8, 9, 13, 14):
            for x in range(2, 27):
                if x % 6 in (2, 3, 4):
                    tiles[x, y] = "brick"
        for x in (8, 20):
            for y in (6, 7, 11, 12):
                tiles[x, y] = "steel"
        for x in (5, 6, 22, 23):
            tiles[x, 10] = "water"
        for pos in ((13, 17), (14, 17), (15, 17), (13, 18), (15, 18)):
            tiles[pos] = "brick"
        return tiles

    @property
    def remaining(self):
        return max(0, math.ceil(self.LIMIT - self.elapsed))

    @property
    def score(self):
        return self.kills * 100 + (self.lives * 200 + self.remaining * 5 if self.result == "win" else 0)

    def command(self, action):
        if self.result:
            return
        if action == "pause":
            self.paused = not self.paused
            return
        if self.paused:
            return
        if isinstance(action, Direction):
            self.player.direction = action
            if self.player.move_wait <= 0:
                self._move(self.player)
                self.player.move_wait = 0.10
        elif action == "fire":
            self._fire(self.player, True)
        elif action == "auto":
            self.auto_fire = not self.auto_fire

    def advance(self, seconds):
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError("Elapsed time must be finite and non-negative")
        if self.paused or self.result:
            return
        self._accumulator += seconds
        while self._accumulator + 1e-9 >= self.STEP and not self.result:
            self._accumulator -= self.STEP
            self._tick()

    def _tick(self):
        self.elapsed = min(self.LIMIT, self.elapsed + self.STEP)
        if self.elapsed >= self.LIMIT - 1e-8:
            self.elapsed = self.LIMIT
            self._finish("win", "Reinforcements arrived. HQ is safe!")
            return
        self.shield = max(0, self.shield - self.STEP)
        self.effects = [(x, y, life - self.STEP) for x, y, life in self.effects if life > self.STEP]
        for tank in [self.player, *self.enemies]:
            tank.cooldown = max(0, tank.cooldown - self.STEP)
            tank.move_wait = max(0, tank.move_wait - self.STEP)
        self.spawn_wait -= self.STEP
        if self.spawn_wait <= 0 and self.spawned < self.TARGET and len(self.enemies) < 4:
            for x, y in self.rng.sample(self.SPAWNS, len(self.SPAWNS)):
                if not self._occupied(x, y):
                    self.enemies.append(Tank(x, y, Direction.DOWN, 1.0, 0.5))
                    self.spawned += 1
                    self.spawn_wait = 4.0
                    break
        if self.auto_fire:
            self._fire(self.player, True)
        for enemy in list(self.enemies):
            if self.result:
                break
            if enemy.move_wait <= 0:
                target = (self.player.x, self.player.y) if self.rng.random() < 0.35 else self.BASE
                enemy.direction = self._toward(enemy, target)
                self._move(enemy)
                enemy.move_wait = self.rng.uniform(0.4, 0.7)
            self._fire(enemy, False)
        if not self.result:
            self._step_bullets()

    def _inside(self, x, y):
        return 0 <= x < self.WIDTH and 0 <= y < self.HEIGHT

    def _occupied(self, x, y, exclude=None):
        return any(t is not exclude and (t.x, t.y) == (x, y) for t in [self.player, *self.enemies])

    def _move(self, tank):
        dx, dy = tank.direction.value
        x, y = tank.x + dx, tank.y + dy
        if self._inside(x, y) and (x, y) not in self.tiles and (x, y) != self.BASE and not self._occupied(x, y, tank):
            tank.x, tank.y = x, y
            for bullet in list(self.bullets):
                if (bullet.x, bullet.y) == (x, y) and bullet.friendly != (tank is self.player):
                    self.bullets.remove(bullet)
                    self._hit_tank(tank)
                    break

    def _toward(self, tank, target):
        # 砖墙可被炮弹打通；钢墙和水域需要绕行。
        queue = deque([(tank.x, tank.y, None)])
        seen = {(tank.x, tank.y)}
        directions = list(Direction)
        self.rng.shuffle(directions)
        while queue:
            x, y, first = queue.popleft()
            if (x, y) == target and first is not None:
                return first
            for direction in directions:
                dx, dy = direction.value
                pos = x + dx, y + dy
                if pos in seen or not self._inside(*pos) or self.tiles.get(pos) in ("steel", "water"):
                    continue
                if pos != target and self._occupied(*pos, exclude=tank):
                    continue
                seen.add(pos)
                queue.append((*pos, first or direction))
        return tank.direction

    def _fire(self, tank, friendly):
        if tank.cooldown > 0 or self.result or (not friendly and tank not in self.enemies):
            return
        tank.cooldown = 0.3 if friendly else self.rng.uniform(1.1, 1.8)
        dx, dy = tank.direction.value
        bullet = Bullet(tank.x + dx, tank.y + dy, tank.direction, friendly)
        for other in list(self.bullets):
            if (other.x, other.y) == (bullet.x, bullet.y) and other.friendly != friendly:
                self.bullets.remove(other)
                return
        if not self._impact(bullet):
            self.bullets.append(bullet)

    def _step_bullets(self):
        # 同一 tick 中先计算轨迹，处理相遇与交叉，避免双方炮弹穿透。
        paths = []
        for bullet in self.bullets:
            dx, dy = bullet.direction.value
            paths.append(((bullet.x, bullet.y), (bullet.x + dx, bullet.y + dy)))
        cancelled = set()
        for i, first in enumerate(self.bullets):
            for j in range(i + 1, len(self.bullets)):
                if first.friendly == self.bullets[j].friendly:
                    continue
                a, b = paths[i], paths[j]
                if a[1] == b[1] or (a[0] == b[1] and a[1] == b[0]):
                    cancelled.update((i, j))
        survivors = []
        for i, bullet in enumerate(self.bullets):
            if i in cancelled:
                continue
            bullet.x, bullet.y = paths[i][1]
            if not self._impact(bullet):
                survivors.append(bullet)
            if self.result:
                break
        self.bullets = survivors

    def _impact(self, bullet):
        pos = bullet.x, bullet.y
        if not self._inside(*pos):
            return True
        tile = self.tiles.get(pos)
        if tile in ("brick", "steel"):
            if tile == "brick":
                del self.tiles[pos]
                self.effects.append((*pos, 0.15))
            return True
        if pos == self.BASE:
            if not bullet.friendly:
                self._finish("lose", "HQ was destroyed.")
            return True
        targets = list(self.enemies) if bullet.friendly else [self.player]
        for tank in targets:
            if pos == (tank.x, tank.y):
                self._hit_tank(tank)
                return True
        return False

    def _hit_tank(self, tank):
        if tank is self.player:
            if self.shield > 0:
                return
            self.lives -= 1
            if self.lives == 0:
                self._finish("lose", "No tanks remaining.")
            else:
                # 优先回到出生点；敌人占位时使用最近的空地。
                spaces = [(x, y) for y in range(self.HEIGHT) for x in range(self.WIDTH)
                          if (x, y) not in self.tiles and (x, y) != self.BASE and not self._occupied(x, y, tank)]
                tank.x, tank.y = min(spaces, key=lambda p: abs(p[0] - self.HOME[0]) + abs(p[1] - self.HOME[1]))
                tank.direction = Direction.UP
                self.shield = 3.0
        elif tank in self.enemies:
            self.enemies.remove(tank)
            self.kills += 1
            self.effects.append((tank.x, tank.y, 0.3))
            if self.kills >= self.TARGET:
                self._finish("win", "All 12 enemy tanks eliminated!")

    def _finish(self, result, reason):
        self.result = result
        self.reason = reason
