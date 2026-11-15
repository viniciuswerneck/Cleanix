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
    def test_optimizer_has_root_and_user_actions(self):
        flags = {action['as_root'] for action in dialogs.OPTIMIZER_ACTIONS}
        self.assertEqual(flags, {True, False})

    def test_adjustments_never_need_root(self):
        for action in dialogs.ADJUSTMENT_ACTIONS:
            self.assertFalse(action['as_root'])
            self.assertNotIn('sudo', action['command'])

    def test_actions_have_all_fields(self):
        for action in (dialogs.OPTIMIZER_ACTIONS + dialogs.ADJUSTMENT_ACTIONS):
            for field in ('label', 'description', 'detail', 'command',
                          'as_root'):
                self.assertIn(field, action)


if __name__ == '__main__':
    unittest.main()
