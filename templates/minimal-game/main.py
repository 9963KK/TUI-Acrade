"""Minimal TUI Arcade game: guess a number, entirely in the current terminal.

只用标准库，不依赖平台代码，演示接入所需的最少约定：
- 在启动它的终端里读写输入输出；
- 存档写入 TUI_ARCADE_DATA_DIR，单独运行时有自己的默认位置；
- 正常结束返回 0，Ctrl-C 返回 130。
"""

import json
import os
from pathlib import Path
import random
import sys
import tempfile


def data_dir():
    if os.environ.get("TUI_ARCADE_DATA_DIR"):
        return Path(os.environ["TUI_ARCADE_DATA_DIR"])
    # 单独运行时的默认位置，见 README。
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "minimal-game"


def load(path):
    """返回存档；文件损坏时返回 None，本局不保存，也不覆盖原文件。"""
    try:
        stats = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"plays": 0, "best": None}
    except (OSError, ValueError):
        return None
    valid = isinstance(stats, dict) and type(stats.get("plays")) is int and (
        stats.get("best") is None or type(stats.get("best")) is int)
    return stats if valid else None


def save(path, stats):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as output:
            json.dump(stats, output)
        Path(output.name).replace(path)
        return True
    except OSError:
        return False


def main():
    leave = "返回大厅" if os.environ.get("TUI_ARCADE_LAUNCHER") == "1" else "退出"
    path = data_dir() / "stats.json"
    stats = load(path)
    if stats is None:
        print(f"存档 {path} 无法读取，本局不会保存，原文件保留。")
    secret, tries = random.randint(1, 100), 0
    best = stats and stats["best"]
    print(f"猜数字 · 1 到 100 之间。{'最少 ' + str(best) + ' 次' if best else '还没有纪录'}。输入 q {leave}。")
    while True:
        try:
            line = input("> ").strip().lower()
        except EOFError:
            break
        if line == "q":
            break
        if not line.isdigit():
            print("请输入 1 到 100 的数字。")
            continue
        tries += 1
        guess = int(line)
        if guess != secret:
            print("小了。" if guess < secret else "大了。")
            continue
        print(f"猜中了！用了 {tries} 次。")
        if stats is not None and (best is None or tries < best):
            stats["best"] = tries
        break
    if stats is not None:
        stats["plays"] += 1
        if not save(path, stats):
            print("存档写入失败，本局记录没有保存。")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        sys.exit(130)
