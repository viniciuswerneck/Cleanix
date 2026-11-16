import unittest

from cleanix import dialogs, i18n


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
            if 'command' not in action:
                continue
            command = action['command']
            self.assertTrue(command)
            self.assertNotIn('sudo', command)
            self.assertNotIn('PATH=$PATH', command)


class ActionListsTest(unittest.TestCase):
    def setUp(self):
        i18n.set_language('pt_BR')

    def tearDown(self):
        i18n.set_language('pt_BR')

    def test_optimizer_commands_need_root(self):
        for action in dialogs.OPTIMIZER_ACTIONS:
            if 'command' in action:
                self.assertTrue(action['as_root'])

    def test_optimizer_has_startup_apps_page(self):
        actions = dialogs.OptimizerDialog.actions
        startup = next(a for a in actions
                       if a['label_key'] == 'optimizer.startup.label')
        self.assertEqual(i18n.t(startup['label_key']),
                         'Aplicativos de inicialização')
        self.assertIsNotNone(startup.get('dialog'))
        self.assertNotIn('command', startup)

    def test_optimizer_has_separate_memory_page(self):
        actions = dialogs.OptimizerDialog.actions
        memory = next(a for a in actions
                      if a['label_key'] == 'optimizer.memory.label')
        self.assertEqual(i18n.t(memory['label_key']), 'Memória RAM')
        self.assertIsNotNone(memory.get('dialog'))
        self.assertNotIn('command', memory)
        self.assertNotIn('as_root', memory)

    def test_optimizer_labels_are_plain_language(self):
        self.assertEqual(i18n.t('optimizer.clean.label'),
                         'Limpar cache do APT')
        self.assertEqual(i18n.t('optimizer.journal.label'),
                         'Limpar logs antigos')
        self.assertEqual(i18n.t('optimizer.fstrim.label'), 'Otimizar SSD')
        self.assertEqual(i18n.t('optimizer.autoremove.title'),
                         'Pacotes não necessários (APT)')

    def test_actions_have_all_fields(self):
        for action in dialogs.OPTIMIZER_ACTIONS:
            self.assertIn('label_key', action)
            self.assertIn('description_key', action)
            if action.get('dialog') is not None:
                self.assertNotIn('command', action)
            else:
                for field in ('detail_key', 'command', 'as_root'):
                    self.assertIn(field, action)

    def test_action_keys_exist_in_every_catalog(self):
        actions = list(dialogs.OPTIMIZER_ACTIONS
                       + tuple(dialogs.OptimizerDialog.actions))
        keys = set()
        for action in actions:
            for field in ('label_key', 'description_key', 'detail_key'):
                if field in action:
                    keys.add(action[field])
        for code in i18n.LANGUAGES:
            catalog = i18n.catalog_keys(code)
            for key in keys:
                self.assertIn(key, catalog, f'{code}: {key}')


class HelpAboutTextTest(unittest.TestCase):
    def tearDown(self):
        i18n.set_language('pt_BR')

    def test_portuguese_has_safety_and_version(self):
        i18n.set_language('pt_BR')
        title, body = dialogs.help_about_text()
        self.assertEqual(title, 'Ajuda e Sobre')
        self.assertIn('Cleanix 1.0', body)
        self.assertIn('/tmp', body)

    def test_english(self):
        i18n.set_language('en')
        title, _ = dialogs.help_about_text()
        self.assertEqual(title, 'Help & About')


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
