"""Shared curses drawing surface for the lobby and bundled Python games."""

import curses
import os
import sys
import unicodedata

from .presentation import Presenter, synchronized_output
from .theme import Theme


def cell_width(text):
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def fit(text, width):
    result = ""
    used = 0
    for char in text:
        size = cell_width(char)
        if used + size > width:
            break
        result += char
        used += size
    return result


class Canvas:
    """文字、边框、按键提示与对话框；ASCII 模式下线条也不用 Unicode，避免歧义宽度字符被画成双宽。"""

    def __init__(self, screen):
        self.screen = screen
        self.theme = Theme()
        self.presenter = Presenter(screen)
        self.surface = "canvas"

    def setup(self):
        self.screen.keypad(True)
        self.screen.nodelay(True)
        self.screen.leaveok(True)
        curses.typeahead(-1)
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        self.theme.setup()
        self.screen.bkgdset(" ", self.theme.style())
        self.presenter.sync = sys.stdout.isatty() and synchronized_output(os.environ)

    @property
    def rich(self):
        return self.theme.rich

    @property
    def rule(self):
        return "─" if self.rich else "-"

    @property
    def arrows(self):
        return "↑↓←→" if self.rich else "方向键"

    @property
    def corners(self):
        return ("┌─", "─┐", "└─", "─┘") if self.rich else ("+-", "-+", "+-", "-+")

    @property
    def bar(self):
        return ("━", "─") if self.rich else ("=", "-")

    def frame(self, heavy):
        """(上角, 下角, 竖线, 横线)"""
        if self.rich:
            return ("┏┓", "┗┛", "┃", "━") if heavy else ("╭╮", "╰╯", "│", "─")
        return ("++", "++", "|", "=" if heavy else "-")

    def paint(self, y, x, value, style):
        height, width = self.screen.getmaxyx()
        if not 0 <= y < height or not 0 <= x < width - 1:
            return
        try:
            self.screen.addstr(y, x, fit(value, width - x - 1), style)
        except curses.error:
            # 窗口可在绘制过程中缩小，下一帧会重新布局。
            pass

    def text(self, y, x, value, role="text", bold=False):
        self.paint(y, x, value, self.theme.style(role, self.surface, bold))

    def box(self, y, x, height, width, title="", role="border", heavy=False, fill=True):
        top, bottom, side, line = self.frame(heavy)
        self.text(y, x, top[0] + line * (width - 2) + top[1], role)
        for row in range(1, height - 1):
            if fill:
                self.text(y + row, x, side + " " * (width - 2) + side, role)
            else:
                self.text(y + row, x, side, role)
                self.text(y + row, x + width - 1, side, role)
        self.text(y + height - 1, x, bottom[0] + line * (width - 2) + bottom[1], role)
        if title:
            self.text(y, x + 3, " " + title + " ", "accent", True)

    def hints(self, y, x, items):
        # 按键用正文色，说明用弱化色，便于一眼扫到操作。
        for key, label in items:
            self.text(y, x, key, "text", True)
            x += cell_width(key) + 1
            self.text(y, x, label, "muted")
            x += cell_width(label) + 3

    def dialog(self, y, x, title, lines, width=54):
        self.surface = "panel"
        self.box(y, x, len(lines) * 2 + 3, width, title)
        for i, line in enumerate(lines):
            self.text(y + 2 + i * 2, x + 3, line, "text")
        self.surface = "canvas"

    def centered_dialog(self, title, lines, width=54):
        height, screen_width = self.screen.getmaxyx()
        self.dialog((height - len(lines) * 2 - 3) // 2, (screen_width - width) // 2, title, lines, width)
