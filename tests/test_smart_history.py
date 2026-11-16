import tempfile
import unittest
from pathlib import Path

from cleanix import smart_history


class SmartHistoryTest(unittest.TestCase):
    def _parsed(self, overall='passed', attrs=None):
        attrs = attrs or []
        return {'overall': overall, 'overall_text': overall.upper(),
                'attributes': attrs}

    def test_record_and_last(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'smart.json'
            parsed = self._parsed('passed', [
                {'name': 'Reallocated_Sector_Ct', 'raw': '0', 'critical': True},
            ])
            smart_history.record_check('sda', 'KINGSTON', parsed, path=path)
            last = smart_history.last_for_disk('sda', 'KINGSTON', path=path)
            self.assertIsNotNone(last)
            self.assertEqual(last['overall'], 'passed')
            self.assertEqual(last['critical'].get('Reallocated_Sector_Ct'), '0')

    def test_compare_no_previous(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'smart.json'
            msg = smart_history.compare_previous(
                'sda', 'KINGSTON', self._parsed('passed'), path=path)
            self.assertIsNone(msg)

    def test_compare_overall_worsened(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'smart.json'
            smart_history.record_check('sda', 'M', self._parsed('passed'), path=path)
            msg = smart_history.compare_previous(
                'sda', 'M', self._parsed('failed'), path=path)
            self.assertIsNotNone(msg)
            self.assertTrue(msg.get('worsened'))

    def test_compare_critical_attribute_increased(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'smart.json'
            smart_history.record_check('sda', 'M', self._parsed('passed', [
                {'name': 'Current_Pending_Sector', 'raw': '0', 'critical': True},
            ]), path=path)
            msg = smart_history.compare_previous(
                'sda', 'M', self._parsed('passed', [
                    {'name': 'Current_Pending_Sector', 'raw': '2', 'critical': True},
                ]), path=path)
            self.assertIsNotNone(msg)
            self.assertTrue(any('Current_Pending_Sector' in m for m in msg.get('messages', [])))

    def test_compare_no_change(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'smart.json'
            parsed = self._parsed('passed', [
                {'name': 'Reallocated_Sector_Ct', 'raw': '0', 'critical': True},
            ])
            smart_history.record_check('sda', 'M', parsed, path=path)
            msg = smart_history.compare_previous('sda', 'M', parsed, path=path)
            self.assertIsNone(msg)

    def test_limit_per_disk(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'smart.json'
            for i in range(25):
                smart_history.record_check(
                    'sda', 'M', self._parsed('passed'), path=path)
            data = smart_history.load_history(path=path)
            self.assertLessEqual(len(data), 20)


if __name__ == '__main__':
    unittest.main()
