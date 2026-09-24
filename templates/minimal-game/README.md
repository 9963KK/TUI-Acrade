# 最小游戏样例 · 猜数字

复制本文件夹作为新游戏的起点。它只用 Python 标准库，不依赖平台代码，演示接入 TUI Arcade 所需的最少约定（完整规范见 [游戏接入规范](../../docs/game-integration.md)）：

1. **在当前终端里游玩**：直接读写标准输入输出，不打开新窗口。
2. **清单**：`game.json` 描述名称、版本、启动命令、运行条件、存档方式和文档位置。
3. **数据目录**：存档写入平台注入的 `TUI_ARCADE_DATA_DIR`；单独运行时写入 `$XDG_DATA_HOME/minimal-game`（默认 `~/.local/share/minimal-game`）。存档损坏时不覆盖原文件。
4. **退出码**：正常结束返回 0，Ctrl-C 返回 130；胜负不体现在退出码里。

## 运行

- 单独运行：`python3 main.py`
- 在游戏厅中调试：`TUI_ARCADE_DEV_GAMES="$PWD/.." python3 -m arcade`（在仓库根目录执行，`TUI_ARCADE_DEV_GAMES` 指向包含游戏文件夹的目录）

`{python}` 启动方式只用于开发来源；正式安装包必须自带运行环境，`launch.argv[0]` 指向包内入口（如 `./bin/guess`）。
