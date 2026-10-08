"""Tank Battle curses front end: battle view, HUD, dialogs and input."""

import curses
import math
import os
import time

from arcade_kit.canvas import Canvas

from .glyphs import TILE_COLORS, Glyphs
from .levels import LEVELS
from .rules import Battle, Direction
from .storage import read_best, save_record

MOVES = {curses.KEY_UP: Direction.UP, curses.KEY_RIGHT: Direction.RIGHT,
         curses.KEY_DOWN: Direction.DOWN, curses.KEY_LEFT: Direction.LEFT,
         ord("w"): Direction.UP, ord("d"): Direction.RIGHT,
         ord("s"): Direction.DOWN, ord("a"): Direction.LEFT}
REASONS = {"Reinforcements arrived. HQ is safe!": "援军抵达，基地守住了！",
           "All enemy tanks eliminated!": "敌军已全部消灭！",
           "HQ was destroyed.": "基地被摧毁。",
           "No tanks remaining.": "坦克全部损失。"}


class App(Canvas):
    MIN_WIDTH = 80
    MIN_HEIGHT = 24

    def __init__(self, screen, env=None):
        super().__init__(screen)
        env = os.environ if env is None else env
        # 从游戏厅启动时 Q 返回大厅，单独运行时 Q 退出。
        self.leave = "返回大厅" if env.get("TUI_ARCADE_LAUNCHER") == "1" else "退出游戏"
        self.running = True
        # 读不出的旧记录在保存时会另存备份，结算时明确告知实际的备份文件名，而不是悄悄归零。
        self.best = read_best()
        self.start(1)

    def start(self, level=None):
        # 重试保留当前关卡；下一关与选关显式传入编号，每关独立计分。
        self.game = Battle(level=self.game.level_number if level is None else level)
        self.saved = False
        self.save_failed = False
        self.preserved = None
        self.help = False
        self.confirm_leave = False
        self.selecting = False
        self.selection = self.game.level_number - 1

    def open_levels(self):
        self.selecting = True
        self.selection = self.game.level_number - 1

    @property
    def glyphs(self):
        return Glyphs(self.rich)

    def cell(self, y, x, glyph):
        # 战场格子统一绘制在 field 底色上；地形使用自带底色。
        text, role = glyph
        if role in TILE_COLORS:
            foreground, background, basic = TILE_COLORS[role]
            style = self.theme.custom(foreground, background, basic, role in ("tile.base", "tile.shield"))
        else:
            style = self.theme.style(role, "field", role in ("player", "enemy"))
        self.paint(y, x, text, style)

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
        if self.selecting:
            if key in (curses.KEY_UP, curses.KEY_LEFT, ord("w"), ord("a")):
                self.selection = max(0, self.selection - 1)
            elif key in (curses.KEY_DOWN, curses.KEY_RIGHT, ord("s"), ord("d")):
                self.selection = min(len(LEVELS) - 1, self.selection + 1)
            elif key in (10, 13):
                self.start(self.selection + 1)
            elif key in (27, ord("q"), ord("l")):
                self.selecting = False
            return
        if self.help:
            if key in (27, ord("?"), ord("h"), ord("q"), 10, 13):
                self.help = False
            return
        if self.confirm_leave:
            if key in (10, 13, ord("y")):
                self.running = False
            elif key in (27, ord("n"), ord("q")):
                self.confirm_leave = False
            return
        if key in (ord("?"), ord("h")):
            self.help = True
            return
        if key == ord("l"):
            self.open_levels()
            return
        if self.game.result:
            if key == ord("r"):
                self.start()
            elif key in (10, 13):
                if self.game.result == "win":
                    if self.game.level_number < len(LEVELS):
                        self.start(self.game.level_number + 1)
                    else:
                        self.open_levels()
                else:
                    self.start()
            elif key in (ord("q"), 27):
                self.running = False
            return
        if key == ord("q"):
            self.confirm_leave = True
        elif key in (27, ord("p")):
            self.game.command("pause")
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
            self.game.paused = True
            return
        if not self.help and not self.confirm_leave and not self.selecting:
            self.game.advance(seconds)
        if self.game.result and not self.saved:
            self.best = max(self.best, self.game.score)
            saved, preserved = save_record(self.best)
            self.save_failed = not saved
            self.saved = True
            self.preserved = preserved.name if preserved else None

    def frame_signature(self):
        game = self.game
        tank_view = lambda tank: (tank.x, tank.y, tank.direction)
        return (self.screen.getmaxyx(), self.help, self.confirm_leave, self.selecting, self.selection,
                self.best, self.save_failed, self.preserved, game.level_number,
                game.remaining, game.lives, game.kills, game.score, game.result,
                game.reason, game.paused, game.auto_fire, math.ceil(game.shield),
                tank_view(game.player), tuple(map(tank_view, game.enemies)),
                tuple((b.x, b.y, b.friendly, b.direction) for b in game.bullets),
                tuple(game.tiles.items()), self.water_phase(),
                tuple((x, y, life > 0.15) for x, y, life in game.effects))

    def water_phase(self):
        # 跟随游戏时间而非墙钟，暂停时水面也静止，不触发重绘。
        return int(self.game.elapsed * 2) % 2

    def draw(self):
        return self.presenter.present(self.frame_signature(), self._draw)

    def _draw(self):
        self.surface = "canvas"
        self.screen.erase()
        height, width = self.screen.getmaxyx()
        if height < self.MIN_HEIGHT or width < self.MIN_WIDTH:
            self.text(1, 1, "窗口太小，游戏已暂停。", "warning", True)
            self.text(3, 1, f"需要 80 x 24，当前 {width} x {height}")
            self.text(5, 1, f"放大窗口后按 P 继续；Q {self.leave}。")
            return
        self.draw_battle(height, width)
        if self.selecting:
            self.draw_levels()
        elif self.help:
            self.dialog_in_field("出击手册", [
                "WASD / 方向键：移动并转向", "空格 / J：开炮    F：切换自动连射",
                "P / Esc：暂停    L：选择关卡",
                "绿色坦克是你，红色是敌军，HQ 是基地。",
                "3 条命；复活后有 3 秒护盾，期间免伤。",
                f"消灭 {self.game.TARGET} 辆敌军或守满 3 分钟获胜。",
                "砖墙可破坏；水域可射穿；友军炮不伤 HQ。",
                "Enter / Esc / Q 关闭说明，继续游戏"])
        elif self.confirm_leave:
            self.dialog_in_field(self.leave, ["结束本局？当前战绩不会保存。", "Enter 确认    Esc 继续游戏"])

    def origin(self):
        height, width = self.screen.getmaxyx()
        return max(0, (width - 80) // 2), max(0, (height - 24) // 2)

    def dialog_in_field(self, title, lines):
        # 在战场内居中，不遮挡右侧状态栏。
        ox, oy = self.origin()
        self.dialog(oy + 2 + (21 - len(lines) * 2 - 3) // 2, ox + 4, title, lines)

    def draw_levels(self):
        # 最多显示 5 项，后续增加关卡时仍能在 80 x 24 的窗口内选关。
        first = max(0, min(self.selection - 2, len(LEVELS) - 5))
        lines = [f"{'>' if index == self.selection else ' '} {index + 1:02}  {level.name}    敌军 {level.target}"
                 for index, level in enumerate(LEVELS) if first <= index < first + 5]
        lines.extend((LEVELS[self.selection].description,
                      "确认后开始新局，当前关卡进度将重置。",
                      "W S / 方向键选择；Enter 开始；Esc 返回"))
        self.dialog_in_field(f"选择关卡 {self.selection + 1}/{len(LEVELS)}", lines)

    def draw_battle(self, height, width):
        game = self.game
        glyphs = self.glyphs
        ox, oy = self.origin()
        self.text(oy, ox + 2, "TANK BATTLE", "accent", True)
        self.text(oy, ox + 14, "坦克大战", "text")
        self.text(oy, ox + 44, f"守住 HQ，或击毁全部 {game.TARGET} 辆敌军", "muted")
        self.text(oy + 1, ox + 2, f"第 {game.level_number}/{len(LEVELS)} 关  {game.level.name}", "accent")
        self.box(oy + 2, ox + 1, 21, 60, fill=False)
        fx, fy = ox + 2, oy + 3
        self.surface = "field"
        for row in range(game.HEIGHT):
            self.text(fy + row, fx, " " * game.WIDTH * 2)
        self.surface = "canvas"
        phase = self.water_phase()
        for (x, y), tile in game.tiles.items():
            self.cell(fy + y, fx + x * 2, glyphs.tile(tile, x, y, phase))
        bx, by = game.BASE
        self.cell(fy + by, fx + bx * 2, glyphs.base())
        for tank in game.enemies:
            self.cell(fy + tank.y, fx + tank.x * 2, glyphs.tank(tank.direction, False))
        player = game.player
        self.cell(fy + player.y, fx + player.x * 2, glyphs.tank(player.direction, True, game.shield > 0))
        for bullet in game.bullets:
            self.cell(fy + bullet.y, fx + bullet.x * 2, glyphs.bullet(bullet.direction, bullet.friendly))
        for x, y, life in game.effects:
            self.cell(fy + y, fx + x * 2, glyphs.blast(life > 0.15))
        self.draw_hud(game, glyphs, ox + 63, oy)
        self.hints(oy + 23, ox + 2, (("WASD", "移动"), ("空格/J", "射击"), ("F", "连射"),
                                     ("P", "暂停"), ("L", "选关"), ("?", "帮助"), ("Q", self.leave[:2])))
        if game.result:
            title = "任务完成" if game.result == "win" else "战斗结束"
            action = "重试"
            if game.result == "win":
                action = "下一关" if game.level_number < len(LEVELS) else "选关"
                if game.level_number == len(LEVELS):
                    title = "最终关完成"
            self.dialog_in_field(title, [
                REASONS[game.reason], f"击毁 {game.kills}/{game.TARGET}     得分 {game.score:05d}",
                "记录保存失败，本局仍可继续操作。" if self.save_failed
                else f"原记录无法读取，已另存为 {self.preserved}" if self.preserved
                else f"本地最高分 {self.best:05d}",
                f"Enter {action}  R 重试  L 选关  Q {self.leave}"])
        elif game.paused:
            self.dialog_in_field("暂停 / PAUSED", ["休息一下。战场与倒计时已冻结。", f"P / Esc 继续    Q {self.leave}"])

    def draw_hud(self, game, glyphs, side, oy):
        urgent = game.remaining < 30
        self.text(oy + 2, side, "剩余时间", "muted")
        self.text(oy + 3, side, f"{game.remaining // 60:02}:{game.remaining % 60:02}", "enemy" if urgent else "text", True)
        filled = round(14 * game.remaining / game.LIMIT)
        done, rest = self.bar
        self.text(oy + 4, side, done * filled, "enemy" if urgent else "accent")
        self.text(oy + 4, side + filled, rest * (14 - filled), "dim")
        self.text(oy + 6, side, "敌军", "muted")
        self.text(oy + 6, side + 6, f"余 {game.TARGET - game.kills:02}", "text")
        # 每个图标代表一辆敌军，击毁后变暗，直观显示离胜利还有多远。
        for index in range(min(game.TARGET, 24)):
            row, column = divmod(index, 8)
            self.text(oy + 7 + row * 2, side + column * 2, *glyphs.icon(False, index < game.TARGET - game.kills))
        self.text(oy + 13, side, "生命", "muted")
        for index in range(3):
            self.text(oy + 13, side + 6 + index * 3, *glyphs.icon(True, index < game.lives))
        lost = game.reason == "HQ was destroyed."
        rows = (("得分", f"{game.score:05}", "text"), ("基地", "失守" if lost else "完好", "enemy" if lost else "player"),
                ("连射", "ON" if game.auto_fire else "OFF", "accent" if game.auto_fire else "muted"),
                ("护盾", f"{math.ceil(game.shield)}s" if game.shield else "无", "player" if game.shield else "muted"))
        for offset, (label, value, role) in enumerate(rows):
            self.text(oy + 15 + offset, side, label, "muted")
            self.text(oy + 15 + offset, side + 6, value, role, role != "muted")
        legend = (("brick", "砖墙 可击碎"), ("steel", "钢墙 不可破"), ("water", "水域 可射穿"))
        for offset, (tile, label) in enumerate(legend):
            self.cell(oy + 20 + offset, side, glyphs.tile(tile, 0, offset))
            self.text(oy + 20 + offset, side + 3, label, "muted")

    def run(self):
        self.setup()
        previous = time.monotonic()
        while self.running:
            now = time.monotonic()
            self.update(now - previous)
            previous = now
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
