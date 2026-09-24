"""Small, failure-tolerant best-score record for Tank Battle.

存档写在平台分配的 TUI_ARCADE_DATA_DIR；单独运行时按 arcade_kit.paths 的同一规则算出默认位置，
两种启动方式共用同一份记录。
"""

import json
import os
from pathlib import Path
import tempfile
import time

from arcade_kit.paths import game_data_dir

GAME_ID = "tank"
FILE = "scores.json"


def score_path(env=None):
    return game_data_dir(GAME_ID, env) / FILE


def legacy_path(env=None):
    # 平台拆分前的旧位置，只读，用于一次性导入。
    env = os.environ if env is None else env
    return Path(env.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "tui-arcade" / FILE


def _read(path):
    """返回 (最高分, 状态)；状态为 missing / ok / corrupt。"""
    try:
        text = Path(path).read_text()
    except FileNotFoundError:
        return 0, "missing"
    except OSError:
        return 0, "corrupt"
    try:
        value = json.loads(text).get("tank_best", 0)
    except (ValueError, AttributeError):
        return 0, "corrupt"
    return (value, "ok") if type(value) is int and value >= 0 else (0, "corrupt")


def read_best(path=None, legacy=None):
    migrate = path is None or legacy is not None
    path = Path(path or score_path())
    value, state = _read(path)
    if state == "missing" and migrate:
        # 新位置还没有记录时导入旧记录；旧文件保留，之后不再读取，不会覆盖更高的新纪录。
        legacy = Path(legacy or legacy_path())
        if legacy != path:
            old, old_state = _read(legacy)
            if old_state == "ok" and old > 0 and save_best(old, path):
                return old
    return value


def is_corrupt(path=None):
    return _read(path or score_path())[1] == "corrupt"


def _preserve(path):
    # 读不出的旧记录不得被静默覆盖：先改名保留，再写入新记录。
    target = path.with_name(FILE + ".corrupt")
    if target.exists():
        target = path.with_name(f"{FILE}.corrupt-{int(time.time())}")
    path.replace(target)
    return target


def save_best(score, path=None):
    if type(score) is not int or score < 0:
        raise ValueError("Score must be a non-negative integer")
    path = Path(path or score_path())
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        previous, state = _read(path)
        if state == "corrupt":
            _preserve(path)
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            json.dump({"tank_best": max(score, previous)}, output)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
        return True
    except OSError:
        return False
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
