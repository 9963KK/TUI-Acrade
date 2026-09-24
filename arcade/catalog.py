"""Read game manifests (docs/game-integration.md). The platform only lists and launches games."""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import sys
import unicodedata

from arcade_kit.canvas import cell_width
from arcade_kit.paths import roots, system_name

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "game.json"
PROTOCOLS = {1}
COVER_WIDTH, COVER_HEIGHT = 11, 4
ID_PATTERN = re.compile(r"[a-z][a-z0-9-]{0,63}")
# Windows 不允许用作文件或目录名，游戏 ID 会成为数据目录名。
RESERVED_IDS = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
SEMVER = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?")
FIELDS = {"manifest_version", "id", "name", "version", "description", "authors", "launch",
          "requirements", "data", "documentation", "metadata"}
NETWORK = {"none", "optional", "required"}
COLOR = {"optional", "16", "256", "truecolor"}
UNICODE = {"optional", "required"}
KEYBOARD = {"basic", "kitty-optional"}
GRAPHICS = {"none", "kitty-optional"}
SAVE_MODES = {"none", "records", "progress", "resume"}
ARCH_ALIASES = {"x86_64": "x86_64", "amd64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}


class ManifestError(ValueError):
    pass


def host():
    return system_name(), ARCH_ALIASES.get(platform.machine().lower(), platform.machine().lower())


def game_dirs(env=None):
    """(目录, 来源)：仓库 games/ 与 TUI_ARCADE_DEV_GAMES 为开发来源，程序目录为已安装来源。"""
    env = os.environ if env is None else env
    dev = [ROOT / "games", *(Path(p) for p in env.get("TUI_ARCADE_DEV_GAMES", "").split(os.pathsep) if p)]
    return [*((directory, "dev") for directory in dev), (roots(env).programs, "installed")]


@dataclass(frozen=True)
class CoverCell:
    text: str
    ascii: str
    foreground: tuple
    background: tuple
    bold: bool


@dataclass(frozen=True)
class Presentation:
    name_en: str = ""
    tags: tuple = ()
    cover: tuple = ()
    cells: dict = field(default_factory=dict)
    cover_background: tuple = (28, 28, 28)


@dataclass(frozen=True)
class Terminal:
    columns: int = 80
    rows: int = 24
    color: str = "optional"
    unicode: str = "optional"
    keyboard: str = "basic"
    graphics: str = "none"


@dataclass(frozen=True)
class Entry:
    id: str
    name: str
    version: str
    description: str
    authors: tuple
    argv: tuple
    root: Path
    cwd: Path
    terminal: Terminal
    network: str
    managed_data: bool
    save_mode: str
    source: str
    presentation: Presentation
    # 能读出但不能运行的原因：协议版本过新、系统或架构不兼容。
    issue: str = ""

    def command(self):
        # {python} 仅开发来源可用，{dir} 为游戏文件夹；以 ./ 开头的入口按游戏文件夹解析。
        parts = [part.replace("{python}", sys.executable).replace("{dir}", str(self.root)) for part in self.argv]
        if parts[0].startswith("./"):
            parts[0] = str(self.root / parts[0][2:])
        return parts


def _sanitize(text):
    # 展示文本中不得带入终端控制序列与隐藏的格式字符。
    return "".join(char for char in text if unicodedata.category(char) not in ("Cc", "Cf"))


def _string(data, key, context="manifest", required=True, default=""):
    if key not in data:
        if required:
            raise ManifestError(f"{context}.{key} is required")
        return default
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{context}.{key} must be a non-empty string")
    return _sanitize(value)


def _choice(data, key, allowed, default, context):
    value = data.get(key, default)
    if value not in allowed:
        raise ManifestError(f"{context}.{key} must be one of {sorted(allowed)}")
    return value


def _inside(root, relative, context):
    # 相对路径规范化后必须仍在游戏文件夹内。
    if not isinstance(relative, str) or not relative or PurePosixPath(relative).is_absolute() or "\\" in relative:
        raise ManifestError(f"{context} must be a relative path")
    path = (root / relative).resolve()
    if path != root and root not in path.parents:
        raise ManifestError(f"{context} escapes the game folder")
    return path


def _color(value, default=None):
    if value is None:
        return default
    if not (isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value)):
        raise ManifestError(f"Invalid color {value!r}")
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


def _presentation(data):
    """metadata.presentation 只影响画廊展示，格式有误时整体忽略，不影响游戏本身。"""
    try:
        spec = data.get("metadata", {}).get("presentation", {})
        tags = spec.get("tags", [])
        if not (isinstance(tags, list) and all(isinstance(tag, str) for tag in tags)):
            raise ManifestError("tags")
        cover = spec.get("cover", {})
        rows = cover.get("rows", [])
        if not (isinstance(rows, list) and all(isinstance(row, str) for row in rows)):
            raise ManifestError("rows")
        cells = {}
        for key, cell in cover.get("cells", {}).items():
            text = cell.get("text", "  ")
            ascii_text = cell.get("ascii", text)
            # 每个封面格固定占两列；宽度不符会让整行错位。
            if len(key) != 1 or cell_width(text) != 2 or cell_width(ascii_text) != 2 or not ascii_text.isascii():
                raise ManifestError("cell")
            cells[key] = CoverCell(_sanitize(text), _sanitize(ascii_text), _color(cell.get("fg"), (225, 225, 225)),
                                   _color(cell.get("bg")), bool(cell.get("bold", False)))
        name_en = spec.get("name_en", "")
        if not isinstance(name_en, str):
            raise ManifestError("name_en")
        return Presentation(_sanitize(name_en), tuple(_sanitize(tag) for tag in tags),
                            tuple(row[:COVER_WIDTH] for row in rows[:COVER_HEIGHT]), cells,
                            _color(cover.get("background"), (28, 28, 28)))
    except (ManifestError, AttributeError, TypeError):
        return Presentation()


