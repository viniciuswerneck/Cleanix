import unittest
from unittest import mock

from cleanix import adjustments
from cleanix.execution import Result

ANIMATIONS_SCHEMA = 'org.gnome.desktop.interface'
PRIVACY_SCHEMA = 'org.gnome.desktop.privacy'


class ParseBoolTest(unittest.TestCase):
    def test_true(self):
        self.assertIs(adjustments.parse_gsettings_bool('true\n'), True)

    def test_false(self):
        self.assertIs(adjustments.parse_gsettings_bool('false'), False)

    def test_garbage_is_unknown(self):
        self.assertIsNone(adjustments.parse_gsettings_bool('talvez'))


class AnimationsTest(unittest.TestCase):
    def test_get_reads_the_schema(self):
        with mock.patch.object(
                adjustments, 'execute_command',
                return_value=Result(True, 'true\n', '')) as run:
            self.assertIs(adjustments.get_animations(), True)

        run.assert_called_once_with(
            f'gsettings get {ANIMATIONS_SCHEMA} enable-animations')

    def test_get_failure_returns_none(self):
        with mock.patch.object(
                adjustments, 'execute_command',
                return_value=Result(False, '', 'sem gsettings')):
            self.assertIsNone(adjustments.get_animations())

    def test_set_writes_false(self):
        with mock.patch.object(
                adjustments, 'execute_command',
                return_value=Result(True, '', '')) as run:
            result = adjustments.set_animations(False)

        run.assert_called_once_with(
            f'gsettings set {ANIMATIONS_SCHEMA} enable-animations false')
        self.assertTrue(result.ok)

    def test_set_failure_is_returned(self):
        with mock.patch.object(
                adjustments, 'execute_command',
                return_value=Result(False, '', 'falhou')):
            result = adjustments.set_animations(True)
        self.assertFalse(result.ok)
        self.assertIn('falhou', result.error)


class PrivacyTest(unittest.TestCase):
    def test_get_reads_the_schema(self):
        with mock.patch.object(
                adjustments, 'execute_command',
                return_value=Result(True, 'false\n', '')) as run:
            self.assertIs(adjustments.get_privacy_cleanup(), False)

        run.assert_called_once_with(
            f'gsettings get {PRIVACY_SCHEMA} remove-old-trash-files')

    def test_set_enables_both_options_in_one_call(self):
        with mock.patch.object(
                adjustments, 'execute_command',
                return_value=Result(True, '', '')) as run:
            result = adjustments.set_privacy_cleanup(True)

        run.assert_called_once_with(
            f'gsettings set {PRIVACY_SCHEMA} remove-old-trash-files true && '
            f'gsettings set {PRIVACY_SCHEMA} remove-old-temp-files true')
        self.assertTrue(result.ok)

    def test_set_failure_is_returned(self):
        with mock.patch.object(
                adjustments, 'execute_command',
                return_value=Result(False, '', 'falhou')):
            result = adjustments.set_privacy_cleanup(False)
        self.assertFalse(result.ok)


if __name__ == '__main__':
    unittest.main()
