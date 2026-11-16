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


class SmartParseTest(unittest.TestCase):
    PASSED = """
=== START OF READ SMART DATA SECTION ===
SMART overall-health self-assessment test result: PASSED

ID# ATTRIBUTE_NAME          VALUE WORST THRESH TYPE      UPDATED  WHEN_FAILED RAW_VALUE
  5 Reallocated_Sector_Ct   100   100   010    Pre-fail  Always       -       0
197 Current_Pending_Sector  100   100   000    Old_age   Always       -       0
198 Offline_Uncorrectable   100   100   000    Old_age   Always       -       0
"""
    FAILED = "SMART overall-health self-assessment test result: FAILED!\n"
    UNKNOWN = "some output without health line\n"

    def test_passed_and_key_attributes(self):
        r = si.parse_smartctl(self.PASSED)
        self.assertEqual(r['overall'], 'passed')
        names = [a['name'] for a in r['attributes']]
        self.assertIn('Reallocated_Sector_Ct', names)

    def test_failed(self):
        r = si.parse_smartctl(self.FAILED)
        self.assertEqual(r['overall'], 'failed')

    def test_unknown(self):
        r = si.parse_smartctl(self.UNKNOWN)
        self.assertEqual(r['overall'], 'unknown')


class PhysicalDisksForSmartTest(unittest.TestCase):
    def test_filters_physical_disks(self):
        disks = [
            {'name': 'sda', 'type': 'disk', 'size_total': 100},
            {'name': 'sda1', 'type': 'part', 'size_total': 50},
            {'name': 'zram0', 'type': 'disk', 'size_total': 10},
            {'name': 'loop0', 'type': 'disk', 'size_total': 10},
        ]
        out = si.physical_disks_for_smart(disks)
        self.assertEqual([d['name'] for d in out], ['sda'])


class SensorReadTest(unittest.TestCase):
    def test_read_thermal_temps(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            z0 = base / 'thermal_zone0'
            z0.mkdir()
            (z0 / 'type').write_text('x86_pkg_temp\n')
            (z0 / 'temp').write_text('49000\n')
            z1 = base / 'thermal_zone1'
            z1.mkdir()
            (z1 / 'temp').write_text('not-a-number\n')
            temps = si.read_thermal_temps(d)
        self.assertEqual(len(temps), 1)
        self.assertEqual(temps[0]['type'], 'x86_pkg_temp')
        self.assertEqual(temps[0]['temp_c'], 49.0)

    def test_read_hwmon_temps(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            h = base / 'hwmon3'
            h.mkdir()
            (h / 'name').write_text('coretemp\n')
            (h / 'temp1_input').write_text('49000\n')
            (h / 'temp1_label').write_text('Package id 0\n')
            (h / 'temp2_input').write_text('47000\n')
            temps = si.read_hwmon_temps(d)
        labels = {x['label'] for x in temps}
        self.assertIn('Package id 0', labels)
        self.assertTrue(any(x['name'] == 'coretemp' for x in temps))

    def test_collect_sensors_empty_when_missing(self):
        with tempfile.TemporaryDirectory() as d:
            data = si.collect_sensors(thermal_path=d + '/t', hwmon_path=d + '/h')
        self.assertEqual(data.get('readings'), [])
        self.assertEqual(data.get('summary'), '')


class PowerSupplyReadTest(unittest.TestCase):
    def test_read_power_supply_battery(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            bat = base / 'BAT1'
            bat.mkdir()
            (bat / 'type').write_text('Battery\n')
            (bat / 'status').write_text('Discharging\n')
            (bat / 'capacity').write_text('80\n')
            (bat / 'energy_full').write_text('1537000\n')
            (bat / 'energy_full_design').write_text('2500000\n')
            (bat / 'cycle_count').write_text('120\n')
            ac = base / 'ACAD'
            ac.mkdir()
            (ac / 'type').write_text('Mains\n')
            (ac / 'online').write_text('0\n')
            info = si.read_power_supply(d)
        self.assertTrue(info.get('present'))
        self.assertEqual(info.get('status'), 'Discharging')
        self.assertEqual(info.get('capacity'), 80)
        self.assertEqual(info.get('cycle_count'), 120)
        self.assertAlmostEqual(info.get('health_pct'), 61.48, places=1)
        self.assertFalse(info.get('ac_online'))
        self.assertIn('80%', info.get('summary', ''))

    def test_read_power_supply_missing(self):
        with tempfile.TemporaryDirectory() as d:
            info = si.read_power_supply(d)
        self.assertFalse(info.get('present'))
        self.assertEqual(info.get('summary', ''), '')
