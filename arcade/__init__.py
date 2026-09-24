"""TUI Arcade platform: list games, hand them the terminal, take it back."""

from pathlib import Path
import sys

# 源码布局下，共用工具包位于仓库的 kit/ 目录；打包发行时随平台一起打入。
_KIT = Path(__file__).resolve().parents[1] / "kit"
if _KIT.is_dir() and str(_KIT) not in sys.path:
    sys.path.insert(0, str(_KIT))
