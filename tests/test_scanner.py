import os
import tempfile
import time
import unittest
from pathlib import Path

from cleanix import scanner


def cache_cat(root: str) -> scanner.Category:
    return scanner.Category(key="cache", label="Teste", roots=(root,), kind="cache")


class IsWithinTest(unittest.TestCase):
    def test_inside(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a", "b.txt")
            os.makedirs(os.path.dirname(p))
            Path(p).write_bytes(b"")
            self.assertTrue(scanner.is_within(p, [d]))

    def test_dotdot_escape(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(scanner.is_within(os.path.join(d, "..", "x"), [d]))

    def test_symlink_escape(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as out:
            os.symlink(out, os.path.join(d, "link"))
            self.assertFalse(scanner.is_within(os.path.join(d, "link", "x"), [d]))


class ScanCacheTest(unittest.TestCase):
    def test_counts_regular_files(self):
        with tempfile.TemporaryDirectory() as d:
            Path(os.path.join(d, "a")).write_bytes(b"x" * 10)
            os.makedirs(os.path.join(d, "sub"))
            Path(os.path.join(d, "sub", "b")).write_bytes(b"y" * 5)
            r = scanner.scan_category(cache_cat(d), open_set=set())
            self.assertEqual((r.files, r.bytes), (2, 15))
            self.assertTrue(r.available)

    def test_ignores_symlinks(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as out:
            Path(os.path.join(out, "big")).write_bytes(b"z" * 100)
            os.symlink(os.path.join(out, "big"), os.path.join(d, "link"))
            r = scanner.scan_category(cache_cat(d), open_set=set())
            self.assertEqual((r.files, r.bytes), (0, 0))


class CleanCacheTest(unittest.TestCase):
    def test_removes_files_keeps_root(self):
        with tempfile.TemporaryDirectory() as d:
            Path(os.path.join(d, "a")).write_bytes(b"x" * 10)
            os.makedirs(os.path.join(d, "sub"))
            Path(os.path.join(d, "sub", "b")).write_bytes(b"y" * 5)
            r = scanner.clean_category(cache_cat(d), open_set=set())
            self.assertEqual((r.files, r.bytes), (2, 15))
            self.assertTrue(os.path.isdir(d))
            self.assertEqual(os.listdir(d), [])


class RequiresAdminTest(unittest.TestCase):
    def test_apt_is_unavailable_and_not_scanned(self):
        cat = scanner.Category("apt", "Cache do APT",
                               ("/var/cache/apt/archives",), "cache",
                               requires_admin=True)
        r = scanner.scan_category(cat)
        self.assertFalse(r.available)
        self.assertEqual((r.bytes, r.files), (0, 0))
