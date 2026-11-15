import unittest

from cleanix import dialogs


class ExecuteCommandTest(unittest.TestCase):
    def test_success_returns_output(self):
        result = dialogs.execute_command('echo ola')
        self.assertTrue(result.ok)
        self.assertEqual(result.output, 'ola')
        self.assertEqual(result.error, '')

    def test_failure_captures_stderr(self):
        result = dialogs.execute_command('echo problema >&2; exit 2')
        self.assertFalse(result.ok)
        self.assertIn('problema', result.error)

    def test_failure_without_stderr_reports_code(self):
        result = dialogs.execute_command('exit 4')
        self.assertFalse(result.ok)
        self.assertIn('4', result.error)

    def test_missing_program_does_not_raise(self):
        result = dialogs.execute_command('cleanix-comando-inexistente-xyz')
        self.assertFalse(result.ok)
        self.assertTrue(result.error)

    def test_root_commands_use_pkexec_without_sudo(self):
        for action in dialogs.OPTIMIZER_ACTIONS:
            command = action['command']
            self.assertTrue(command)
            self.assertNotIn('sudo', command)
            self.assertNotIn('PATH=$PATH', command)


class ActionListsTest(unittest.TestCase):
    def test_optimizer_commands_need_root(self):
        for action in dialogs.OPTIMIZER_ACTIONS:
            self.assertTrue(action['as_root'])

    def test_optimizer_has_startup_apps_page(self):
        actions = dialogs.OptimizerDialog.actions
        labels = [action['label'] for action in actions]
        self.assertIn('Startup Apps', labels)
        startup = next(a for a in actions if a['label'] == 'Startup Apps')
        self.assertIsNotNone(startup.get('dialog'))
        self.assertNotIn('command', startup)

    def test_adjustments_never_need_root(self):
        for action in dialogs.ADJUSTMENT_ACTIONS:
            self.assertFalse(action['as_root'])
            self.assertNotIn('sudo', action['command'])

    def test_actions_have_all_fields(self):
        for action in (dialogs.OPTIMIZER_ACTIONS + dialogs.ADJUSTMENT_ACTIONS):
            for field in ('label', 'description', 'detail', 'command',
                          'as_root'):
                self.assertIn(field, action)


class StartupLayoutTest(unittest.TestCase):
    def test_four_columns(self):
        self.assertEqual(dialogs.STARTUP_COLUMNS, 4)

    def test_content_limit_fits_common_screen(self):
        self.assertEqual(dialogs.startup_content_limit(768), 340)

    def test_content_limit_shrinks_on_small_screen(self):
        self.assertEqual(dialogs.startup_content_limit(560), 240)

    def test_content_limit_never_goes_too_small(self):
        self.assertEqual(dialogs.startup_content_limit(400), 160)


if __name__ == '__main__':
    unittest.main()