def parse(path, source="dev", system_arch=None):
    path = Path(path)
    root = path.resolve().parent
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ManifestError("Manifest must be an object")
    version = data.get("manifest_version")
    if type(version) is not int or version < 1:
        raise ManifestError("manifest_version must be a positive integer")
    game_id = data.get("id")
    if not (isinstance(game_id, str) and ID_PATTERN.fullmatch(game_id)) or game_id in RESERVED_IDS:
        raise ManifestError("id must match [a-z][a-z0-9-]{0,63} and not be a reserved name")
    name = _string(data, "name")
    if version not in PROTOCOLS:
        # 协议更新的清单不猜测解析，只保留可展示的信息并禁止启动。
        return _placeholder(game_id, name, root, source, f"需要更新平台（清单协议 {version}）")
    unknown = set(data) - FIELDS
    if unknown:
        raise ManifestError(f"Unknown fields: {sorted(unknown)}")
    game_version = _string(data, "version")
    if not SEMVER.fullmatch(game_version):
        raise ManifestError("version must be MAJOR.MINOR.PATCH")
    authors = data.get("authors")
    if not (isinstance(authors, list) and authors and all(isinstance(a, str) and a.strip() for a in authors)):
        raise ManifestError("authors must be a non-empty list of strings")
    launch = data.get("launch")
    if not isinstance(launch, dict):
        raise ManifestError("launch is required")
    argv = launch.get("argv")
    if not (isinstance(argv, list) and argv and all(isinstance(part, str) and part for part in argv)):
        raise ManifestError("launch.argv must be a non-empty list of strings")
    # 预构建包不得依赖玩家电脑上的解释器；{python} 只允许用于开发来源。
    if source != "dev" and any("{python}" in part for part in argv):
        raise ManifestError("{python} is only allowed for development sources")
    if source != "dev" and not argv[0].startswith("./"):
        raise ManifestError("launch.argv[0] must be an entry inside the package (./...)")
    if argv[0].startswith("./"):
        _inside(root, argv[0][2:], "launch.argv[0]")
    cwd = _inside(root, launch.get("cwd", "."), "launch.cwd")
    requirements = data.get("requirements", {})
    terminal_spec = requirements.get("terminal", {}) if isinstance(requirements, dict) else None
    if not isinstance(terminal_spec, dict):
        raise ManifestError("requirements must be an object")
    columns, rows = terminal_spec.get("columns", 80), terminal_spec.get("rows", 24)
    if not all(type(n) is int and n > 0 for n in (columns, rows)):
        raise ManifestError("requirements.terminal.columns/rows must be positive integers")
    context = "requirements.terminal"
    terminal = Terminal(columns, rows, _choice(terminal_spec, "color", COLOR, "optional", context),
                        _choice(terminal_spec, "unicode", UNICODE, "optional", context),
                        _choice(terminal_spec, "keyboard", KEYBOARD, "basic", context),
                        _choice(terminal_spec, "graphics", GRAPHICS, "none", context))
    network = _choice(requirements, "network", NETWORK, "none", "requirements")
    systems, arches = requirements.get("os", []), requirements.get("arch", [])
    if not (isinstance(systems, list) and isinstance(arches, list)):
        raise ManifestError("requirements.os/arch must be lists")
    data_spec = data.get("data", {})
    if not isinstance(data_spec, dict):
        raise ManifestError("data must be an object")
    managed = data_spec.get("managed_directory", True)
    if type(managed) is not bool:
        raise ManifestError("data.managed_directory must be a boolean")
    save_mode = _choice(data_spec, "save_mode", SAVE_MODES, "none", "data")
    documentation = data.get("documentation", {})
    if not isinstance(documentation, dict):
        raise ManifestError("documentation must be an object")
    for key, relative in documentation.items():
        if not _inside(root, relative, f"documentation.{key}").is_file():
            raise ManifestError(f"documentation.{key} does not exist")
    current_system, current_arch = system_arch or host()
    issue = ""
    if (systems and current_system not in systems) or (arches and current_arch not in arches):
        issue = f"本机不支持（{'/'.join(systems) or '任意系统'} · {'/'.join(arches) or '任意架构'}）"
    return Entry(game_id, name, game_version, _string(data, "description", required=False), tuple(authors),
                 tuple(argv), root, cwd, terminal, network, managed, save_mode, source, _presentation(data), issue)


def _placeholder(game_id, name, root, source, issue):
    return Entry(game_id, name, "", "", (), ("?",), root, root, Terminal(), "none", False, "none", source,
                 Presentation(), issue)


def load(dirs=None):
    """返回 (游戏列表, 无效清单)；无效清单为 (路径, 原因)。重复 id 只保留先出现的（开发来源优先）。"""
    entries, problems, seen = [], [], set()
    for directory, source in dirs if dirs is not None else game_dirs():
        try:
            manifests = sorted(Path(directory).glob(f"*/{MANIFEST}"))
        except OSError:
            continue
        for manifest in manifests:
            try:
                entry = parse(manifest, source)
            except (OSError, ValueError, AttributeError, TypeError) as error:
                problems.append((manifest, str(error)))
                continue
            if entry.id not in seen:
                seen.add(entry.id)
                entries.append(entry)
    return entries, problems
