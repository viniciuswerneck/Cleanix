import unittest

from cleanix import systeminfo as si


class FormatBytesTest(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(si.format_bytes(0), "0 B")

    def test_bytes(self):
        self.assertEqual(si.format_bytes(999), "999 B")

    def test_kilobytes(self):
        self.assertEqual(si.format_bytes(1024), "1,00 KB")

    def test_gigabytes_one_decimal(self):
        self.assertEqual(si.format_bytes(int(78.4 * 1024**3)), "78,4 GB")

    def test_gigabytes_two_decimals(self):
        self.assertEqual(si.format_bytes(int(2.48 * 1024**3)), "2,48 GB")


class ParseMeminfoTest(unittest.TestCase):
    TEXT = ("MemTotal:       16000000 kB\n"
            "MemFree:         2000000 kB\n"
            "MemAvailable:    6000000 kB\n")

    def test_used_and_percent(self):
        info = si.parse_meminfo(self.TEXT)
        self.assertEqual(info.total, 16000000 * 1024)
        self.assertEqual(info.available, 6000000 * 1024)
        self.assertEqual(info.used, 10000000 * 1024)
        self.assertAlmostEqual(info.percent_used, 62.5)


class ParseCpuTimesTest(unittest.TestCase):
    TEXT = "cpu  100 0 100 800 0 0 0 0 0 0\ncpu0 1 2 3 4\n"

    def test_busy_and_total(self):
        busy, total = si.parse_cpu_times(self.TEXT)
        self.assertEqual(busy, 200)
        self.assertEqual(total, 1000)


class SampleCpuTest(unittest.TestCase):
    def test_first_sample_is_zero(self):
        percent, sample = si.sample_cpu(None)
        self.assertEqual(percent, 0.0)
        self.assertIsInstance(sample, tuple)


class HealthStateTest(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(si.health_state(50), "ok")
        self.assertEqual(si.health_state(20), "ok")
        self.assertEqual(si.health_state(19.9), "warn")
        self.assertEqual(si.health_state(10), "warn")
        self.assertEqual(si.health_state(9.9), "bad")


class DiskInfoTest(unittest.TestCase):
    def test_used_plus_free_is_total(self):
        info = si.get_disk_info("/")
        self.assertEqual(info.used + info.free, info.total)
        self.assertGreaterEqual(info.percent_used, 0)
        self.assertLessEqual(info.percent_used, 100)
