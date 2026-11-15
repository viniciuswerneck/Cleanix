import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cleanix import memory


class ReadMeminfoTest(unittest.TestCase):
    def test_parses_kilobytes_into_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(os.path.join(d, "meminfo"))
            path.write_text(
                "MemTotal:       1000 kB\n"
                "MemAvailable:    400 kB\n"
                "Cached:          300 kB\n"
                "SReclaimable:     50 kB\n"
                "Shmem:            25 kB\n",
                encoding="utf-8",
            )
            values = memory.read_meminfo(path)

        self.assertEqual(values["MemTotal"], 1000 * 1024)
        self.assertEqual(values["MemAvailable"], 400 * 1024)
        self.assertEqual(values["Cached"], 300 * 1024)

    def test_missing_file_returns_empty_dict(self):
        self.assertEqual(memory.read_meminfo("/caminho/que/nao/existe"), {})


class ReclaimableMemoryTest(unittest.TestCase):
    def test_discounts_shared_memory(self):
        values = {"Cached": 300, "SReclaimable": 50, "Shmem": 25}
        self.assertEqual(memory.reclaimable_memory(values), 325)

    def test_never_negative(self):
        values = {"Cached": 10, "SReclaimable": 0, "Shmem": 50}
        self.assertEqual(memory.reclaimable_memory(values), 0)


class ReleaseMemoryTest(unittest.TestCase):
    def test_reports_available_increase(self):
        before = {"MemAvailable": 400}
        after = {"MemAvailable": 900}
        with mock.patch.object(
                memory, "read_meminfo", side_effect=[before, after]), \
                mock.patch.object(
                    memory, "execute_command",
                    return_value=mock.Mock(ok=True, error="")) as run:
            result = memory.release_memory()

        run.assert_called_once_with(memory.DROP_CACHES_COMMAND, as_root=True)
        self.assertTrue(result.ok)
        self.assertIn("500 B", result.output)

    def test_unavailable_without_meminfo(self):
        with mock.patch.object(memory, "read_meminfo", return_value={}), \
                mock.patch.object(memory, "execute_command") as run:
            result = memory.release_memory()

        run.assert_not_called()
        self.assertFalse(result.ok)
        self.assertTrue(result.error)

    def test_failure_returns_command_error(self):
        with mock.patch.object(
                memory, "read_meminfo",
                return_value={"MemAvailable": 400}), \
                mock.patch.object(
                    memory, "execute_command",
                    return_value=mock.Mock(ok=False,
                                           error="senha cancelada")):
            result = memory.release_memory()

        self.assertFalse(result.ok)
        self.assertIn("senha", result.error)


if __name__ == "__main__":
    unittest.main()
