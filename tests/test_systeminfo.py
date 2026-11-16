import tempfile
import unittest
from pathlib import Path

from cleanix import i18n
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


class LocalizedBytesTest(unittest.TestCase):
    def tearDown(self):
        i18n.set_language('pt_BR')

    def test_english_uses_dot(self):
        i18n.set_language('en')
        self.assertEqual(si.format_bytes(1024), '1.00 KB')
        self.assertEqual(si.format_bytes(int(78.4 * 1024**3)), '78.4 GB')

    def test_spanish_uses_comma(self):
        i18n.set_language('es')
        self.assertEqual(si.format_bytes(1024), '1,00 KB')


class DistroTest(unittest.TestCase):
    def _write(self, text):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / 'os-release'
        path.write_text(text, encoding='utf-8')
        return str(path)

    def test_prefers_pretty_name(self):
        path = self._write('NAME="Ubuntu"\nVERSION_ID="26.04"\n'
                           'PRETTY_NAME="Ubuntu 26.04.1 LTS"\n')
        self.assertEqual(si.distro_name(path), 'Ubuntu 26.04.1 LTS')

    def test_falls_back_to_name_and_version(self):
        path = self._write('NAME="Debian GNU/Linux"\nVERSION_ID="12"\n')
        self.assertEqual(si.distro_name(path), 'Debian GNU/Linux 12')

    def test_missing_file_returns_linux(self):
        self.assertEqual(si.distro_name('/nao/existe'), 'Linux')

    def test_info_returns_name_and_version(self):
        path = self._write('NAME="Ubuntu"\nVERSION_ID="26.04"\n'
                           'PRETTY_NAME="Ubuntu 26.04.1 LTS"\n')
        self.assertEqual(si.distro_info(path), ('Ubuntu', '26.04'))

    def test_info_missing_file(self):
        self.assertEqual(si.distro_info('/nao/existe'), ('Linux', ''))
