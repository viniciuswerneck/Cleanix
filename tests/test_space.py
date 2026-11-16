import os
import tempfile
import unittest
from pathlib import Path

from cleanix import space


class LargestFilesTest(unittest.TestCase):
    def test_finds_largest_files(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'a.txt').write_bytes(b'a' * 10)
            (root / 'b.txt').write_bytes(b'b' * 100)
            sub = root / 'sub'
            sub.mkdir()
            (sub / 'c.txt').write_bytes(b'c' * 50)
            result = space.scan_largest(str(root), top_files=5, top_dirs=5)
            files = result['files']
            self.assertEqual(files[0]['path'], str(root / 'b.txt'))
            self.assertEqual(files[0]['size'], 100)
            names = [Path(f['path']).name for f in files]
            self.assertIn('c.txt', names)

    def test_does_not_follow_symlinks(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            real = root / 'real'
            real.mkdir()
            (real / 'big.bin').write_bytes(b'x' * 200)
            outside = Path(tempfile.mkdtemp())
            try:
                (outside / 'secret.bin').write_bytes(b'y' * 500)
                link = root / 'linkout'
                try:
                    link.symlink_to(outside, target_is_directory=True)
                except (OSError, NotImplementedError):
                    self.skipTest('symlinks not supported')
                result = space.scan_largest(str(root), top_files=10, top_dirs=10)
                paths = [f['path'] for f in result['files']]
                self.assertTrue(any(p.endswith('big.bin') for p in paths))
                self.assertFalse(any('secret.bin' in p for p in paths))
            finally:
                for p in outside.iterdir():
                    p.unlink()
                outside.rmdir()

    def test_cancel_stops(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for i in range(5):
                (root / f'f{i}').write_bytes(b'z' * 10)
            result = space.scan_largest(str(root), top_files=10, top_dirs=10,
                                        cancel=lambda: True)
            self.assertTrue(result.get('cancelled'))


class DuplicatesTest(unittest.TestCase):
    def test_finds_duplicate_groups(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            content = b'hello world duplicate content' * 10
            (root / 'a.bin').write_bytes(content)
            sub = root / 'sub'
            sub.mkdir()
            (sub / 'b.bin').write_bytes(content)
            (root / 'c.bin').write_bytes(b'different' * 20)
            (root / 'small.bin').write_bytes(content[:10])  # same prefix but small/diff size
            result = space.find_duplicates(str(root), min_size=1)
            groups = result['groups']
            # one group with a.bin and b.bin
            found = False
            for g in groups:
                paths = sorted(Path(p).name for p in g['files'])
                if paths == ['a.bin', 'b.bin']:
                    found = True
                    self.assertEqual(g['size'], len(content))
                    self.assertEqual(g['count'], 2)
            self.assertTrue(found, groups)

    def test_ignores_different_content_same_size(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'x.bin').write_bytes(b'aaaaaaaaaa')
            (root / 'y.bin').write_bytes(b'bbbbbbbbbb')
            result = space.find_duplicates(str(root), min_size=1)
            self.assertEqual(result['groups'], [])

    def test_cancel(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'a').write_bytes(b'x' * 100)
            (root / 'b').write_bytes(b'x' * 100)
            result = space.find_duplicates(str(root), min_size=1, cancel=lambda: True)
            self.assertTrue(result.get('cancelled'))


if __name__ == '__main__':
    unittest.main()

class ExcludeAndFilterTest(unittest.TestCase):
    def test_excludes_folder(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'keep.txt').write_bytes(b'a' * 50)
            skip = root / 'skipme'
            skip.mkdir()
            (skip / 'big.txt').write_bytes(b'b' * 500)
            result = space.scan_largest(str(root), top_files=10, top_dirs=10,
                                        exclude=[str(skip)])
            paths = [f['path'] for f in result['files']]
            self.assertTrue(any('keep.txt' in p for p in paths))
            self.assertFalse(any('big.txt' in p for p in paths))

    def test_min_size_filters_large_files(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'small.txt').write_bytes(b'a' * 10)
            (root / 'big.txt').write_bytes(b'b' * 100)
            result = space.scan_largest(str(root), top_files=10, top_dirs=10,
                                        min_size=50)
            paths = [Path(f['path']).name for f in result['files']]
            self.assertEqual(paths, ['big.txt'])

    def test_duplicates_respects_exclude(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            content = b'x' * 200
            (root / 'a.bin').write_bytes(content)
            skip = root / 'skip'
            skip.mkdir()
            (skip / 'b.bin').write_bytes(content)
            result = space.find_duplicates(str(root), min_size=1, exclude=[str(skip)])
            self.assertEqual(result['groups'], [])


class TrashSelectionTest(unittest.TestCase):
    def test_empty_selection(self):
        ok, err = space.validate_trash_selection([], [])
        self.assertFalse(ok)

    def test_cannot_trash_all_copies_in_group(self):
        groups = [{'files': ['/a/x', '/a/y'], 'size': 10, 'count': 2, 'wasted': 10, 'hash': 'h'}]
        ok, err = space.validate_trash_selection(['/a/x', '/a/y'], groups)
        self.assertFalse(ok)
        self.assertEqual(err, 'space.trash.keep_one')

    def test_can_trash_some_copies(self):
        groups = [{'files': ['/a/x', '/a/y', '/a/z'], 'size': 10, 'count': 3, 'wasted': 20, 'hash': 'h'}]
        ok, err = space.validate_trash_selection(['/a/x'], groups)
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_non_duplicate_files_ok(self):
        ok, err = space.validate_trash_selection(['/a/b'], [])
        self.assertTrue(ok)
