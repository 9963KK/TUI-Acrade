"""Shared test helpers: a fake curses screen and access to the bundled tank game."""

from contextlib import contextmanager
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TANK = ROOT / "games" / "tank"
for folder in (ROOT / "kit", TANK):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from arcade_kit.canvas import cell_width  # noqa: E402


class Screen:
    def __init__(self, height=24, width=80):
        self.height, self.width = height, width
        self.writes = []
        self.positions = []

    def getmaxyx(self):
        return self.height, self.width

    def addstr(self, y, x, text, style):
        assert 0 <= y < self.height
        assert x + cell_width(text) < self.width
        self.writes.append(text)
        self.positions.append((y, x, text))

    def erase(self):
        self.writes = []
        self.positions = []

    def clear(self):
        self.erase()

    def noutrefresh(self):
        pass


@contextmanager
def colors(count=256, pairs=256):
    with patch("curses.has_colors", return_value=True), patch("curses.start_color"), \
         patch("curses.COLORS", count, create=True), patch("curses.COLOR_PAIRS", pairs, create=True), \
         patch("curses.init_pair") as initialize, patch("curses.color_pair", side_effect=lambda i: i << 8):
        yield initialize
