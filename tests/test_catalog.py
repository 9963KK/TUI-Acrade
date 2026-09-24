import copy
import json
from pathlib import Path
import signal
import sys
import tempfile
import unittest

import support  # noqa: F401

from arcade import catalog
from arcade.launcher import game_env, launch, prepare

VALID = {
    "manifest_version": 1, "id": "demo", "name": "演示", "version": "1.0.0", "description": "说明",
    "authors": ["作者"], "launch": {"argv": ["{python}", "main.py"], "cwd": "."},
    "requirements": {"os": [], "arch": [], "network": "none", "terminal": {"columns": 40, "rows": 10}},
    "data": {"managed_directory": True, "save_mode": "none"}, "documentation": {"readme": "README.md"},
}


def write(root, folder, base=None, **changes):
    data = copy.deepcopy(VALID if base is None else base)
    data.update(changes)
    path = Path(root) / folder
    path.mkdir(parents=True)
    (path / "README.md").write_text("说明")
    (path / catalog.MANIFEST).write_text(json.dumps(data), encoding="utf-8")
    return path / catalog.MANIFEST


class CatalogTests(unittest.TestCase):
    def test_bundled_manifests_are_valid(self):
        entries, problems = catalog.load([(catalog.ROOT / "games", "dev"), (catalog.ROOT / "templates", "dev")])
        self.assertEqual(problems, [])
        tank, sample = entries
        self.assertEqual((tank.id, tank.terminal.columns, tank.save_mode), ("tank", 80, "records"))
        self.assertEqual(tank.command()[0], sys.executable)
        self.assertEqual(len(tank.presentation.cover), catalog.COVER_HEIGHT)
        self.assertEqual(sample.id, "minimal-game")

    def test_rejects_malformed_manifests(self):
        cases = {
            "no-version": {"manifest_version": None}, "bad-id": {"id": "Demo"}, "reserved": {"id": "con"},
            "com": {"id": "com3"}, "unknown": {"extra": 1}, "semver": {"version": "1.0"},
            "authors": {"authors": []}, "argv": {"launch": {"argv": []}},
            "cwd": {"launch": {"argv": ["{python}"], "cwd": "../.."}},
            "absolute": {"launch": {"argv": ["./bin/game"], "cwd": "/tmp"}},
            "entry": {"launch": {"argv": ["./../../evil"]}},
            "network": {"requirements": {"network": "sometimes"}},
            "color": {"requirements": {"terminal": {"color": "millions"}}},
            "size": {"requirements": {"terminal": {"columns": 0}}},
            "save": {"data": {"save_mode": "cloud"}}, "managed": {"data": {"managed_directory": "yes"}},
            "docs": {"documentation": {"license": "LICENSE"}},
        }
        with tempfile.TemporaryDirectory() as root:
            for folder, change in cases.items():
                with self.subTest(folder):
                    with self.assertRaises(catalog.ManifestError):
                        catalog.parse(write(root, folder, **change))

    def test_installed_packages_must_bring_their_own_runtime(self):
        with tempfile.TemporaryDirectory() as root:
            dev = write(root, "a")
            self.assertEqual(catalog.parse(dev, "dev").source, "dev")
            with self.assertRaises(catalog.ManifestError):
                catalog.parse(dev, "installed")
            packaged = write(root, "b", launch={"argv": ["./bin/game", "--fast"]})
            entry = catalog.parse(packaged, "installed")
            self.assertEqual(entry.command(), [str(Path(root).resolve() / "b" / "bin/game"), "--fast"])
            with self.assertRaises(catalog.ManifestError):
                catalog.parse(write(root, "c", launch={"argv": ["python3", "main.py"]}), "installed")

    def test_newer_protocol_and_foreign_platform_are_listed_but_blocked(self):
        with tempfile.TemporaryDirectory() as root:
            future = catalog.parse(write(root, "a", manifest_version=2, surprise=True))
            self.assertIn("需要更新平台", future.issue)
            foreign = write(root, "b", requirements={"os": ["windows"], "arch": ["x86_64"]})
            self.assertIn("本机不支持", catalog.parse(foreign, system_arch=("macos", "arm64")).issue)
            self.assertEqual(catalog.parse(foreign, system_arch=("windows", "x86_64")).issue, "")

    def test_presentation_is_optional_and_malformed_ones_are_ignored(self):
        with tempfile.TemporaryDirectory() as root:
            broken = write(root, "a", metadata={"presentation": {"cover": {"cells": {"X": {"text": "宽"}}}},
                                                "anything": 1})
            self.assertEqual(catalog.parse(broken).presentation, catalog.Presentation())
            shown = write(root, "b", name="危\x1b[31m险", metadata={"presentation": {"tags": ["单人"]}})
            entry = catalog.parse(shown)
            self.assertEqual((entry.name, entry.presentation.tags), ("危[31m险", ("单人",)))

    def test_load_skips_invalid_and_duplicates(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            write(first, "a", name="甲")
            write(first, "b", id="b", version="x")
            write(second, "a", name="重复", launch={"argv": ["./game"]})
            write(second, "c", id="c", launch={"argv": ["./game"]})
            entries, problems = catalog.load([(first, "dev"), (second, "installed"), (Path(first) / "none", "dev")])
        self.assertEqual([(entry.id, entry.name) for entry in entries], [("demo", "甲"), ("c", "演示")])
        self.assertEqual(len(problems), 1)
        self.assertIn("version", problems[0][1])

    def test_sources_include_dev_override_and_programs(self):
        dirs = catalog.game_dirs({"TUI_ARCADE_HOME": "/tmp/home", "TUI_ARCADE_DEV_GAMES": "/src/a"})
        self.assertEqual(dirs[0], (catalog.ROOT / "games", "dev"))
        self.assertEqual(dirs[1], (Path("/src/a"), "dev"))
        self.assertEqual(dirs[-1], (Path("/tmp/home/programs"), "installed"))


class LauncherTests(unittest.TestCase):
    def entry(self, root, argv, managed=True, source="dev"):
        path = write(root, "g", launch={"argv": argv}, data={"managed_directory": managed, "save_mode": "none"})
        return catalog.parse(path, source)

    def test_env_is_injected_and_platform_paths_are_not(self):
        with tempfile.TemporaryDirectory() as root:
            entry = self.entry(root, ["{python}", "main.py"])
            env = game_env(entry, {"TUI_ARCADE_HOME": root, "PYTHONPATH": "/mine", "TUI_ARCADE_DATA_DIR": "/evil"})
        self.assertEqual(env["TUI_ARCADE_DATA_DIR"], str(Path(root) / "data" / "games" / "demo"))
        self.assertEqual(env["TUI_ARCADE_LOG_DIR"], str(Path(root) / "logs" / "demo"))
        self.assertEqual((env["TUI_ARCADE_GAME_ID"], env["TUI_ARCADE_PROTOCOL"], env["TUI_ARCADE_LAUNCHER"]),
                         ("demo", "1", "1"))
        self.assertEqual(env["PYTHONPATH"], "/mine")
        with tempfile.TemporaryDirectory() as root:
            unmanaged = game_env(self.entry(root, ["{python}"], managed=False), {"TUI_ARCADE_HOME": root})
        self.assertNotIn("TUI_ARCADE_DATA_DIR", unmanaged)

    def test_runs_in_game_folder_with_created_data_dir(self):
        with tempfile.TemporaryDirectory() as root:
            script = ("import os, sys; open(os.path.join(os.environ['TUI_ARCADE_DATA_DIR'], 'ran'), 'w')"
                      ".write(os.getcwd()); sys.exit(3)")
            entry = self.entry(root, ["{python}", "-c", script])
            env, problem = prepare(entry, {"TUI_ARCADE_HOME": root})
            self.assertEqual(problem, "")
            before = signal.getsignal(signal.SIGINT)
            self.assertEqual(launch(entry, env), (3, None))
            self.assertIs(signal.getsignal(signal.SIGINT), before)
            ran = Path(env["TUI_ARCADE_DATA_DIR"]) / "ran"
            self.assertEqual(Path(ran.read_text()).resolve(), entry.cwd)

    def test_missing_entry_and_issues_block_before_handoff(self):
        with tempfile.TemporaryDirectory() as root:
            missing = self.entry(root, ["./bin/game"], source="installed")
            self.assertEqual(prepare(missing, {"TUI_ARCADE_HOME": root})[1], "游戏入口缺失，请重新安装")
            future = catalog.parse(write(root, "f", manifest_version=9))
            self.assertIn("需要更新平台", prepare(future, {"TUI_ARCADE_HOME": root})[1])

    def test_os_errors_are_reported(self):
        with tempfile.TemporaryDirectory() as root:
            entry = self.entry(root, ["/nonexistent/game"])
            env, _ = prepare(entry, {"TUI_ARCADE_HOME": root})
            code, error = launch(entry, env)
        self.assertIsNone(code)
        self.assertTrue(error)


if __name__ == "__main__":
    unittest.main()
