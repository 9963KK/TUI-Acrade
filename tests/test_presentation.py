import unittest
from unittest.mock import Mock

import support  # noqa: F401
from arcade_kit.presentation import Presenter, synchronized_output


class PresentationTests(unittest.TestCase):
    def test_same_frame_emits_nothing(self):
        screen, draw, flush, write = Mock(), Mock(), Mock(), Mock()
        presenter = Presenter(screen, flush=flush, write=write)
        self.assertTrue(presenter.present((80, 24, "lobby"), draw))
        self.assertFalse(presenter.present((80, 24, "lobby"), draw))
        draw.assert_called_once()
        screen.noutrefresh.assert_called_once()
        flush.assert_called_once()
        write.assert_not_called()

    def test_changed_frame_and_resize_submit_once_each(self):
        draw, flush = Mock(), Mock()
        presenter = Presenter(Mock(), flush=flush)
        for state in ((80, 24, 1), (80, 24, 2), (120, 40, 2)):
            self.assertTrue(presenter.present(state, draw))
        self.assertEqual(flush.call_count, 3)

    def test_sync_brackets_only_the_terminal_submission(self):
        events = []
        screen = Mock()
        screen.noutrefresh.side_effect = lambda: events.append("stage")
        presenter = Presenter(screen, flush=lambda: events.append("flush"), write=events.append)
        presenter.sync = True
        presenter.present("first", lambda: events.append("draw"))
        self.assertEqual(events, ["draw", "stage", b"\x1b[?2026h", "flush", b"\x1b[?2026l"])

    def test_failed_flush_releases_sync_and_does_not_cache_frame(self):
        write = Mock()
        presenter = Presenter(Mock(), flush=Mock(side_effect=OSError("closed")), write=write)
        presenter.sync = True
        with self.assertRaises(OSError):
            presenter.present("new", Mock())
        write.assert_called_with(b"\x1b[?2026l")
        self.assertIsNone(presenter.previous)

    def test_terminal_capability_matrix(self):
        for env in ({"TERM_PROGRAM": "ghostty"}, {"TERM_PROGRAM": "WezTerm"},
                    {"TERM": "xterm-kitty"}, {"TERM": "foot"}, {"ARCADE_SYNC": "1"}):
            self.assertTrue(synchronized_output(env), env)
        for env in ({}, {"TERM_PROGRAM": "Apple_Terminal"}, {"TERM": "xterm-256color"},
                    {"TERM": "screen-256color", "ARCADE_SYNC": "1"},
                    {"TERM_PROGRAM": "ghostty", "TMUX": "/tmp/tmux"},
                    {"TERM_PROGRAM": "WezTerm", "STY": "screen"},
                    {"TERM_PROGRAM": "ghostty", "ARCADE_SYNC": "0"}):
            self.assertFalse(synchronized_output(env), env)
