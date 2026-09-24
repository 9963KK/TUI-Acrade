import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import support  # noqa: F401
from tank_battle.storage import is_corrupt, read_best, save_best, score_path


class StorageTests(unittest.TestCase):
    def test_roundtrip_never_lowers_record(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sub/scores.json"
            self.assertEqual(read_best(path), 0)
            self.assertTrue(save_best(200, path))
            self.assertTrue(save_best(100, path))
            self.assertEqual(read_best(path), 200)
            self.assertEqual(len(list(path.parent.iterdir())), 1)

    def test_unreadable_record_is_preserved_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scores.json"
            for data in ("invalid", "null", "[]", '{"tank_best": true}', '{"tank_best": -1}', '{"tank_best": "3"}'):
                path.write_text(data)
                self.assertEqual(read_best(path), 0)
                self.assertTrue(is_corrupt(path))
            self.assertTrue(save_best(300, path))
            self.assertEqual(json.loads(path.read_text())["tank_best"], 300)
            self.assertEqual((Path(directory) / "scores.json.corrupt").read_text(), '{"tank_best": "3"}')
            path.write_text("again")
            self.assertTrue(save_best(10, path))
            self.assertEqual(len(list(Path(directory).glob("scores.json.corrupt*"))), 2)

    def test_legacy_record_is_imported_once(self):
        with tempfile.TemporaryDirectory() as directory:
            legacy = Path(directory) / "old.json"
            legacy.write_text('{"tank_best": 900}')
            path = Path(directory) / "games/tank/scores.json"
            self.assertEqual(read_best(path, legacy), 900)
            self.assertTrue(path.exists())
            self.assertTrue(legacy.exists())
            save_best(1200, path)
            legacy.write_text('{"tank_best": 5000}')
            self.assertEqual(read_best(path, legacy), 1200)
            # 显式指定存档路径而不给旧路径时，不读取任何旧记录。
            fresh = Path(directory) / "fresh.json"
            self.assertEqual(read_best(fresh), 0)
            self.assertFalse(fresh.exists())

    def test_write_failure_preserves_existing_record(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scores.json"
            save_best(200, path)
            with patch.object(Path, "replace", side_effect=OSError("disk full")):
                self.assertFalse(save_best(300, path))
            self.assertEqual(read_best(path), 200)
            self.assertEqual(len(list(path.parent.iterdir())), 1)

    def test_invalid_scores(self):
        for score in (-1, True, 2.4, "20"):
            with self.assertRaises(ValueError):
                save_best(score)

    def test_location_follows_platform_rules(self):
        self.assertEqual(score_path({"TUI_ARCADE_DATA_DIR": "/given"}), Path("/given/scores.json"))
        self.assertEqual(score_path({"TUI_ARCADE_HOME": "/t"}), Path("/t/data/games/tank/scores.json"))
        self.assertEqual(score_path({"XDG_DATA_HOME": "/x"}), Path("/x/tui-arcade/games/tank/scores.json"))


if __name__ == "__main__":
    unittest.main()
