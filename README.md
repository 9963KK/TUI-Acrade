# TUI Arcade · 终端游戏厅

终端游戏的统一入口。平台负责**安装与检查游戏、在当前终端里启动游戏、游戏结束后回到大厅**；游戏的玩法、菜单、渲染、存档、联网都由游戏自己管理。第一款：**坦克大战**。

## 开始玩

首次安装 `tplay` 命令（在 `~/.local/bin` 生成启动脚本，指向本仓库；可用 `TPLAY_BIN_DIR` 指定其他目录）：

```sh
cd "/Users/jenkinschen5/Desktop/ManyThings/TUI Arcade"
scripts/install-tplay.sh
```

之后在任意目录输入 `tplay`，启动界面提供「进入游戏厅」「安装游戏」「退出游戏厅」。首次默认选中「安装游戏」，选择坦克大战，确认运行环境与试运行命令，通过检查后即可进入大厅游玩。大厅只展示已安装的游戏。

启动脚本会在源码变化时重新构建平台（`bin/tplay`），无需重新安装命令；`scripts/install-tplay.sh --uninstall` 可移除该命令。

也可使用命令行管理游戏：

```sh
tplay install tank                   # 安装内置坦克大战，先展示并确认安装计划
tplay install /absolute/path/to/game # 登记本地游戏目录，源码留在原处
tplay install https://example.com/game.git # 克隆根目录带 game.json 的仓库
tplay list                           # 查看已安装游戏
tplay check tank --run               # 静态检查并使用存档副本试运行
tplay uninstall tank                # 卸载登记和运行环境，保留存档
```

`install` / `uninstall` 的 `--yes` 可跳过确认，适合自动化；`install --keep` 保留失败后的暂存源码。安装页面也提供 git／本地目录添加、卸载和修复操作。大厅中的 `/` 按名称或标签搜索，`Q` / `Esc` 返回启动界面。

- 安装后直接进入坦克大战：`tplay --game tank`（退出后回到大厅）；查看版本：`tplay --version`。
- 不安装命令时，也可运行仓库中的 `./play.sh`，或在 macOS 上双击 `play.command`。
- 坦克大战也可单独运行：`cd games/tank && python3 -m tank_battle`。
- 调试自己的游戏：`tplay install /absolute/path/to/game`，修改源码后重新检查；若检查失败，在安装页面修复。
- `go run ./cmd/tplay` 的构建在 Go 缓存目录中。需要内置游戏列表时设置 `TUI_ARCADE_REPO=/absolute/path/to/repo`，或使用 `tplay` / `play.sh`。

从源码运行需要 Go 1.26+（构建平台）与 Python 3.10+（坦克大战等 Python 游戏），以及支持 UTF-8 的交互式终端，窗口至少 **80 列 × 24 行**。平台本身是单个可执行文件，`scripts/build.sh` 在一台机器上交叉编译出 macOS（Intel / Apple Silicon）、Linux x86_64 与 Windows x86_64 四个版本；坦克大战使用 Python 标准库 `curses`，目前只支持 macOS 与 Linux。

## 游戏

| 游戏 | 说明 |
| --- | --- |
| [坦克大战](games/tank/README.md) | 经典 35 关单人战役；独立主菜单、暂停／继续／重试、选关与通关结算；退出游戏后返回大厅 |
| [猜数字（样例）](templates/minimal-game/README.md) | 最小接入样例，默认不上架；开发新游戏时从这里复制起步 |

## 接入游戏

**核心要求：游戏必须在启动它的同一个终端窗口里运行和游玩。** 平台把当前终端直接交给游戏进程，游戏退出后收回；游戏不能打开新窗口、浏览器或图形界面程序。语言、渲染、存档、联网都由游戏自己决定。完整协议见 [游戏接入规范](docs/game-integration.md)，这里只列要点：

