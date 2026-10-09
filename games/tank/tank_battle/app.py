"""Standalone Battle City menus, campaign and curses presentation."""

import curses
import math
import os
import time

from arcade_kit.canvas import Canvas, cell_width

from .classic import BLACK, COLORS, FONT
from .glyphs import TILE_COLORS, Glyphs
from .levels import KINDS, LEVELS
from .rules import Battle, Direction
from .storage import read_best, save_record

MOVES = {curses.KEY_UP: Direction.UP, curses.KEY_RIGHT: Direction.RIGHT,
         curses.KEY_DOWN: Direction.DOWN, curses.KEY_LEFT: Direction.LEFT,
         ord("w"): Direction.UP, ord("d"): Direction.RIGHT,
         ord("s"): Direction.DOWN, ord("a"): Direction.LEFT}
REASONS = {"All enemy tanks eliminated!": "敌军已全部消灭！",
           "HQ was destroyed.": "基地被摧毁。",
           "No tanks remaining.": "坦克全部损失。",
           "No safe respawn position.": "没有安全的复活位置。"}
BONUSES = {"star": "*", "tank": "+", "helmet": "H", "clock": "T", "grenade": "G", "shovel": "S"}


class App(Canvas):
    MIN_WIDTH = 80
    MIN_HEIGHT = 24

    def __init__(self, screen, env=None):
        super().__init__(screen)
        env = os.environ if env is None else env
        self.leave = "退出并返回大厅" if env.get("TUI_ARCADE_LAUNCHER") == "1" else "退出游戏"
        self.running = True
        self.best = read_best()
        self.has_campaign = False
        self.start(1)
        self.has_campaign = False
        self.mode = "title"

    def start(self, level=1, *, checkpoint=None):
        """新战役从选定关卡开始；逐关继续和重试使用明确的关前快照。"""
        lives, score, power = checkpoint or (3, 0, 0)
        self.game = Battle(level=level, lives=lives, score=score, power=power)
        self.checkpoint = (lives, score, power)
        self.saved = False
        self.save_failed = False
        self.preserved = None
        self.has_campaign = True
        self.mode = "playing"
        self.menu_index = 0
        self.selection = level - 1
        self.return_mode = "title"
        self.confirm_return_mode = "title"
        self.pending = None

    def retry(self):
        self.start(self.game.level_number, checkpoint=self.checkpoint)

    def next_level(self):
        if self.game.result != "win" or self.game.level_number >= len(LEVELS):
            return
        self.start(self.game.level_number + 1,
                   checkpoint=(self.game.lives, self.game.score, self.game.power))

    def resume(self):
        self.mode = "result" if self.game.result else "playing"
        self.game.paused = False
        self.menu_index = 0

    def title(self):
        self.mode = "title"
        self.menu_index = 0

    def _style(self, role="text", bold=False):
        color, basic = COLORS.get(role, COLORS["text"])
        return self.theme.custom(color, BLACK, (basic, curses.COLOR_BLACK), bold)

    def setup(self):
        super().setup()
        self.screen.bkgdset(" ", self._style())

    def text(self, y, x, value, role="text", bold=False):
        self.paint(y, x, value, self._style(role, bold))

    def open_levels(self):
        self.return_mode = self.mode
        self.mode = "select"
        self.selection = self.game.level_number - 1

    def confirm(self, action):
        self.confirm_return_mode = self.mode
        self.pending = action
        self.mode = "confirm"

    def menu_items(self):
        if self.mode == "title":
            items = [("1 PLAYER  单人战役", "new")]
            if self.has_campaign:
                items.append(("继续当前战役", "resume"))
            return items + [("选择关卡", "select"), ("操作说明", "help"), (self.leave, "quit")]
        if self.mode == "pause":
            return [("继续游戏", "resume"), ("重试本关", "retry"), ("选择关卡", "select"),
                    ("返回游戏主菜单", "title"), ("操作说明", "help"), (self.leave, "quit")]
        if self.mode == "result":
            items = []
            if self.game.result == "win" and self.game.level_number < len(LEVELS):
                items.append(("继续：下一关", "next"))
            elif self.game.result == "lose":
                items.append(("重试本关", "retry"))
            else:
                items.append(("返回游戏主菜单", "title"))
            if self.game.result != "lose":
                items.append(("重试本关", "retry"))
            if self.game.result != "win" or self.game.level_number < len(LEVELS):
                items.append(("返回游戏主菜单", "title"))
            return items + [("选择关卡", "select"), (self.leave, "quit")]
        return []

    def activate(self, action):
        if action == "new":
            if self.has_campaign:
                self.confirm("new")
            else:
                self.start(1)
        elif action == "resume":
            self.resume()
        elif action == "retry":
            if self.game.result:
                self.retry()
            else:
                self.confirm("retry")
        elif action == "next":
            self.next_level()
        elif action == "title":
            self.title()
        elif action == "select":
            self.open_levels()
        elif action == "help":
            self.return_mode = self.mode
            self.mode = "help"
        elif action == "quit":
            self.confirm("quit")

    def handle(self, key):
        if key == -1 or key == curses.KEY_RESIZE:
            return
        if 65 <= key <= 90:
            key += 32
        height, width = self.screen.getmaxyx()
        if height < self.MIN_HEIGHT or width < self.MIN_WIDTH:
            if key in (ord("q"), 27):
                self.running = False
            return
        if self.mode == "confirm":
            if key in (10, 13, ord("y")):
                action = self.pending
                if action == "quit":
                    self.running = False
                elif action == "retry":
                    self.retry()
                elif action == "new":
                    self.start(1)
                elif action == "stage":
                    self.start(self.selection + 1)
            elif key in (27, ord("n"), ord("q")):
                self.mode = self.confirm_return_mode
            return
        if self.mode == "help":
            if key in (27, ord("?"), ord("h"), ord("q"), 10, 13):
                self.mode = self.return_mode
            return
        if self.mode == "select":
            if key in (curses.KEY_UP, curses.KEY_LEFT, ord("w"), ord("a")):
                self.selection = max(0, self.selection - 1)
            elif key in (curses.KEY_DOWN, curses.KEY_RIGHT, ord("s"), ord("d")):
                self.selection = min(len(LEVELS) - 1, self.selection + 1)
            elif key == curses.KEY_HOME:
                self.selection = 0
            elif key == curses.KEY_END:
                self.selection = len(LEVELS) - 1
            elif key in (curses.KEY_PPAGE, curses.KEY_NPAGE):
                self.selection = max(0, min(len(LEVELS) - 1,
                                           self.selection + (-5 if key == curses.KEY_PPAGE else 5)))
            elif key in (10, 13):
                if self.has_campaign:
                    self.confirm("stage")
                else:
                    self.start(self.selection + 1)
            elif key in (27, ord("q"), ord("l")):
                self.mode = self.return_mode
            return
        if key in (ord("?"), ord("h")):
            self.activate("help")
            return
        if key == ord("l"):
            self.open_levels()
            return
        if key == ord("q"):
            self.confirm("quit")
            return
        if self.mode in ("title", "pause", "result"):
            items = self.menu_items()
            if key in (curses.KEY_UP, ord("w")):
                self.menu_index = (self.menu_index - 1) % len(items)
            elif key in (curses.KEY_DOWN, ord("s")):
                self.menu_index = (self.menu_index + 1) % len(items)
            elif key in (10, 13, ord(" "), ord("j")):
                self.activate(items[self.menu_index][1])
            elif self.mode == "pause" and key in (27, ord("p")):
                self.resume()
            elif self.mode == "result" and key == ord("r"):
                self.retry()
            elif self.mode == "title" and key == 27:
                self.confirm("quit")
            return
        if key in (27, ord("p")):
            self.mode = "pause"
            self.game.paused = True
            self.menu_index = 0
        elif key in MOVES:
            self.game.command(MOVES[key])
        elif key in (ord(" "), ord("j")):
            self.game.command("fire")
        elif key == ord("f"):
            self.game.command("auto")
        if self.game.result:
            self.update(0)

    def update(self, seconds):
        height, width = self.screen.getmaxyx()
        if height < self.MIN_HEIGHT or width < self.MIN_WIDTH:
            if self.mode == "playing":
                self.game.paused = True
                self.mode = "pause"
                self.menu_index = 0
            return
        if self.mode == "playing":
            self.game.advance(seconds)
            if self.game.result:
                self.mode = "result"
                self.menu_index = 0
        if self.has_campaign and self.game.result and not self.saved:
            self.best = max(self.best, self.game.score)
            saved, preserved = save_record(self.best)
            self.save_failed = not saved
            self.saved = True
            self.preserved = preserved.name if preserved else None

    def frame_signature(self):
        game = self.game
        tank_view = lambda tank: (tank.x, tank.y, tank.direction, tank.hp, tank.carries_bonus)
        return (self.screen.getmaxyx(), self.mode, self.menu_index, self.selection, self.pending,
                self.has_campaign, self.best, self.save_failed, self.preserved, game.level_number,
                int(game.elapsed), game.lives, game.kills, game.score, game.power, game.result,
                game.reason, game.paused, game.auto_fire, math.ceil(game.shield),
                math.ceil(game.freeze), math.ceil(game.fortify),
                tank_view(game.player), tuple(map(tank_view, game.enemies)),
                tuple((b.x, b.y, b.friendly, b.direction) for b in game.bullets),
                tuple(game.tiles.items()), int(game.elapsed * 2) % 2,
                tuple((p.x, p.y, p.kind) for p in game.powerups),
                tuple((x, y, life > 0.15) for x, y, life in game.effects))

    def draw(self):
        return self.presenter.present(self.frame_signature(), self._draw)

    def origin(self):
        height, width = self.screen.getmaxyx()
        return max(0, (width - 80) // 2), max(0, (height - 24) // 2)

    def draw_cursor(self, y, x, tall=True):
        if self.rich and tall:
            # 炮塔、炮管与带轮子的履带分开绘制，避免糊成一个色块。
            self.text(y, x + 1, "▄▄━━", "player", True)
            track = (192, 144, 32)
            edge = self.theme.custom(track, BLACK, (curses.COLOR_YELLOW, curses.COLOR_BLACK))
            wheels = self.theme.custom(BLACK, track, (curses.COLOR_BLACK, curses.COLOR_YELLOW))
            self.paint(y + 1, x, "▟", edge)
            self.paint(y + 1, x + 1, "●●●", wheels)
            self.paint(y + 1, x + 4, "▙", edge)
        else:
            self.text(y, x, self.glyphs.tank(Direction.RIGHT, True)[0], "player", True)

    def draw_page(self, title, lines):
        ox, oy = self.origin()
        self.text(oy, ox + 2, "TANK BATTLE", "muted")
        self.text(oy + 2, ox + (80 - cell_width(title)) // 2, title, "text", True)
        width = min(68, max(map(cell_width, lines), default=0))
        x = ox + (80 - width) // 2
        first = max(4, (24 - len(lines) * 2) // 2)
        for i, line in enumerate(lines):
            if line.startswith("> "):
                self.draw_cursor(oy + first + i * 2, x - 6)
                line = "  " + line[2:]
            self.text(oy + first + i * 2, x, line)

    @property
    def glyphs(self):
        return Glyphs(self.rich)

    def cell(self, y, x, glyph):
        text, role = glyph
        if role in TILE_COLORS:
            foreground, background, basic = TILE_COLORS[role]
            style = self.theme.custom(foreground, background, basic, role in ("tile.base", "tile.shield"))
        else:
            style = self._style(role, role in ("player", "enemy"))
        self.paint(y, x, text, style)

    def _draw(self):
        self.surface = "canvas"
        self.screen.erase()
        height, width = self.screen.getmaxyx()
        if height < self.MIN_HEIGHT or width < self.MIN_WIDTH:
            self.text(1, 1, "窗口太小，游戏已暂停。", "warning", True)
            self.text(3, 1, f"需要 80 x 24，当前 {width} x {height}")
            self.text(5, 1, f"放大窗口后按 P 继续；Q {self.leave}。")
            return
        ox, oy = self.origin()
        if self.mode == "title":
            self.draw_title()
        elif self.mode == "playing":
            self.text(oy, ox + 2, "TANK BATTLE", "text", True)
            self.text(oy + 1, ox + 2, f"1P-{self.game.score:06d}     HI-{self.best:06d}")
            self.draw_battle(ox, oy)
        elif self.mode == "select":
            self.draw_levels()
        elif self.mode == "help":
            self.draw_page("出击手册", [
                "WASD / 方向键：移动，空格 / J：开炮",
                "P / Esc：暂停菜单，F：切换自动连射",
                "每关消灭 20 辆敌军；基地失守即失败。",
                "生命、总分、升级跨关保留；每万分加 1 命。",
                "砖墙可破坏；三级升级可击碎钢墙。",
                "水域可射穿；森林遮蔽；冰面会滑行。",
                "* 升级  + 加命  H 护盾  T 冻结  G 炸弹  S 护城",
                "Enter / Esc 返回；Q 在此只关闭说明。"])
        elif self.mode == "confirm":
            title = "确认退出" if self.pending == "quit" else "确认重新开始"
            message = "结束游戏？已结算的最高分会保留。" if self.pending == "quit" else "放弃当前关卡进度并重新开始？"
            self.draw_page(title, [message, "Enter / Y 确认    Esc / N 取消"])
        elif self.mode in ("pause", "result"):
            self.draw_menu()

    def draw_title(self):
        height, width = self.screen.getmaxyx()
        compact = height < 30
        page_height = 24 if compact else 28
        oy = (height - page_height) // 2
        record = f"HI-{self.best:06d}"
        self.text(oy, (width - cell_width(record)) // 2, record)
        for word, top in (("BATTLE", 2), ("CITY", 8)):
            left = (width - (len(word) * 6 - 1) * 2) // 2
            for row in range(5):
                for letter, char in enumerate(word):
                    for column, pixel in enumerate(FONT[char][row]):
                        if pixel != "1":
                            continue
                        color = (200, 80, 32) if (row + column) % 2 else (248, 144, 64)
                        style = self.theme.custom(color, BLACK, (curses.COLOR_YELLOW, curses.COLOR_BLACK), True)
                        self.paint(oy + top + row, left + (letter * 6 + column) * 2,
                                   "██" if self.rich else "##", style)
        items = self.menu_items()
        menu_width = max(cell_width(label) for label, _ in items)
        left = (width - menu_width) // 2
        for i, (label, _) in enumerate(items):
            y = oy + 16 + i * (1 if compact else 2)
            if i == self.menu_index:
                self.draw_cursor(y, left - 7, tall=not compact)
            self.text(y, left, label, "text", i == self.menu_index)
        self.text(oy + page_height - 2, (width - 11) // 2, "TANK BATTLE", "muted")
        hint = "W S / 方向键选择   Enter / J 确认   经典 35 关"
        self.text(oy + page_height - 1, (width - cell_width(hint)) // 2, hint, "muted")

    def draw_menu(self):
        title = {"pause": "暂停 / PAUSED", "result": "战斗结束"}[self.mode]
        if self.mode == "pause":
            title += f" · 第 {self.game.level_number:02} 关"
        lines = []
        if self.mode == "result":
            if self.game.result == "win":
                title = "全部 35 关完成" if self.game.level_number == len(LEVELS) else "任务完成"
            counts = self.game.kill_counts
            lines = [REASONS.get(self.game.reason, self.game.reason),
                     "  ".join(f"{label}{counts[kind]:02}" for label, kind in zip(("普", "快", "火", "甲"), KINDS))
                     + f"  总分 {self.game.score:06d}"]
        lines += [f"{'>' if index == self.menu_index else ' '} {label}"
                  for index, (label, _) in enumerate(self.menu_items())]
        lines += ["W S / 方向键选择，Enter / J 确认"]
        self.draw_page(title, lines)
        if self.mode == "result":
            ox, oy = self.origin()
            feedback = ("记录保存失败，本局仍可继续操作。" if self.save_failed
                        else f"原记录无法读取，已另存为 {self.preserved}" if self.preserved
                        else f"本地最高分 {self.best:06d}")
            self.text(oy + 22, ox + 3, feedback, "warning" if self.save_failed else "muted")

    def draw_levels(self):
        first = max(0, min(self.selection - 2, len(LEVELS) - 5))
        lines = [f"{'>' if index == self.selection else ' '} {index + 1:02}  {level.name}    敌军 {level.target}"
                 for index, level in enumerate(LEVELS) if first <= index < first + 5]
        lines += [LEVELS[self.selection].description, "方向键选择，PgUp/PgDn 翻页，Enter 开始，Esc 返回"]
        self.draw_page(f"选择关卡 {self.selection + 1}/{len(LEVELS)}", lines)

    def draw_battle(self, ox, oy):
        game, glyphs = self.game, self.glyphs
        # 灰色直角边框围住黑色战场，独立于标题和菜单画面。
        frame_style = self.theme.custom((128, 128, 128), (128, 128, 128),
                                        (curses.COLOR_WHITE, curses.COLOR_WHITE))
        for row in range(15):
            if row in (0, 14):
                self.paint(oy + 3 + row, ox + 2, " " * 54 if self.theme.level != "mono" else "=" * 54, frame_style)
            else:
                self.paint(oy + 3 + row, ox + 2, " " if self.theme.level != "mono" else "|", frame_style)
                self.paint(oy + 3 + row, ox + 55, " " if self.theme.level != "mono" else "|", frame_style)
        fx, fy = ox + 3, oy + 4
        for y in range(0, game.HEIGHT, 4):
            for x in range(0, game.WIDTH, 2):
                self.cell(fy + y // 4, fx + x, glyphs.terrain(game.tiles, x, y, int(game.elapsed * 2) % 2))
        self.cell(fy + game.BASE[1] // 4, fx + game.BASE[0], (" HQ ", "tile.base" if self.rich else "player"))
        for bonus in game.powerups:
            self.cell(fy + bonus.y // 4, fx + bonus.x, (f"[{BONUSES[bonus.kind]}]", "warning"))
        for tank in [*game.enemies, game.player]:
            friendly = tank is game.player
            # 森林中的敌军隐藏车身，开火时仍可通过炮弹发现。
            if not friendly and all(game.tiles.get((tank.x + dx, tank.y + dy)) == "forest"
                                    for dx in range(4) for dy in range(4)):
                continue
            text, role = glyphs.tank(tank.direction, friendly, friendly and game.shield > 0)
            if not friendly and tank.kind == "armor" and not self.rich:
                text = f"A{tank.hp}"
            if tank.carries_bonus:
                role = "warning"
            self.cell(fy + tank.y // 4, fx + tank.x, (" " + text + " ", role))
        for bullet in game.bullets:
            self.cell(fy + bullet.y // 4, fx + bullet.x, ("*", "player" if bullet.friendly else "enemy"))
        for x, y, life in game.effects:
            self.cell(fy + y // 4, fx + x, ("*", "warning"))
        self.text(oy + 19, ox + 3, f"STAGE {game.level_number:02}/35  {game.level.name}", "accent")
        effects = [("护盾", game.shield), ("冻结", game.freeze), ("护城", game.fortify)]
        status = [f"{label} {math.ceil(seconds)}s" for label, seconds in effects if seconds > 0]
        if game.auto_fire:
            status.append("连射 ON")
        self.text(oy + 21, ox + 3, "   ".join(status), "muted")
        self.draw_hud(game, glyphs, ox + 60, oy)
        self.hints(oy + 23, ox + 2, (("WASD", "移动"), ("空格/J", "射击"), ("P", "菜单"),
                                     ("F", "连射"), ("L", "选关"), ("?", "帮助"), ("Q", "退出")))

    def draw_hud(self, game, glyphs, side, oy):
        self.text(oy + 3, side, "敌军", "muted")
        self.text(oy + 4, side, f"剩余 {game.TARGET - game.kills:02}", "text", True)
        for index in range(game.TARGET):
            row, column = divmod(index, 2)
            self.text(oy + 5 + row, side + column * 4, *glyphs.icon(False, index < game.TARGET - game.kills))
        rows = (("1P", str(game.lives), "player"), ("SCORE", f"{game.score:06d}", "text"),
                ("POWER", f"{game.power}/3", "player"))
        for offset, (label, value, role) in enumerate(rows):
            self.text(oy + 16 + offset, side, label, "muted")
            self.text(oy + 16 + offset, side + 7, value, role)
        lost = game.reason == "HQ was destroyed."
        self.text(oy + 19, side, "HQ 失守" if lost else "HQ 完好", "enemy" if lost else "player")
        self.text(oy + 20, side, f"{int(game.elapsed) // 60:02}:{int(game.elapsed) % 60:02}", "muted")

    def run(self):
        self.setup()
        previous = time.monotonic()
        while self.running:
            now = time.monotonic()
            self.update(now - previous)
            previous = now
            for _ in range(32):
                key = self.screen.getch()
                if key == -1:
                    break
                self.handle(key)
                if not self.running:
                    break
            self.draw()
            time.sleep(1 / 30)
