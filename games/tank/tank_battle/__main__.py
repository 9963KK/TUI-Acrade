import curses
import locale
from pathlib import Path
import sys

try:
    import arcade_kit  # noqa: F401
except ImportError:
    # 源码布局下工具包在仓库的 kit/ 目录；构建安装包时会把它一并打入，不依赖平台提供。
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "kit"))

from .app import App


def main():
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("Please run Tank Battle in an interactive terminal.", file=sys.stderr)
        return 1
    locale.setlocale(locale.LC_ALL, "")
    try:
        curses.wrapper(lambda screen: App(screen).run())
    except KeyboardInterrupt:
        pass
    except curses.error:
        print("Cannot initialize the terminal. Check TERM and try a UTF-8 terminal.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
