import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

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


class TmpRulesTest(unittest.TestCase):
    def _cat(self, root):
        return scanner.Category("tmp", "Temporários", (root,), "tmp", min_age=600)

    def test_old_file_counted_new_file_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.path.join(d, "old")
            new = os.path.join(d, "new")
            Path(old).write_bytes(b"o" * 10)
            Path(new).write_bytes(b"n" * 10)
            now = time.time()
            os.utime(old, (now - 700, now - 700))
            r = scanner.scan_category(self._cat(d), now=now, open_set=set())
            self.assertEqual((r.files, r.bytes), (1, 10))

    def test_open_file_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "inuse")
            Path(p).write_bytes(b"x" * 10)
            now = time.time()
            os.utime(p, (now - 700, now - 700))
            r = scanner.scan_category(self._cat(d), now=now,
                                      open_set={os.path.realpath(p)})
            self.assertEqual(r.files, 0)

    def test_open_subtree_pruned(self):
        with tempfile.TemporaryDirectory() as d:
            sub = os.path.join(d, "live")
            os.makedirs(sub)
            p = os.path.join(sub, "f")
            Path(p).write_bytes(b"x" * 10)
            now = time.time()
            os.utime(p, (now - 700, now - 700))
            r = scanner.scan_category(self._cat(d), now=now,
                                      open_set={os.path.realpath(sub)})
            self.assertEqual(r.files, 0)

    def test_clean_keeps_recent_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "recent")
            Path(p).write_bytes(b"x" * 10)
            now = time.time()
            os.utime(p, (now - 60, now - 60))
            scanner.clean_category(self._cat(d), now=now, open_set=set())
            self.assertTrue(os.path.exists(p))

    def test_clean_prunes_empty_old_dirs_but_not_root(self):
        with tempfile.TemporaryDirectory() as d:
            sub = os.path.join(d, "olddir")
            os.makedirs(sub)
            f = os.path.join(sub, "f")
            Path(f).write_bytes(b"x" * 10)
            now = time.time()
            os.utime(f, (now - 700, now - 700))
            os.utime(sub, (now - 700, now - 700))
            scanner.clean_category(self._cat(d), now=now, open_set=set())
            self.assertTrue(os.path.isdir(d))
            self.assertFalse(os.path.exists(sub))

    def test_proc_unavailable_disables_tmp(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(scanner, "proc_available", return_value=False):
                r = scanner.scan_category(self._cat(d))
            self.assertFalse(r.available)
