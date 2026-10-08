"""Terminal-independent classic tank rules."""

from collections import Counter, deque
from dataclasses import dataclass
from enum import Enum
import math
import random

from .levels import BASE, HEIGHT, HOME, SCORES, SIZE, SPAWNS, WIDTH, get_level


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
    kind: str = "basic"
    hp: int = 1
    carries_bonus: bool = False


@dataclass
class Bullet:
    x: int
    y: int
    direction: Direction
    friendly: bool
    power: int = 1
    speed: int = 1


@dataclass
class PowerUp:
    x: int
    y: int
    kind: str
    remaining: float = 15.0


class Battle:
    WIDTH = WIDTH
    HEIGHT = HEIGHT
    SIZE = SIZE
    STEP = 0.05
    BASE = BASE
    HOME = HOME
    SPAWNS = SPAWNS

    def __init__(self, seed=None, level=1, *, lives=3, score=0, power=0):
        if type(lives) is not int or lives < 1 or type(score) is not int or score < 0:
            raise ValueError("Lives must be positive and score must be non-negative integers")
        if type(power) is not int or not 0 <= power <= 3:
            raise ValueError("Player power must be between 0 and 3")
        self.rng = random.Random(seed)
        self.level = get_level(level)
        self.level_number = level
        self.TARGET = self.level.target
        self.tiles = self.level.make_tiles()
        self.player = Tank(*self.HOME)
        self.enemies = []
        self.bullets = []
        self.effects = []
        self.powerups = []
        self.lives = lives
        self.power = power
        self.points = score
        self.kills = 0
        self.kill_counts = Counter()
        self.spawned = 0
        self.elapsed = 0.0
        self.spawn_wait = 0.0
        self.shield = 3.0
        self.freeze = 0.0
        self.fortify = 0.0
        self._shelter = {}
        self.slide = 0.0
        self.paused = False
        self.auto_fire = False
        self.result = None
        self.reason = ""
        self._accumulator = 0.0

    @property
    def score(self):
        return self.points

    @staticmethod
    def overlaps(x, y, tx, ty, size=SIZE):
        return x < tx + size and tx < x + size and y < ty + size and ty < y + size

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
            if self.player.move_wait <= 1e-8:
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
        self.elapsed += self.STEP
        self.shield = max(0, self.shield - self.STEP)
        self.freeze = max(0, self.freeze - self.STEP)
        self.effects = [(x, y, life - self.STEP) for x, y, life in self.effects if life > self.STEP]
        for bonus in self.powerups:
            bonus.remaining -= self.STEP
        self.powerups = [bonus for bonus in self.powerups if bonus.remaining > 0]
        if self.fortify > 0:
            self.fortify = max(0, self.fortify - self.STEP)
            if self.fortify == 0:
                for pos, kind in self._shelter.items():
                    if kind is None:
                        self.tiles.pop(pos, None)
                    else:
                        self.tiles[pos] = kind
                self._shelter.clear()
        for tank in [self.player, *self.enemies]:
            tank.cooldown = max(0, tank.cooldown - self.STEP)
            tank.move_wait = max(0, tank.move_wait - self.STEP)
        if self.slide > 0:
            self.slide = max(0, self.slide - self.STEP)
            if self.player.move_wait <= 1e-8:
                self._move(self.player, sliding=True)
                self.player.move_wait = 0.10
        self.spawn_wait -= self.STEP
        if self.spawn_wait <= 0 and self.spawned < self.TARGET and len(self.enemies) < self.level.max_enemies:
            for x, y in self.SPAWNS[self.spawned % 3:] + self.SPAWNS[:self.spawned % 3]:
                if not self._occupied(x, y):
                    kind = self.level.bots[self.spawned]
                    self.enemies.append(Tank(x, y, Direction.DOWN, 1.0, 0.5, kind,
                                             4 if kind == "armor" else 1, self.spawned in (3, 10, 17)))
                    self.spawned += 1
                    self.spawn_wait = self.level.spawn_interval
                    break
        if self.auto_fire:
            self._fire(self.player, True)
        if self.freeze == 0:
            for enemy in list(self.enemies):
                if self.result:
                    break
                if enemy.move_wait <= 1e-8:
                    target = (self.player.x, self.player.y) if self.rng.random() < 0.35 else self.BASE
                    enemy.direction = self._toward(enemy, target)
                    self._move(enemy)
                    enemy.move_wait = self.rng.uniform(*self.level.move_delay) / (2 if enemy.kind == "fast" else 1)
                self._fire(enemy, False)
        if not self.result:
            self._step_bullets()

    def _inside(self, x, y, size=1):
        return 0 <= x <= self.WIDTH - size and 0 <= y <= self.HEIGHT - size

    def _occupied(self, x, y, exclude=None):
        return any(t is not exclude and self.overlaps(x, y, t.x, t.y)
                   for t in [self.player, *self.enemies])

    def _blocked(self, x, y, destructible=False):
        kinds = ("steel", "water") if destructible else ("brick", "steel", "water")
        return any(self.tiles.get((x + dx, y + dy)) in kinds
                   for dx in range(SIZE) for dy in range(SIZE))

    def _move(self, tank, sliding=False):
        dx, dy = tank.direction.value
        x, y = tank.x + dx * 2, tank.y + dy * 2
        if (self._inside(x, y, SIZE) and not self._blocked(x, y)
                and not self.overlaps(x, y, *self.BASE) and not self._occupied(x, y, tank)):
            tank.x, tank.y = x, y
            for bullet in list(self.bullets):
                if (x <= bullet.x < x + SIZE and y <= bullet.y < y + SIZE
                        and bullet.friendly != (tank is self.player)):
                    self.bullets.remove(bullet)
                    self._hit_tank(tank)
                    break
            if tank is self.player:
                if not sliding:
                    self.slide = 0.4 if any(self.tiles.get((x + dx, y + dy)) == "ice"
                                           for dx in range(SIZE) for dy in range(SIZE)) else 0
                for bonus in list(self.powerups):
                    if self.overlaps(x, y, bonus.x, bonus.y):
                        self.powerups.remove(bonus)
                        self._collect(bonus.kind)
        elif tank is self.player:
            self.slide = 0

    def _toward(self, tank, target):
        # 按坦克占地寻路，砖墙可打通，钢墙和水域必须绕开。
        queue = deque([(tank.x, tank.y, None)])
        seen = {(tank.x, tank.y)}
        directions = list(Direction)
        self.rng.shuffle(directions)
        while queue:
            x, y, first = queue.popleft()
            if self.overlaps(x, y, *target) and first is not None:
                return first
            for direction in directions:
                dx, dy = direction.value
                pos = x + dx * 2, y + dy * 2
                if pos in seen or not self._inside(*pos, SIZE) or self._blocked(*pos, destructible=True):
                    continue
                if not self.overlaps(*pos, *target) and self._occupied(*pos, exclude=tank):
                    continue
                seen.add(pos)
                queue.append((*pos, first or direction))
        return tank.direction

    def _fire(self, tank, friendly):
        if tank.cooldown > 1e-8 or self.result or (not friendly and tank not in self.enemies):
            return
        if sum(b.friendly == friendly for b in self.bullets) >= (2 if self.power >= 2 else 1) and friendly:
            return
        tank.cooldown = 0.3 if friendly else self.rng.uniform(*self.level.fire_delay)
        dx, dy = tank.direction.value
        x = tank.x + (SIZE if dx > 0 else -1 if dx < 0 else 1)
        y = tank.y + (SIZE if dy > 0 else -1 if dy < 0 else 1)
        bullet = Bullet(x, y, tank.direction, friendly, 3 if friendly and self.power == 3 else 1,
                        2 if (friendly and self.power > 0) or tank.kind == "power" else 1)
        for other in list(self.bullets):
            if (other.x, other.y) == (bullet.x, bullet.y) and other.friendly != friendly:
                self.bullets.remove(other)
                return
        if not self._impact(bullet):
            self.bullets.append(bullet)

    def _step_bullets(self):
        # 分步推进快炮弹，仍检查交叉碰撞，避免穿过一格薄墙或坦克。
        for step in range(2):
            paths = []
            for bullet in self.bullets:
                dx, dy = bullet.direction.value if step < bullet.speed else (0, 0)
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
            if self.result:
                break

    def _impact(self, bullet):
        pos = bullet.x, bullet.y
        if not self._inside(*pos):
            return True
        tile = self.tiles.get(pos)
        if tile in ("brick", "steel"):
            if tile == "brick" or bullet.power >= 3:
                # 终端按 8 px 移动，一炮打开坦克宽度，防止留下永远无法通过的细缝。
                dx, dy = bullet.direction.value
                points = [(pos[0] + (offset if dy else depth * dx),
                           pos[1] + (offset if dx else depth * dy))
                          for offset in range(-1, 3) for depth in range(2)]
                for point in points:
                    if self.tiles.get(point) == tile:
                        del self.tiles[point]
                self.effects.append((*pos, 0.15))
            return True
        if self.BASE[0] <= pos[0] < self.BASE[0] + SIZE and self.BASE[1] <= pos[1] < self.BASE[1] + SIZE:
            self._finish("lose", "HQ was destroyed.")
            return True
        targets = list(self.enemies) if bullet.friendly else [self.player]
        for tank in targets:
            if tank.x <= pos[0] < tank.x + SIZE and tank.y <= pos[1] < tank.y + SIZE:
                self._hit_tank(tank)
                return True
        return False

    def _add_score(self, points):
        previous = self.points // 10000
        self.points += points
        self.lives += self.points // 10000 - previous

    def _hit_tank(self, tank):
        if tank is self.player:
            if self.shield > 0:
                return
            self.lives -= 1
            self.power = 0
            self.slide = 0
            if self.lives == 0:
                self._finish("lose", "No tanks remaining.")
            else:
                spaces = [(x, y) for y in range(0, self.HEIGHT - SIZE + 1, 2)
                          for x in range(0, self.WIDTH - SIZE + 1, 2)
                          if not self._blocked(x, y) and not self.overlaps(x, y, *self.BASE)
                          and not self._occupied(x, y, tank)]
                if not spaces:
                    self._finish("lose", "No safe respawn position.")
                    return
                tank.x, tank.y = min(spaces, key=lambda p: abs(p[0] - self.HOME[0]) + abs(p[1] - self.HOME[1]))
                tank.direction = Direction.UP
                self.shield = 3.0
        elif tank in self.enemies:
            if tank.carries_bonus:
                tank.carries_bonus = False
                self._drop_bonus()
            tank.hp -= 1
            if tank.hp > 0:
                return
            self.enemies.remove(tank)
            self.kills += 1
            self.kill_counts[tank.kind] += 1
            self._add_score(SCORES[tank.kind])
            self.effects.append((tank.x, tank.y, 0.3))
            if self.kills >= self.TARGET:
                self._finish("win", "All enemy tanks eliminated!")

    def _drop_bonus(self):
        spaces = [(x, y) for y in range(4, 45, 4) for x in range(0, 49, 4)
                  if not self._blocked(x, y) and not self.overlaps(x, y, *self.BASE)]
        if spaces:
            x, y = self.rng.choice(spaces)
            self.powerups = [PowerUp(x, y, self.rng.choice(("star", "tank", "helmet", "clock", "grenade", "shovel")))]

    def _collect(self, kind):
        self._add_score(500)
        if kind == "star":
            self.power = min(3, self.power + 1)
        elif kind == "tank":
            self.lives += 1
        elif kind == "helmet":
            self.shield = 10.0
        elif kind == "clock":
            self.freeze = 10.0
        elif kind == "grenade":
            for enemy in list(self.enemies):
                enemy.hp = 1
                self._hit_tank(enemy)
        elif kind == "shovel":
            bx, by = self.BASE
            shelter = [(x, y) for y in range(by - 2, by + SIZE) for x in range(bx - 2, bx + SIZE + 2)
                       if not (bx <= x < bx + SIZE and by <= y < by + SIZE)]
            if not self._shelter:
                self._shelter = {pos: self.tiles.get(pos) for pos in shelter}
            for pos in shelter:
                self.tiles[pos] = "steel"
            self.fortify = 10.0

    def _finish(self, result, reason):
        self.result = result
        self.reason = reason
