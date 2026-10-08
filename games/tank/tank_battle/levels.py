"""Classic Battle City stages, adapted from feichao93/battle-city (MIT)."""

from dataclasses import dataclass
import json
from pathlib import Path
import re

# 保留原地图的 4 px 砖块网格；坦克占 4 × 4 子格，移动按 8 px 对齐。
WIDTH = HEIGHT = 52
SIZE = 4
BASE = (24, 48)
HOME = (16, 48)
SPAWNS = ((24, 0), (48, 0), (0, 0))
KINDS = ("basic", "fast", "power", "armor")
SCORES = dict(zip(KINDS, (100, 200, 300, 400)))


@dataclass(frozen=True)
class Level:
    name: str
    layout: tuple[str, ...]
    bots: tuple[str, ...]
    number: int
    difficulty: int = 1

    @property
    def target(self):
        return len(self.bots)

    @property
    def description(self):
        labels = ("普通", "快速", "火力", "装甲")
        return " / ".join(f"{label} {self.bots.count(kind)}" for label, kind in zip(labels, KINDS))

    @property
    def spawn_interval(self):
        return (190 - 4 * self.number) / 60

    max_enemies = 4
    move_delay = (0.20, 0.30)
    fire_delay = (0.8, 1.5)

    def make_tiles(self):
        """逐象限展开短/长十六进制地形；每局返回可独立破坏的副本。"""
        rows = [row.split() for row in self.layout]
        if len(rows) != 13 or any(len(row) != 13 for row in rows):
            raise ValueError("Stage map must contain 13 x 13 blocks")
        tiles = {}
        bases = []
        for row, items in enumerate(rows):
            for col, token in enumerate(items):
                token = token.upper()
                kind, bits = token[0], token[1:]
                x, y = col * SIZE, row * SIZE
                if kind == "B" and re.fullmatch(r"[0-9A-F]{1}|[0-9A-F]{4}", bits):
                    masks = ([15 if int(bits, 16) & (1 << q) else 0 for q in range(4)]
                             if len(bits) == 1 else [int(c, 16) for c in bits])
                    for q, mask in enumerate(masks):
                        for bit in range(4):
                            if mask & (1 << bit):
                                tiles[x + (q % 2) * 2 + bit % 2,
                                      y + (q // 2) * 2 + bit // 2] = "brick"
                elif kind == "T" and re.fullmatch(r"[0-9A-F]", bits):
                    for q in range(4):
                        if int(bits, 16) & (1 << q):
                            for dy in range(2):
                                for dx in range(2):
                                    tiles[x + q % 2 * 2 + dx, y + q // 2 * 2 + dy] = "steel"
                elif token in ("R", "S", "F"):
                    for dy in range(SIZE):
                        for dx in range(SIZE):
                            tiles[x + dx, y + dy] = {"R": "water", "S": "ice", "F": "forest"}[token]
                elif token in ("E", "EE"):
                    bases.append((x, y))
                elif token != "X":
                    raise ValueError(f"Invalid stage terrain: {token}")
        if bases != [BASE]:
            raise ValueError("Stage must contain one HQ at the classic base position")
        for x, y in (HOME, *SPAWNS):
            if any(tiles.get((x + dx, y + dy)) in ("brick", "steel", "water")
                   for dx in range(SIZE) for dy in range(SIZE)):
                raise ValueError("Stage blocks a tank spawn")
        return tiles


def load_level(path, number):
    """校验随包发布的地图及敌军队列，损坏数据明确报错。"""
    raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    bots = []
    for descriptor in raw["bots"]:
        match = re.fullmatch(r"(\d{1,2})\*(basic|fast|power|armor)", descriptor)
        if match is None:
            raise ValueError(f"Invalid enemy group: {descriptor}")
        bots.extend([match[2]] * int(match[1]))
    if len(bots) != 20 or raw["name"] != str(number) or raw["difficulty"] not in (1, 2, 3, 4):
        raise ValueError("Invalid classic stage metadata")
    level = Level(f"经典关卡 {number:02}", tuple(raw["map"]), tuple(bots), number, raw["difficulty"])
    level.make_tiles()
    return level


STAGES = Path(__file__).with_name("stages")
LEVELS = tuple(load_level(STAGES / f"stage-{number}.json", number) for number in range(1, 36))


def get_level(number):
    """编号从 1 开始，不允许越界或把 bool 当作关卡号。"""
    if type(number) is not int or not 1 <= number <= len(LEVELS):
        raise ValueError(f"Level number must be between 1 and {len(LEVELS)}")
    return LEVELS[number - 1]
