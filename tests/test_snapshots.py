import json
import tempfile
import unittest
from pathlib import Path

from cleanix import snapshots, xray


def sample_snapshot():
    return {
        'bios': {'summary': 'BIOS: ACME', 'details': 'd', 'fields': {'product_name': 'PC'}},
        'hardware': {'summary': 'CPU', 'details': 'h'},
        'programs': {
            'apt': [('bash', '5', '1 MB'), ('vim', '9', '2 MB')],
            'snap': [('firefox', '120', '')],
            'flatpak_apps': [], 'flatpak_runtimes': 1, 'summary': 'APT: 2'},
        'network': {'summary': 'n', 'details': 'MAC: aa:bb:cc:dd:ee:ff', 'interfaces': []},
        'system': {'summary': 's', 'details': 'd', 'updates': 3},
        'disks': [{'name': 'sda', 'type': 'disk', 'size_total': 100, 'size_used': 50, 'pct_used': 50, 'mount_point': '/'}],
        'alerts': [{'level': 'info', 'text': '3 atualizações pendentes'}],
        'limitations': [],
        'smart_known': [],
    }


class BuildReportDataTest(unittest.TestCase):
    def test_build_report_data_redacts(self):
        data = xray.build_report_data(
            sample_snapshot(), bios_details='Serial Number: SEC\n', redact=True)
        self.assertTrue(data['meta']['redacted'])
        self.assertNotIn('SEC', json.dumps(data, ensure_ascii=False))
        self.assertNotIn('aa:bb:cc:dd:ee:ff', json.dumps(data, ensure_ascii=False))
        self.assertEqual(data['programs']['apt'][0]['name'], 'bash')

    def test_build_report_json_uses_data(self):
        text = xray.build_report_json(sample_snapshot())
        data = json.loads(text)
        self.assertIn('meta', data)
        self.assertIn('programs', data)


class SnapshotStorageTest(unittest.TestCase):
    def test_save_list_load(self):
        with tempfile.TemporaryDirectory() as d:
            data = xray.build_report_data(sample_snapshot())
            path = snapshots.save_snapshot(data, directory=d)
            self.assertTrue(Path(path).exists())
            items = snapshots.list_snapshots(directory=d)
            self.assertEqual(len(items), 1)
            self.assertTrue(items[0]['path'])
            loaded = snapshots.load_snapshot(items[0]['path'])
            self.assertEqual(loaded['meta']['product'], 'PC')

    def test_limit_retention(self):
        with tempfile.TemporaryDirectory() as d:
            for i in range(5):
                data = xray.build_report_data(sample_snapshot())
                data['meta']['generated'] = f'2026-01-01 00:00:{i:02d}'
                snapshots.save_snapshot(data, directory=d, keep=3)
            items = snapshots.list_snapshots(directory=d)
            self.assertLessEqual(len(items), 3)


if __name__ == '__main__':
    unittest.main()
