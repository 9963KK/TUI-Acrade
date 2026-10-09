"""Verify command installation and argument forwarding without building the platform."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "posix", "Requires POSIX shell")
class InstallCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "Arcade ' $cash `literal`"
        (self.repo / "scripts").mkdir(parents=True)
        self.script = self.repo / "scripts" / "install-tplay.sh"
        shutil.copy2(ROOT / "scripts" / "install-tplay.sh", self.script)
        (self.repo / "play.sh").write_text('#!/bin/sh\nprintf "<%s>\\n" "$@"\n')
        (self.repo / "play.sh").chmod(0o755)
        self.bin = Path(self.temp.name) / "user bin"
        self.env = {**os.environ, "TPLAY_BIN_DIR": str(self.bin)}

    def run_installer(self, *args):
        return subprocess.run([str(self.script), *args], env=self.env, capture_output=True, text=True)

    def test_install_update_forward_arguments_and_uninstall(self):
        for _ in range(2):
            result = self.run_installer()
            self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([str(self.bin / "tplay"), "install", "path with space", "$literal"],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["<install>", "<path with space>", "<$literal>"])
        self.assertEqual(self.run_installer("--uninstall").returncode, 0)
        self.assertFalse((self.bin / "tplay").exists())

    def test_other_commands_and_dangling_symlinks_are_preserved(self):
        self.bin.mkdir()
        target = self.bin / "tplay"
        target.write_text("another program")
        self.assertEqual(self.run_installer().returncode, 1)
        self.run_installer("--uninstall")
        self.assertEqual(target.read_text(), "another program")
        target.unlink()
        target.symlink_to(self.bin / "missing")
        self.assertEqual(self.run_installer().returncode, 1)
        self.assertTrue(target.is_symlink())

    def test_help_and_invalid_arguments(self):
        self.assertEqual(self.run_installer("--help").returncode, 0)
        for args in [("--unknown",), ("--uninstall", "extra")]:
            self.assertEqual(self.run_installer(*args).returncode, 2)
        self.assertFalse((self.bin / "tplay").exists())
