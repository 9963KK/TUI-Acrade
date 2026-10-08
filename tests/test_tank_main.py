import curses
import io
import unittest
from unittest.mock import patch

import support  # noqa: F401
from tank_battle.__main__ import main


class MainTests(unittest.TestCase):
    def test_rejects_redirected_input_or_output(self):
        for stdin, stdout in ((False, True), (True, False)):
            with patch("sys.stdin.isatty", return_value=stdin), \
                 patch("sys.stdout.isatty", return_value=stdout), \
                 patch("sys.stderr", new_callable=io.StringIO) as error:
                self.assertEqual(main(), 1)
                self.assertIn("interactive terminal", error.getvalue())

    def test_launches_standalone_game_and_restores_wrapper(self):
        with patch("sys.stdin.isatty", return_value=True), \
             patch("sys.stdout.isatty", return_value=True), \
             patch("tank_battle.__main__.locale.setlocale"), \
             patch("tank_battle.__main__.App") as app, \
             patch("curses.wrapper", side_effect=lambda callback: callback("screen")):
            self.assertEqual(main(), 0)
        app.assert_called_once_with("screen")
        app.return_value.run.assert_called_once()

    def test_ctrl_c_exits_cleanly_and_terminal_errors_are_friendly(self):
        for exception, code in ((KeyboardInterrupt, 0), (curses.error, 1)):
            with patch("sys.stdin.isatty", return_value=True), \
                 patch("sys.stdout.isatty", return_value=True), \
                 patch("tank_battle.__main__.locale.setlocale"), \
                 patch("curses.wrapper", side_effect=exception), \
                 patch("sys.stderr", new_callable=io.StringIO) as error:
                self.assertEqual(main(), code)
                if code:
                    self.assertIn("Cannot initialize the terminal", error.getvalue())
