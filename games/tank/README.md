# 坦克大战 · TANK BATTLE

守住基地，等待援军。一局 3 分钟的单人终端坦克战。

## 玩法

- 消灭 12 辆敌军可提前获胜；倒计时结束且基地仍在也算获胜。
- 3 条命，出生和复活后有 3 秒护盾；基地被击中或生命耗尽立即结束。
- 砖墙可破坏，钢墙不可破坏，水域挡车不挡炮；双方炮弹可以互相抵消；玩家炮弹不会破坏基地。
- 每击毁一辆得 100 分；获胜另得剩余生命 × 200 + 剩余秒数 × 5。

| 按键 | 功能 |
| --- | --- |
| WASD / 方向键 | 移动、转向 |
| 空格 / J | 射击 |
| F | 开关自动连射 |
| P / Esc | 暂停、继续 |
| ? / H | 说明 |
| Q | 结束本局并退出（从游戏厅启动时返回大厅） |
| Enter / R | 结算后再来一局 |

## 运行

- 从游戏厅：`python3 -m arcade --game tank`
- 单独运行：`cd games/tank && python3 -m tank_battle`

需要 80 × 24 以上的 UTF-8 终端。使用 Python 标准库 `curses`，因此当前只支持 macOS 与 Linux；Windows 需要改用其它终端后端后才能声明支持。

## 存档

只保存最高分（`save_mode: records`），文件为数据目录下的 `scores.json`：

- 由游戏厅启动时写入平台分配的 `TUI_ARCADE_DATA_DIR`；
- 单独运行时使用同一位置：Linux `~/.local/share/tui-arcade/games/tank/`，macOS `~/Library/Application Support/TUI Arcade/games/tank/`（设置了 `XDG_DATA_HOME` 或 `TUI_ARCADE_HOME` 时以其为准）。

首次运行会从旧位置 `~/.local/share/tui-arcade/scores.json` 导入最高分，旧文件保留不删。记录文件无法读取时不会被覆盖，而是另存为 `scores.json.corrupt` 并在结算时提示。

## 开发

- `tank_battle/rules.py`：不依赖终端的规则，可直接单元测试。
- `tank_battle/app.py`、`glyphs.py`：终端界面与字形，使用可选工具包 `arcade_kit`（仓库 `kit/`）；打包安装包时须把 `arcade_kit` 一并打入。
- `tank_battle/storage.py`：最高分读写与迁移。
