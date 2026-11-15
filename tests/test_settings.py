import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cleanix import settings


class LoadSettingsTest(unittest.TestCase):
    def test_defaults_when_file_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            conf = settings.load_settings(Path(tmp) / "config.json")
        self.assertTrue(conf.confirm_before_clean)
        self.assertTrue(conf.keep_history)

    def test_invalid_json_returns_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text("{isto não é json", encoding="utf-8")
            conf = settings.load_settings(path)
        self.assertEqual(conf, settings.Settings())

    def test_reads_saved_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(
                json.dumps({"confirm_before_clean": False,
                            "keep_history": False}),
                encoding="utf-8")
            conf = settings.load_settings(path)
        self.assertFalse(conf.confirm_before_clean)
        self.assertFalse(conf.keep_history)

    def test_ignores_invalid_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({"confirm_before_clean": "sim"}),
                            encoding="utf-8")
            conf = settings.load_settings(path)
        self.assertTrue(conf.confirm_before_clean)

    def test_ignores_unknown_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({"inexistente": 1}), encoding="utf-8")
            conf = settings.load_settings(path)
        self.assertEqual(conf, settings.Settings())


class SaveSettingsTest(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "config.json"
            original = settings.Settings(confirm_before_clean=False,
                                         keep_history=True)
            settings.save_settings(original, path)
            self.assertTrue(path.exists())
            self.assertEqual(settings.load_settings(path), original)

    def test_config_path_respects_xdg_config_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}):
                path = settings.config_path()
        self.assertEqual(path, Path(tmp) / "cleanix" / "config.json")


if __name__ == "__main__":
    unittest.main()
