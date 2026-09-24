"""Per-OS locations for TUI Arcade programs, game data, logs and cache.

平台和游戏共用这一套规则：游戏由平台启动时使用注入的 TUI_ARCADE_DATA_DIR，
单独运行时按同样规则算出默认位置，因此两种方式共用同一份数据。
"""

from dataclasses import dataclass
import os
from pathlib import Path
import sys


@dataclass(frozen=True)
class Roots:
    programs: Path
    data: Path
    logs: Path
    cache: Path


def system_name(platform=None):
    platform = sys.platform if platform is None else platform
    if platform.startswith("win"):
        return "windows"
    return "macos" if platform == "darwin" else "linux"


def roots(env=None, system=None, home=None):
    env = os.environ if env is None else env
    system = system_name() if system is None else system
    home = Path.home() if home is None else Path(home)
    # 整体改到一个目录下，用于测试、便携安装或多份独立环境。
    if env.get("TUI_ARCADE_HOME"):
        base = Path(env["TUI_ARCADE_HOME"])
        return Roots(base / "programs", base / "data", base / "logs", base / "cache")
    if system == "windows":
        local = Path(env.get("LOCALAPPDATA") or home / "AppData" / "Local")
        return Roots(local / "Programs" / "tui-arcade", local / "tui-arcade", local / "tui-arcade" / "logs",
                     local / "tui-arcade" / "cache")
    xdg = lambda key: env.get(key) and Path(env[key]) / "tui-arcade"
    if system == "macos":
        # 显式设置的 XDG 变量优先，方便习惯 XDG 的用户与测试隔离。
        support = xdg("XDG_DATA_HOME") or home / "Library" / "Application Support" / "TUI Arcade"
        return Roots(support / "programs", support, xdg("XDG_STATE_HOME") or home / "Library" / "Logs" / "TUI Arcade",
                     xdg("XDG_CACHE_HOME") or home / "Library" / "Caches" / "TUI Arcade")
    data = xdg("XDG_DATA_HOME") or home / ".local" / "share" / "tui-arcade"
    state = xdg("XDG_STATE_HOME") or home / ".local" / "state" / "tui-arcade"
    return Roots(data / "programs", data, state / "logs", xdg("XDG_CACHE_HOME") or home / ".cache" / "tui-arcade")


def game_data_dir(game_id, env=None, **kwargs):
    env = os.environ if env is None else env
    if env.get("TUI_ARCADE_DATA_DIR"):
        return Path(env["TUI_ARCADE_DATA_DIR"])
    return roots(env, **kwargs).data / "games" / game_id


def game_log_dir(game_id, env=None, **kwargs):
    env = os.environ if env is None else env
    if env.get("TUI_ARCADE_LOG_DIR"):
        return Path(env["TUI_ARCADE_LOG_DIR"])
    return roots(env, **kwargs).logs / game_id
