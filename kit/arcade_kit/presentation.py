"""Change-driven, bounded frame submission for a single curses surface."""

import curses
import os
import sys


def synchronized_output(env):
    term = env.get("TERM", "")
    if env.get("TMUX") or env.get("STY") or term.startswith(("screen", "tmux")):
        return False
    override = env.get("ARCADE_SYNC")
    if override in ("0", "1"):
        return override == "1"
    # 保守识别；未知终端以及 Apple Terminal 使用正常的 curses 差分提交。
    return (env.get("TERM_PROGRAM", "").lower() in ("ghostty", "wezterm")
            or term in ("xterm-kitty", "foot", "foot-extra"))


class Presenter:
    def __init__(self, screen, flush=None, write=None):
        self.screen = screen
        self.flush = curses.doupdate if flush is None else flush
        self.write = self._write if write is None else write
        self.sync = False
        self.previous = None

    @staticmethod
    def _write(data):
        sys.stdout.flush()
        os.write(sys.stdout.fileno(), data)

    def present(self, signature, draw):
        if signature == self.previous:
            return False
        draw()
        # 先完整合成画面，再一次提交；不产生等待写出的帧队列。
        self.screen.noutrefresh()
        if self.sync:
            self.write(b"\x1b[?2026h")
        try:
            self.flush()
        finally:
            if self.sync:
                self.write(b"\x1b[?2026l")
        self.previous = signature
        return True