- 每个游戏是一个带 `game.json` 的文件夹，字段为 `manifest_version`、`id`、`name`、`version`、`description`、`authors`、`launch`、`requirements`、`data`、`documentation`，画廊展示信息放在可选的 `metadata.presentation`（英文名、标签、封面）。参考 [坦克大战的清单](games/tank/game.json)。
- 平台只认识清单协议 `1`；更新的协议显示“需要更新平台”，不猜测解析。未知顶层字段、非法 ID（含 Windows 保留名 `con`、`nul` 等）、越界路径、缺失的文档文件都会让清单被拒绝，标题栏显示无效清单数量。
- 游戏来源分三类：**内置**是平台所在源码仓库的 `games/`；**git** 克隆到 `programs/games/<id>/`；**本地**登记绝对目录。三种来源都必须确认并通过安装检查，`TUI_ARCADE_DEV_GAMES` 不再作为自动发现入口。卸载只删除 git 克隆和平台创建的环境，保留内置／本地源码与所有存档。
- 三种来源均可使用 `{python}` 或包内可执行入口 `./bin/...`。`requirements.python` 可声明 `version`（如 `>=3.10,<4`）、`modules`（如 `["curses"]）、`packages`（指向 requirements 文件）。平台选择符合版本的解释器，仅声明 packages 时创建独立 venv 并安装依赖；不修改系统 Python。可用 `TUI_ARCADE_PYTHON` 优先指定解释器。
- 安装检查涵盖清单、平台／架构、解释器、模块、入口和 POSIX 伪终端试运行；试运行使用存档副本。Windows 跳过伪终端试运行并在报告中标明。源码或运行环境失效时，大厅仍保留游戏卡片但禁止启动，显示修复报告和日志。
- 安装记录保存在数据根目录的 `installed.json`，采用文件锁、原子替换与 `.bak` 备份。安装／卸载中断会在下次启动恢复或清理暂存事务；游戏运行期间不能卸载。
- 启动时注入：`TUI_ARCADE_LAUNCHER=1`、`TUI_ARCADE_PROTOCOL=1`、`TUI_ARCADE_GAME_ID`、`TUI_ARCADE_LOG_DIR`，以及 `data.managed_directory` 为真时的 `TUI_ARCADE_DATA_DIR`（平台负责创建）。平台不修改 `PYTHONPATH`，游戏不得依赖平台内部模块。
- 退出码 0 为正常结束，其它退出码在大厅提示，Ctrl-C 结束不提示；胜负不体现在退出码里。平台在游戏退出后兜底复位颜色、光标、备用屏幕、鼠标上报、括号粘贴与 Kitty 键盘协议，并恢复终端模式。
- Python 游戏可选用 `kit/arcade_kit`（绘制、配色、帧提交、目录规则）。选用时须在构建安装包时一并打入；源码布局下游戏自行从仓库 `kit/` 找到它。
- 平台会原样执行 `launch.argv`，**只安装信得过的游戏**。

目录位置（`TUI_ARCADE_HOME` 可把全部内容改到同一个目录下，便于测试和便携使用）：

| | Linux | macOS | Windows |
| --- | --- | --- | --- |
| 已安装程序 | `~/.local/share/tui-arcade/programs` | `~/Library/Application Support/TUI Arcade/programs` | `%LOCALAPPDATA%\Programs\tui-arcade` |
| 游戏数据 | `~/.local/share/tui-arcade/games/<id>` | `~/Library/Application Support/TUI Arcade/games/<id>` | `%LOCALAPPDATA%\tui-arcade\games\<id>` |
| 日志 | `~/.local/state/tui-arcade/logs/<id>` | `~/Library/Logs/TUI Arcade/<id>` | `%LOCALAPPDATA%\tui-arcade\logs\<id>` |

Linux 遵循 `XDG_DATA_HOME` / `XDG_STATE_HOME` / `XDG_CACHE_HOME`；macOS 上显式设置了这些变量时也以其为准。

## 开发

- `platform/`：平台（Go + [Bubble Tea](https://github.com/charmbracelet/bubbletea)），入口为 `cmd/tplay`。
  - `internal/catalog`：读取并校验清单；`internal/launcher`：注入环境、交出与收回终端（POSIX 用 termios，Windows 用控制台模式）；
  - `internal/install`：源码获取、依赖环境、检查与安装事务；`internal/registry`：安装记录与跨进程文件锁；
  - `internal/lobby`：启动界面、安装管理、画廊大厅（2 行 3 列，超过 6 款自动分页，左右不跨行）；`internal/screen`：单元格缓冲区与颜色降级；`internal/paths`：各系统目录规则。
- `kit/arcade_kit/`：Python 游戏可选用的工具包。`canvas.py` 绘制，`theme.py` 语义颜色与按需色对，`presentation.py` 帧提交，`paths.py` 各系统目录规则（与 `internal/paths` 同一规则）。
- `games/tank/`：坦克大战，见其 [README](games/tank/README.md)。
- `templates/minimal-game/`：只用标准库的最小游戏样例。
- `docs/`：[设计文档](docs/README.md)，包含架构、接入、安装管理与贡献规范。

### Grok Build 风格渲染

平台大厅与坦克大战使用同一套 GrokNight 配色。大厅由 Go 渲染：根据 `COLORTERM`、`TERM` 选择 24 位真彩色、256 色、8／16 色或单色（`NO_COLOR`）；`ARCADE_ASCII=1` 或 `TERM=linux` 时线条改用 ASCII。每帧在内存中完整合成，Bubble Tea 只重写变化的行，静止画面不输出任何数据。下面几条描述坦克大战（Python / curses）：

- **统一主题**：参考 [GrokNight](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager-render/src/theme/groknight.rs)，使用中性深灰背景和浮起一层的面板；蓝色用于界面提示，绿／红区分敌我，砖墙和钢墙使用低饱和色。
- **块字符战场**：52 × 52 子格地图压缩到 13 行，彩色终端用 `▟▙`、`━█` 显示坦克，用 Braille 点保留砖墙缺口，并区分钢墙、水域、森林与冰面。若字体缺少块字符，或终端把歧义宽度字符显示为双宽，请用 `ARCADE_ASCII=1 ./play.sh` 切换为 ASCII 界面；Linux 控制台自动使用 ASCII。
- **颜色降级**：根据 curses 实际报告的能力，将 RGB 主题映射至 256 色或基础 8／16 色。支持 `NO_COLOR=1`；单色或色对不足时自动改用 ASCII 符号，以 `P`、`!`、地形字符和粗体区分内容。当前 curses 后端不直接输出 24 位 truecolor，不修改终端全局调色板。
- **只提交变化**：比较画面中可见的状态；大厅、暂停、帮助等静止画面不重复重绘。画面变化时在内存中完整合成，再通过 curses 双缓冲差分更新终端；动画上限为 30 FPS，游戏模拟仍按独立的固定步长推进。
- **整帧同步**：参考 Grok Build 的 [draw_frame](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager-render/src/render/draw.rs)，在识别到 Ghostty、WezTerm、Kitty、foot 时用 synchronized output 包裹提交；未知终端和 Apple Terminal 使用常规差分输出，tmux／screen 内禁用额外包裹。可用 `ARCADE_SYNC=0` 关闭，或在确认支持的直连终端中用 `ARCADE_SYNC=1` 启用。
- **实现边界**：坦克大战借鉴主题与提交逻辑，仍使用 Python / curses。输出串行完成，不累积待渲染帧；尚未移植 Grok Build 的异步 writer、图片覆盖层和长历史虚拟化，慢速终端写入仍可能阻塞主循环。

```sh
(cd platform && go vet ./... && go test ./...)
python3 -m unittest discover -s tests -v
```

`tests/test_terminal.py` 会先构建 Go 平台，再在真实伪终端中验证：首次通过菜单安装坦克大战；安装后启动坦克大战、最小样例与本地可执行游戏；Ctrl-C 只结束游戏；存档写入平台分配的目录；退出后回到大厅和启动界面；终端模式完整还原。Go 测试覆盖安装失败回滚、修复、依赖环境、记录备份、并发锁和中断恢复。

终端按键依靠系统连发，初次长按的延迟随系统设置变化；可开启自动连射改善边走边打的手感。坦克大战以消灭每关 20 辆敌军作为胜利条件，生命、分数和升级可跨关保留，菜单打开时战场冻结。
