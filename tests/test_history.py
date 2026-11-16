import tempfile
import unittest
from pathlib import Path

from cleanix import history, i18n


def entry(n: int) -> history.HistoryEntry:
    return history.HistoryEntry(
        timestamp="2026-11-15T10:20:00",
        bytes=n, files=1, categories=("trash",), errors=0)


class HistoryTest(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "h.json"
            history.append_entry(entry(100), path=p)
            self.assertEqual(history.load_history(path=p), [entry(100)])

    def test_missing_file_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(history.load_history(path=Path(d) / "nope.json"), [])

    def test_corrupt_file_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "h.json"
            p.write_text("{oops", encoding="utf-8")
            self.assertEqual(history.load_history(path=p), [])

    def test_caps_at_200(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "h.json"
            for i in range(205):
                history.append_entry(entry(i), path=p)
            loaded = history.load_history(path=p)
            self.assertEqual(len(loaded), 200)
            self.assertEqual(loaded[0].bytes, 5)
            self.assertEqual(loaded[-1].bytes, 204)

    def test_clear(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "h.json"
            history.append_entry(entry(1), path=p)
            history.clear_history(path=p)
            self.assertFalse(p.exists())

    def test_atomic_leaves_no_tmp_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "h.json"
            history.append_entry(entry(1), path=p)
            self.assertEqual(sorted(x.name for x in Path(d).iterdir()), ["h.json"])

    def test_format_timestamp(self):
        self.assertEqual(history.format_timestamp("2026-11-15T10:20:00"),
                         "15/11/2026 10:20")

    def test_format_timestamp_english(self):
        i18n.set_language("en")
        try:
            self.assertEqual(history.format_timestamp("2026-11-15T10:20:00"),
                             "11/15/2026 10:20")
        finally:
            i18n.set_language("pt_BR")
