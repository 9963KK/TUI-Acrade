import argparse
import curses
import locale
import sys

from . import catalog
from .ui import App


def main():
    games, problems = catalog.load()
    parser = argparse.ArgumentParser(description="TUI Arcade — short games for your terminal")
    parser.add_argument("--game", choices=[entry.id for entry in games], help="Launch a game directly")
    args = parser.parse_args()
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("Please run TUI Arcade in an interactive terminal.", file=sys.stderr)
        return 1
    locale.setlocale(locale.LC_ALL, "")
    start = next((entry for entry in games if entry.id == args.game), None)
    try:
        curses.wrapper(lambda screen: App(screen, games, problems=problems).run(start))
    except KeyboardInterrupt:
        pass
    except curses.error:
        print("Cannot initialize the terminal. Check TERM and try a UTF-8 terminal.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
