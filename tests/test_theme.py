import curses
import unittest
from unittest.mock import patch

import support  # noqa: F401
from arcade_kit.theme import INKS, SURFACES, Theme, basic_color, indexed_color


class ThemeTests(unittest.TestCase):
    def configure(self, colors=256, pairs=256, env=None):
        theme = Theme()
        with patch("curses.has_colors", return_value=True), patch("curses.start_color"), \
             patch("curses.COLORS", colors, create=True), patch("curses.COLOR_PAIRS", pairs, create=True), \
             patch("curses.init_pair") as initialize, patch("curses.color_pair", side_effect=lambda i: i << 8):
            theme.setup({} if env is None else env)
        return theme, initialize

    def test_indexed_quantization_preserves_gray_and_accent_family(self):
        self.assertEqual(indexed_color((20, 20, 20)), 233)
        self.assertEqual(indexed_color((36, 36, 36)), 235)
        self.assertEqual(indexed_color((122, 162, 247)), 111)
        for ink in INKS.values():
            self.assertTrue(16 <= indexed_color(ink.rgb) <= 255)

    def test_256_color_surfaces_and_roles_are_distinct(self):
        theme, initialize = self.configure()
        self.assertEqual(theme.level, "256")
        self.assertEqual(initialize.call_count, len(INKS) * len(SURFACES))
        self.assertTrue(theme.rich)
        self.assertNotEqual(theme.style("text"), theme.style("text", "panel"))
        self.assertNotEqual(theme.style("player", "field"), theme.style("player"))
        self.assertNotEqual(theme.style("player"), theme.style("enemy"))
        for call in initialize.call_args_list:
            self.assertTrue(all(0 <= color < 256 for color in call.args[1:]))

    def test_low_color_uses_only_supported_indices(self):
        for count in (8, 16):
            theme, initialize = self.configure(colors=count)
            self.assertEqual(theme.level, "basic")
            for call in initialize.call_args_list:
                self.assertTrue(all(0 <= color < count for color in call.args[1:]))

    def test_small_pair_budget_degrades_without_invalid_pairs(self):
        theme, initialize = self.configure(colors=8, pairs=8)
        self.assertEqual(initialize.call_count, 7)
        self.assertEqual(theme.style("player", "panel"), theme.style("player"))
        self.assertEqual(theme.style("steel"), 0)
        self.assertFalse(theme.rich)

    def test_ascii_override_keeps_colors(self):
        theme, _ = self.configure(env={"ARCADE_ASCII": "1"})
        self.assertEqual(theme.level, "256")
        self.assertFalse(theme.rich)
        theme, _ = self.configure(env={"TERM": "linux"})
        self.assertFalse(theme.rich)

    def test_no_color_and_colorless_terminal_keep_text_emphasis(self):
        theme, initialize = self.configure(env={"NO_COLOR": "1"})
        initialize.assert_not_called()
        self.assertEqual(theme.level, "mono")
        self.assertFalse(theme.rich)
        self.assertEqual(theme.style("enemy"), 0)
        self.assertEqual(theme.style("enemy", bold=True), curses.A_BOLD)
        with patch("curses.has_colors", return_value=False):
            theme.setup({})
        self.assertEqual(theme.level, "mono")
        theme, initialize = self.configure(colors=2)
        self.assertEqual(theme.level, "mono")
        initialize.assert_not_called()

    def test_failed_initialization_clears_partial_theme(self):
        theme = Theme()
        with patch("curses.has_colors", return_value=True), patch("curses.start_color"), \
             patch("curses.COLORS", 256, create=True), patch("curses.COLOR_PAIRS", 256, create=True), \
             patch("curses.init_pair", side_effect=curses.error("not supported")):
            theme.setup({})
        self.assertEqual(theme.styles, {})
        self.assertEqual(theme.level, "mono")


class CustomColorTests(unittest.TestCase):
    def configure(self, colors=256, pairs=256):
        theme = Theme()
        initialize = patch("curses.init_pair").start()
        self.addCleanup(patch.stopall)
        for target, value in (("curses.COLORS", colors), ("curses.COLOR_PAIRS", pairs)):
            patch(target, value, create=True).start()
        patch("curses.has_colors", return_value=True).start()
        patch("curses.start_color").start()
        patch("curses.color_pair", side_effect=lambda i: i << 8).start()
        theme.setup({})
        return theme, initialize

    def test_custom_pairs_are_cached_and_quantized(self):
        theme, initialize = self.configure()
        before = initialize.call_count
        brick = theme.custom((175, 135, 95), (68, 68, 68))
        self.assertEqual(theme.custom((175, 135, 95), (68, 68, 68)), brick)
        self.assertEqual(initialize.call_count, before + 1)
        self.assertEqual(initialize.call_args.args[1:], (indexed_color((175, 135, 95)), indexed_color((68, 68, 68))))
        self.assertEqual(theme.custom((175, 135, 95), (68, 68, 68), bold=True), brick | curses.A_BOLD)

    def test_basic_colors_honor_explicit_fallback(self):
        theme, initialize = self.configure(colors=8, pairs=64)
        theme.custom((218, 218, 218), (128, 128, 128), (curses.COLOR_BLACK, curses.COLOR_WHITE))
        self.assertEqual(initialize.call_args.args[1:], (curses.COLOR_BLACK, curses.COLOR_WHITE))
        theme.custom((205, 0, 0))
        self.assertEqual(initialize.call_args.args[1:], (curses.COLOR_RED, curses.COLOR_BLACK))
        self.assertEqual(basic_color((0, 90, 200)), curses.COLOR_BLUE)

    def test_exhausted_or_mono_budget_falls_back_safely(self):
        theme, _ = self.configure(pairs=len(INKS) * len(SURFACES) + 2)
        self.assertFalse(theme.rich)
        first = theme.custom((1, 2, 3))
        self.assertNotEqual(first, 0)
        self.assertEqual(theme.custom((4, 5, 6)), theme.style("text"))
        mono = Theme()
        self.assertEqual(mono.custom((1, 2, 3), bold=True), curses.A_BOLD)
