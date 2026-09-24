"""Two-column battlefield glyphs, with an ASCII set for mono or limited terminals."""

import curses

from .rules import Direction

# 地形自带底色：(前景 RGB, 背景 RGB, 8 色终端下的 (前景, 背景))；块字符的前景和背景共同组成图案。
TILE_COLORS = {
    "tile.brick": ((175, 135, 95), (68, 68, 68), (curses.COLOR_YELLOW, curses.COLOR_BLACK)),
    "tile.steel": ((218, 218, 218), (128, 128, 128), (curses.COLOR_BLACK, curses.COLOR_WHITE)),
    "tile.water": ((135, 175, 215), (0, 95, 135), (curses.COLOR_CYAN, curses.COLOR_BLUE)),
    "tile.base": ((28, 28, 28), (215, 175, 95), (curses.COLOR_BLACK, curses.COLOR_YELLOW)),
    "tile.shield": ((175, 215, 95), (0, 95, 0), (curses.COLOR_BLACK, curses.COLOR_GREEN)),
}


class Glyphs:
    """每个战场格子占两列；返回 (文本, 颜色角色)。"""

    def __init__(self, rich):
        self.rich = rich

    def tile(self, kind, x, y, phase=0):
        if not self.rich:
            return {"brick": "##", "steel": "[]", "water": "~~"}[kind], kind
        if kind == "brick":
            # 相邻两行错开砖缝，拼出砌墙的样子。
            return ("▀▘" if y % 2 else "▝▀"), "tile.brick"
        if kind == "steel":
            return "▗▖", "tile.steel"
        # 波纹随阶段左右交替，产生缓慢流动感。
        return ("~~" if (y + phase) % 2 else "~ "), "tile.water"

    def base(self):
        return "HQ", ("tile.base" if self.rich else "player")

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

    def bullet(self, direction, friendly):
        role = "player" if friendly else "enemy"
        if not self.rich:
            return "* ", role
        return {Direction.UP: "▝▘", Direction.DOWN: "▗▖",
                Direction.LEFT: "╺╸", Direction.RIGHT: "╺╸"}[direction], role

    def blast(self, fresh):
        # 击毁坦克先亮后暗；碎砖效果较短，只显示较暗的一档。
        return ("▓▓" if fresh else "▒▒") if self.rich else "**", "warning"
