"""Two-column battlefield glyphs, with an ASCII set for mono or limited terminals."""

import curses

from .rules import Direction

# 地形自带底色：(前景 RGB, 背景 RGB, 8 色终端下的 (前景, 背景))；块字符的前景和背景共同组成图案。
TILE_COLORS = {
    "tile.brick": ((175, 135, 95), (68, 68, 68), (curses.COLOR_YELLOW, curses.COLOR_BLACK)),
    "tile.steel": ((218, 218, 218), (128, 128, 128), (curses.COLOR_BLACK, curses.COLOR_WHITE)),
    "tile.water": ((135, 175, 215), (0, 95, 135), (curses.COLOR_CYAN, curses.COLOR_BLUE)),
    "tile.forest": ((95, 175, 95), (0, 55, 0), (curses.COLOR_GREEN, curses.COLOR_BLACK)),
    "tile.ice": ((215, 255, 255), (65, 100, 115), (curses.COLOR_WHITE, curses.COLOR_CYAN)),
    "tile.base": ((28, 28, 28), (215, 175, 95), (curses.COLOR_BLACK, curses.COLOR_YELLOW)),
    "tile.shield": ((175, 215, 95), (0, 95, 0), (curses.COLOR_BLACK, curses.COLOR_GREEN)),
}


class Glyphs:
    """每个战场格子占两列；返回 (文本, 颜色角色)。"""

    def __init__(self, rich):
        self.rich = rich

    def tile(self, kind, x, y, phase=0):
        if not self.rich:
            return {"brick": "##", "steel": "[]", "water": "~~",
                    "forest": "FF", "ice": "=="}[kind], kind if kind in ("brick", "steel", "water") else "player"
        if kind == "brick":
            # 相邻两行错开砖缝，拼出砌墙的样子。
            return ("▀▘" if y % 2 else "▝▀"), "tile.brick"
        if kind == "steel":
            return "▗▖", "tile.steel"
        if kind == "forest":
            return "♣♣", "tile.forest"
        if kind == "ice":
            return "··", "tile.ice"
        # 波纹随阶段左右交替，产生缓慢流动感。
        return ("~~" if (y + phase) % 2 else "~ "), "tile.water"

    def terrain(self, tiles, x, y, phase=0):
        """2 × 4 子格压入一行，Braille 点保留砖墙的实际缺口。"""
        cells = [(dx, dy, tiles.get((x + dx, y + dy))) for dy in range(4) for dx in range(2)]
        present = [(dx, dy, kind) for dx, dy, kind in cells if kind]
        if not present:
            return "  ", "text"
        kind = present[0][2]
        if not self.rich:
            if kind == "brick":
                return "".join("#" if any(dx == col for dx, _, _ in present) else " " for col in (0, 1)), "brick"
            return self.tile(kind, x, y, phase)
        if kind != "brick":
            text, role = self.tile(kind, x, y, phase)
            if kind == "steel":
                return ("██" if len(present) == 8 else "▀▀" if present[0][1] < 2 else "▄▄"), role
            return text, role
        dots = ((0, 3), (1, 4), (2, 5), (6, 7))
        mask = sum(1 << dots[dy][dx] for dx, dy, _ in present)
        char = chr(0x2800 + mask)
        return char * 2, "tile.brick"

    def tank(self, direction, friendly, shielded=False):
        if self.rich:
            text = {Direction.UP: "▟▙", Direction.DOWN: "▜▛",
                    Direction.LEFT: "━█", Direction.RIGHT: "█━"}[direction]
            return text, ("tile.shield" if shielded else "player" if friendly else "enemy")
        arrow = {Direction.UP: "^", Direction.RIGHT: ">", Direction.DOWN: "v", Direction.LEFT: "<"}[direction]
        return arrow + ("@" if shielded else "P" if friendly else "!"), "player" if friendly else "enemy"

    def icon(self, friendly, alive=True):
        """HUD 中的坦克小图标；已损失的在单色下也要能看出来。"""
        if not self.rich:
            return ("P " if friendly else "! ") if alive else ". ", "player" if friendly else "enemy"
        return "▟▙", ("player" if friendly else "enemy") if alive else "dim"
