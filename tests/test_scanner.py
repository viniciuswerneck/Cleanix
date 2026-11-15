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


class CleanerCategoriesTest(unittest.TestCase):
    def test_memory_is_not_a_cleaner_category(self):
        keys = {cat.key for cat in scanner.CATEGORIES}
        self.assertNotIn("memory", keys)

    def test_apt_is_a_selectable_cleaner_category(self):
        apt = next(cat for cat in scanner.CATEGORIES if cat.key == "apt")
        self.assertTrue(apt.requires_admin)
        self.assertTrue(apt.admin_command)
        self.assertEqual(apt.kind, "apt")


class AdminCategoriesTest(unittest.TestCase):
    @staticmethod
    def _apt(root):
        return scanner.Category(
            "apt", "Cache do APT", (str(root),), "apt",
            requires_admin=True,
            admin_command="/usr/bin/apt-get clean",
        )

    def test_apt_scan_counts_only_package_files(self):
        with tempfile.TemporaryDirectory() as d:
            Path(os.path.join(d, "pacote.deb")).write_bytes(b"x" * 10)
            Path(os.path.join(d, "lock")).write_bytes(b"")
            os.makedirs(os.path.join(d, "partial"))
            Path(os.path.join(d, "partial", "outro.deb")).write_bytes(b"y" * 5)

            r = scanner.scan_category(self._apt(d))

        self.assertTrue(r.available)
        self.assertEqual((r.files, r.bytes), (2, 15))

    def test_apt_clean_runs_admin_command_and_reports_freed(self):
        with tempfile.TemporaryDirectory() as d:
            package = Path(os.path.join(d, "pacote.deb"))
            package.write_bytes(b"x" * 10)
            cat = self._apt(d)

            def fake(command, as_root=False, timeout=None):
                package.unlink()
                return mock.Mock(ok=True, error="")

            with mock.patch.object(scanner, "execute_command",
                                   side_effect=fake) as run:
                r = scanner.clean_category(cat)

        run.assert_called_once_with(cat.admin_command, as_root=True)
        self.assertTrue(r.available)
        self.assertEqual((r.bytes, r.files, r.errors), (10, 1, 0))

    def test_apt_clean_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            Path(os.path.join(d, "pacote.deb")).write_bytes(b"x" * 10)
            cat = self._apt(d)

            with mock.patch.object(
                    scanner, "execute_command",
                    return_value=mock.Mock(ok=False, error="senha cancelada")):
                r = scanner.clean_category(cat)

        self.assertTrue(r.available)
        self.assertEqual((r.bytes, r.files, r.errors), (0, 0, 1))
        self.assertIn("senha", r.error)


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
