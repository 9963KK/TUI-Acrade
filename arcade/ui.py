"""Gallery lobby: list games from their manifests and hand the terminal to the chosen one."""

import curses
import os
import signal
import sys
import time

from arcade_kit.canvas import Canvas, cell_width

from . import catalog
from .launcher import launch, prepare

# 画廊每页 2 行 3 列；不足一页时补空展位。
COLUMNS, PAGE = 3, 6
MOVES = {curses.KEY_UP: -COLUMNS, curses.KEY_DOWN: COLUMNS, curses.KEY_LEFT: -1, curses.KEY_RIGHT: 1,
         ord("w"): -COLUMNS, ord("s"): COLUMNS, ord("a"): -1, ord("d"): 1}
# 玩家用 Ctrl-C 结束游戏属于正常离开，不提示异常。
INTERRUPTED = (-signal.SIGINT, 128 + signal.SIGINT)
NETWORK = {"optional": "部分功能联网", "required": "需要联网"}


class App(Canvas):
    MIN_WIDTH = 80
    MIN_HEIGHT = 24

    def __init__(self, screen, games=None, launcher=None, problems=()):
        super().__init__(screen)
        if games is None:
            games, problems = catalog.load()
        self.games = list(games)
        # 无法解析的清单不上架，只在标题栏提示数量，避免一份坏清单拖垮整个大厅。
        self.problems = list(problems)
        self.launcher = launcher or self.run_game
        self.selection = 0
        self.help = False
        self.notice = None
        self.running = True

    @property
    def slots(self):
        return max(PAGE, -(-len(self.games) // PAGE) * PAGE)

    def handle(self, key):
        if key == -1 or key == curses.KEY_RESIZE:
            return
        if 65 <= key <= 90:
            key += 32
        if self.notice:
            if key in (10, 13, 27, ord(" "), ord("q")):
                self.notice = None
            return
        height, width = self.screen.getmaxyx()
        if height < self.MIN_HEIGHT or width < self.MIN_WIDTH:
            if key in (ord("q"), 27):
                self.running = False
            return
        if self.help:
            if key in (27, ord("?"), ord("h"), ord("q"), 10, 13):
                self.help = False
            return
        if key in (ord("?"), ord("h")):
            self.help = True
        elif key in (ord("q"), 27):
            self.running = False
        elif key in MOVES:
            delta = MOVES[key]
            target = self.selection + delta
            # 左右只在同一行内移动，不从行尾折到下一行。
            if 0 <= target < self.slots and (abs(delta) == COLUMNS or target // COLUMNS == self.selection // COLUMNS):
                self.selection = target
        elif key in (10, 13, ord(" ")) and self.selection < len(self.games):
            self.open(self.games[self.selection])

    def open(self, entry):
        if entry.issue:
            self.notice = ("无法启动", [f"{entry.name}：{entry.issue}", "Enter 关闭"])
            return
        height, width = self.screen.getmaxyx()
        columns, rows = entry.terminal.columns, entry.terminal.rows
        if width < columns or height < rows:
            self.notice = ("窗口太小", [f"{entry.name}需要 {columns} x {rows}，当前 {width} x {height}。",
                                        "放大窗口后再进入    Enter 关闭"])
            return
        code, error = self.launcher(entry)
        if error:
            self.notice = ("无法启动", [f"{entry.name}：{error}", "Enter 关闭"])
        elif code not in (0, *INTERRUPTED):
            # 退出码只代表进程是否正常结束，不代表游戏胜负。
            self.notice = ("游戏异常退出", [f"{entry.name}以代码 {code} 结束。", "Enter 关闭"])

    def run_game(self, entry):
        env, problem = prepare(entry)
        if problem:
            return None, problem
        # 交出终端：游戏在同一个终端窗口里前台运行，退出后再恢复大厅。
        curses.endwin()
        try:
            return launch(entry, env)
        finally:
            self.resume()

    def resume(self):
        try:
            columns, lines = os.get_terminal_size(sys.stdout.fileno())
            if curses.is_term_resized(lines, columns):
                curses.resizeterm(lines, columns)
        except (OSError, curses.error):
            pass
        # 游戏可能画满了整屏；清空后整帧重画大厅。
        self.screen.clear()
        self.presenter.previous = None

    def frame_signature(self):
        return self.screen.getmaxyx(), self.selection, self.help, self.notice, len(self.games)

    def draw(self):
        return self.presenter.present(self.frame_signature(), self._draw)

    def _draw(self):
        self.surface = "canvas"
        self.screen.erase()
        height, width = self.screen.getmaxyx()
        if height < self.MIN_HEIGHT or width < self.MIN_WIDTH:
            self.text(1, 1, "窗口太小。", "warning", True)
            self.text(3, 1, f"游戏厅需要 80 x 24，当前 {width} x {height}")
            self.text(5, 1, "放大窗口即可继续；Q 退出。")
            return
        self.draw_lobby(height, width)
        if self.notice:
            self.centered_dialog(*self.notice)
        elif self.help:
            self.centered_dialog("游戏厅说明", [
                f"{self.arrows} / WASD：在展位之间移动", "Enter：进入选中的游戏    Q：退出",
                "游戏在当前终端中运行，退出后回到这里。", "Enter / Esc 关闭说明"])

    def draw_lobby(self, height, width):
        x0, oy = max(0, (width - 80) // 2) + 1, max(0, (height - 24) // 2)
        self.text(oy, x0, "TUI ARCADE", "accent", True)
        self.text(oy, x0 + 12, "终端游戏厅", "text", True)
        count = f"已收录 {len(self.games)} 款"
        if self.problems:
            count += f" · {len(self.problems)} 份清单无效"
        if self.slots > PAGE:
            count += f" · 第 {self.selection // PAGE + 1}/{self.slots // PAGE} 页"
        self.text(oy, x0 + 78 - cell_width(count), count, "muted")
        self.text(oy + 1, x0, self.rule * 78, "border")
        first = self.selection // PAGE * PAGE
        for slot in range(first, first + PAGE):
            row, column = divmod(slot - first, COLUMNS)
            self.draw_card(oy + 3 + row * 8, x0 + column * 27, slot)
        self.text(oy + 18, x0, self.rule * 78, "border")
        if self.selection < len(self.games):
            entry = self.games[self.selection]
            self.text(oy + 19, x0, entry.name, "text", True)
            self.text(oy + 19, x0 + cell_width(entry.name) + 2, entry.presentation.name_en, "muted")
            status, role = self.status(entry, height, width)
            self.text(oy + 19, x0 + 78 - cell_width(status), status, role)
            self.text(oy + 20, x0, entry.description, "text")
            # 标签做成浮起的小胶囊，与说明文字区分层次；联网需求由平台统一展示。
            x = x0
            self.surface = "panel"
            for tag in (*entry.presentation.tags, *filter(None, [NETWORK.get(entry.network)])):
                self.text(oy + 21, x, f" {tag} ", "muted")
                x += cell_width(tag) + 3
            self.surface = "canvas"
        else:
            self.text(oy + 19, x0, f"{self.selection + 1:02} 号展位", "muted", True)
            self.text(oy + 20, x0, "暂无游戏", "dim")
        self.hints(oy + 23, x0, ((self.arrows, "选择"), ("Enter", "开始"), ("?", "帮助"), ("Q", "退出")))

    def draw_card(self, y, x, slot):
        selected = slot == self.selection
        entry = self.games[slot] if slot < len(self.games) else None
        number = f"{slot + 1:02}"
        if entry is None:
            if selected:
                self.box(y, x, 6, 24, role="accent", heavy=True)
            else:
                # 空展位只画四角，像墙上的空画框，不与已上架的游戏抢视线。
                corners = self.corners
                for row, (left, right) in ((y, corners[:2]), (y + 5, corners[2:])):
                    self.text(row, x, left, "dim")
                    self.text(row, x + 22, right, "dim")
            self.text(y + 6, x + 1, number, "accent" if selected else "dim")
            return
        self.box(y, x, 6, 24, role="accent" if selected else "border", heavy=selected, fill=False)
        self.draw_cover(y + 1, x + 1, entry)
        # 铭牌只放编号和名称，英文名与简介留给下方说明卡；不能运行的游戏名称变暗。
        self.text(y + 6, x + 1, number, "accent" if selected else "muted")
        self.text(y + 6, x + 4, entry.name, "muted" if entry.issue else "accent" if selected else "text", True)

    def status(self, entry, height, width):
        """说明卡右上角：不能运行的原因 > 窗口要求 > 终端能力提示 > 版本与来源。能力提示不阻止启动。"""
        if entry.issue:
            return entry.issue, "warning"
        terminal = entry.terminal
        if width < terminal.columns or height < terminal.rows:
            return f"需要 {terminal.columns} x {terminal.rows} 窗口", "warning"
        colors = {"mono": 0, "basic": 16, "256": 256}.get(self.theme.level, 0)
        if terminal.color == "truecolor" and os.environ.get("COLORTERM") not in ("truecolor", "24bit"):
            return "建议使用真彩色终端", "warning"
        if terminal.color in ("16", "256") and colors < int(terminal.color):
            return f"建议使用 {terminal.color} 色终端", "warning"
        if terminal.unicode == "required" and not self.rich:
            return "需要 Unicode 字形", "warning"
        return ("开发来源 · " if entry.source == "dev" else "") + f"v{entry.version}", "muted"

    def draw_cover(self, y, x, entry):
        look = entry.presentation
        blank = self.theme.custom((225, 225, 225), look.cover_background)
        for row in range(catalog.COVER_HEIGHT):
            self.paint(y + row, x, " " * catalog.COVER_WIDTH * 2, blank)
        for row, line in enumerate(look.cover):
            for column, key in enumerate(line):
                cell = look.cells.get(key)
                if cell:
                    style = self.theme.custom(cell.foreground, cell.background or look.cover_background,
                                              bold=cell.bold)
                    self.paint(y + row, x + column * 2, cell.text if self.rich else cell.ascii, style)

    def run(self, start=None):
        self.setup()
        if start is not None:
            self.open(start)
        while self.running:
            # 限制每帧输入量，避免大量粘贴导致主循环失去响应。
            for _ in range(32):
                key = self.screen.getch()
                if key == -1:
                    break
                self.handle(key)
                if not self.running:
                    break
            self.draw()
            time.sleep(1 / 30)
