"""Classic console colors and a small brick-letter alphabet."""

import curses

BLACK = (0, 0, 0)
COLORS = {
    "text": ((232, 232, 232), curses.COLOR_WHITE),
    "accent": ((232, 232, 232), curses.COLOR_WHITE),
    "muted": ((160, 160, 160), curses.COLOR_WHITE),
    "border": ((128, 128, 128), curses.COLOR_WHITE),
    "dim": ((64, 64, 64), curses.COLOR_WHITE),
    "player": ((248, 208, 64), curses.COLOR_YELLOW),
    "enemy": ((216, 216, 216), curses.COLOR_WHITE),
    "warning": ((248, 112, 48), curses.COLOR_YELLOW),
    "brick": ((200, 88, 40), curses.COLOR_YELLOW),
    "steel": ((216, 216, 216), curses.COLOR_WHITE),
    "water": ((64, 112, 248), curses.COLOR_BLUE),
}

# 标题字形自行绘制；每个像素占两列，不依赖图片协议或外部字体。
FONT = {
    "B": ("11110", "10001", "11110", "10001", "11110"),
    "A": ("01110", "10001", "11111", "10001", "10001"),
    "T": ("11111", "00100", "00100", "00100", "00100"),
    "L": ("10000", "10000", "10000", "10000", "11111"),
    "E": ("11111", "10000", "11110", "10000", "11111"),
    "C": ("01111", "10000", "10000", "10000", "01111"),
    "I": ("11111", "00100", "00100", "00100", "11111"),
    "Y": ("10001", "01010", "00100", "00100", "00100"),
}
