"""Data-driven stages for the terminal tank game."""

from dataclasses import dataclass

WIDTH = 29
HEIGHT = 19
BASE = (14, 18)
HOME = (12, 17)
SPAWNS = ((2, 0), (14, 0), (26, 0))
TILES = {"#": "brick", "S": "steel", "~": "water"}


@dataclass(frozen=True)
class Level:
    name: str
    description: str
    layout: tuple[str, ...]
    target: int = 12
    spawn_interval: float = 4.0
    max_enemies: int = 4
    move_delay: tuple[float, float] = (0.4, 0.7)
    fire_delay: tuple[float, float] = (1.1, 1.8)

    def make_tiles(self):
        """每局生成独立地形；破坏砖墙不会修改关卡模板。"""
        if len(self.layout) != HEIGHT or any(len(row) != WIDTH for row in self.layout):
            raise ValueError(f"Level {self.name!r} must have a {WIDTH} x {HEIGHT} layout")
        if any(cell not in ".#S~" for row in self.layout for cell in row):
            raise ValueError(f"Level {self.name!r} contains an unknown terrain symbol")
        tiles = {(x, y): TILES[cell] for y, row in enumerate(self.layout)
                 for x, cell in enumerate(row) if cell in TILES}
        if any(pos in tiles for pos in (BASE, HOME, *SPAWNS)):
            raise ValueError(f"Level {self.name!r} blocks the base or a spawn point")
        return tiles


# . 空地，# 砖墙，S 钢墙，~ 水域。第 1 关保持原版终端地图与节奏。
LEVELS = (
    Level("前线阵地", "利用砖墙掩护，熟悉基地防守。", (
        ".............................",
        ".............................",
        ".............................",
        "..###...###...###...###...#..",
        "..###...###...###...###...#..",
        ".............................",
        "........S...........S........",
        "........S...........S........",
        "..###...###...###...###...#..",
        "..###...###...###...###...#..",
        ".....~~...............~~.....",
        "........S...........S........",
        "........S...........S........",
        "..###...###...###...###...#..",
        "..###...###...###...###...#..",
        ".............................",
        ".............................",
        ".............###.............",
        ".............#.#.............",
    )),
    Level("渡口防线", "水道分割战场，留意两翼的敌军。", (
        ".............................",
        ".............................",
        "........~~.........~~........",
        "..####..~~..####...~~..####..",
        "........~~.........~~........",
        ".............................",
        "....S...................S....",
        "....S...~~.........~~...S....",
        "..####..~~..####...~~..####..",
        "........~~.........~~........",
        "........~~.........~~........",
        "....S...................S....",
        "....S...................S....",
        "..####..~~..####...~~..####..",
        "........~~.........~~........",
        ".............................",
        ".............................",
        ".............###.............",
        ".............#.#.............",
    ), target=16, spawn_interval=3.5, move_delay=(0.35, 0.6), fire_delay=(1.0, 1.6)),
    Level("钢铁要塞", "钢墙形成狭道，敌军增援更快。", (
        ".............................",
        ".............................",
        ".............................",
        "..SSS...SSSSS...SSSSS...SSS..",
        "..##...###...###...###...##..",
        ".............................",
        ".............................",
        "..SSS...SSSSS...SSSSS...SSS..",
        "..##...###...###...###...##..",
        ".............................",
        ".............................",
        "..SSS...SSSSS...SSSSS...SSS..",
        "..##...###...###...###...##..",
        ".............................",
        ".............................",
        ".....~~...............~~.....",
        ".............................",
        ".............###.............",
        ".............#.#.............",
    ), target=20, spawn_interval=3.0, max_enemies=5,
          move_delay=(0.3, 0.55), fire_delay=(0.9, 1.4)),
)


def get_level(number):
    """关卡编号从 1 开始；非法编号不会偷偷回到第 1 关。"""
    if type(number) is not int or not 1 <= number <= len(LEVELS):
        raise ValueError(f"Level number must be between 1 and {len(LEVELS)}")
    return LEVELS[number - 1]
