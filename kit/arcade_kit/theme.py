"""Semantic GrokNight-inspired colors, adapted to curses capabilities."""

import curses
from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Ink:
    rgb: tuple
    basic: int


# 颜色统一按用途命名，场景代码不再依赖 color-pair 编号。
INKS = {
    "text": Ink((225, 225, 225), curses.COLOR_WHITE),
    "muted": Ink((150, 150, 150), curses.COLOR_WHITE),
    "border": Ink((80, 80, 88), curses.COLOR_WHITE),
    "accent": Ink((122, 162, 247), curses.COLOR_CYAN),
    "player": Ink((158, 206, 106), curses.COLOR_GREEN),
    "enemy": Ink((247, 118, 142), curses.COLOR_RED),
    "warning": Ink((224, 175, 104), curses.COLOR_YELLOW),
    "water": Ink((122, 162, 247), curses.COLOR_BLUE),
    "brick": Ink((180, 145, 108), curses.COLOR_YELLOW),
    "steel": Ink((150, 150, 150), curses.COLOR_WHITE),
    "dim": Ink((78, 78, 78), curses.COLOR_WHITE),
}
SURFACES = {"canvas": (20, 20, 20), "panel": (36, 36, 36), "field": (28, 28, 28)}
# 语义色之外，为游戏图案与大厅封面预留的按需色对数量；不足时整体改用 ASCII 字形。
CUSTOM_PAIRS = 32
BASIC_RGB = {curses.COLOR_BLACK: (0, 0, 0), curses.COLOR_RED: (205, 0, 0), curses.COLOR_GREEN: (0, 205, 0),
             curses.COLOR_YELLOW: (205, 205, 0), curses.COLOR_BLUE: (0, 0, 238), curses.COLOR_MAGENTA: (205, 0, 205),
             curses.COLOR_CYAN: (0, 205, 205), curses.COLOR_WHITE: (229, 229, 229)}


def indexed_color(rgb):
    # ANSI 前 16 色由用户自定义；只从稳定的色立方和灰阶中取最近值。
    levels = (0, 95, 135, 175, 215, 255)
    palette = [(16 + r * 36 + g * 6 + b, (red, green, blue))
               for r, red in enumerate(levels) for g, green in enumerate(levels)
               for b, blue in enumerate(levels)]
    palette += [(232 + i, (8 + i * 10,) * 3) for i in range(24)]
    return min(palette, key=lambda entry: sum((a - b) ** 2 for a, b in zip(rgb, entry[1])))[0]


def basic_color(rgb):
    return min(BASIC_RGB, key=lambda index: sum((a - b) ** 2 for a, b in zip(rgb, BASIC_RGB[index])))


class Theme:
    def __init__(self):
        self.styles = {}
        self.custom_styles = {}
        self.level = "mono"
        self.rich = False
        self.next_pair = 1
        self.pair_limit = 0

    def setup(self, env=None):
        env = os.environ if env is None else env
        self.styles.clear()
        self.custom_styles.clear()
        self.level = "mono"
        self.rich = False
        self.next_pair = 1
        self.pair_limit = 0
        if env.get("NO_COLOR") or not curses.has_colors():
            return
        try:
            curses.start_color()
            count = curses.COLORS
            if count < 8:
                return
            indexed = count >= 256
            self.level = "256" if indexed else "basic"
            self.pair_limit = curses.COLOR_PAIRS
            for surface, background in SURFACES.items():
                for role, ink in INKS.items():
                    if self.next_pair >= self.pair_limit:
                        continue
                    foreground = indexed_color(ink.rgb) if indexed else ink.basic
                    bg = indexed_color(background) if indexed else curses.COLOR_BLACK
                    curses.init_pair(self.next_pair, foreground, bg)
                    self.styles[role, surface] = curses.color_pair(self.next_pair)
                    self.next_pair += 1
            # 色对不足时块字符无法区分敌我与图案，改用 ASCII 字形；Linux 控制台字体缺少块字符。
            self.rich = (self.next_pair + CUSTOM_PAIRS <= self.pair_limit
                         and env.get("ARCADE_ASCII") != "1" and env.get("TERM") != "linux")
        except curses.error:
            # 极少数终端声明支持颜色但拒绝初始化，整体退回单色。
            self.styles.clear()
            self.level = "mono"
            self.rich = False

    def style(self, role="text", surface="canvas", bold=False):
        style = self.styles.get((role, surface), self.styles.get((role, "canvas"), 0))
        if bold:
            style |= curses.A_BOLD
        return style

    def custom(self, foreground, background=None, basic=None, bold=False, surface="canvas"):
        """按 RGB 取得任意前景/背景色；basic 可显式指定 8 色终端下的 (前景, 背景)。"""
        bold_flag = curses.A_BOLD if bold else 0
        if self.level == "mono":
            return bold_flag
        background = SURFACES[surface] if background is None else background
        key = (foreground, background, basic)
        if key not in self.custom_styles:
            if self.next_pair >= self.pair_limit:
                return self.style("text", surface, bold)
            if self.level == "256":
                pair = indexed_color(foreground), indexed_color(background)
            else:
                pair = basic or (basic_color(foreground), basic_color(background))
            try:
                curses.init_pair(self.next_pair, *pair)
            except curses.error:
                return self.style("text", surface, bold)
            self.custom_styles[key] = curses.color_pair(self.next_pair)
            self.next_pair += 1
        return self.custom_styles[key] | bold_flag
