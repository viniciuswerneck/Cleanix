import ast
import unittest
from pathlib import Path

from cleanix import i18n


class CatalogTest(unittest.TestCase):
    def tearDown(self):
        i18n.set_language('pt_BR')

    def test_three_catalogs_have_same_keys(self):
        base = i18n.catalog_keys('pt_BR')
        self.assertTrue(base)
        for code in i18n.LANGUAGES:
            self.assertEqual(i18n.catalog_keys(code), base, code)

    def test_invalid_language_falls_back_to_portuguese(self):
        i18n.set_language('en')
        self.assertFalse(i18n.set_language('fr'))
        self.assertEqual(i18n.get_language(), 'pt_BR')

    def test_missing_key_returns_key_and_logs(self):
        i18n.set_language('en')
        with self.assertLogs('cleanix.i18n', level='WARNING'):
            self.assertEqual(i18n.t('chave.inexistente'), 'chave.inexistente')


class PluralTest(unittest.TestCase):
    def tearDown(self):
        i18n.set_language('pt_BR')

    def test_one_and_other(self):
        i18n.set_language('pt_BR')
        self.assertEqual(i18n.tn('files.removed', 1), '1 arquivo removido')
        self.assertEqual(i18n.tn('files.removed', 3), '3 arquivos removidos')

    def test_english_plural(self):
        i18n.set_language('en')
        self.assertEqual(i18n.tn('files.removed', 1), '1 file removed')
        self.assertEqual(i18n.tn('files.removed', 2), '2 files removed')


class NumberTest(unittest.TestCase):
    def tearDown(self):
        i18n.set_language('pt_BR')

    def test_locale_separators(self):
        i18n.set_language('pt_BR')
        self.assertEqual(i18n.format_number(1234.5, 1), '1.234,5')
        i18n.set_language('en')
        self.assertEqual(i18n.format_number(1234.5, 1), '1,234.5')
        i18n.set_language('es')
        self.assertEqual(i18n.format_number(1234.5, 1), '1.234,5')

    def test_no_decimals(self):
        i18n.set_language('pt_BR')
        self.assertEqual(i18n.format_number(1234, 0), '1.234')


class DateTimeTest(unittest.TestCase):
    def tearDown(self):
        i18n.set_language('pt_BR')

    def test_date_order(self):
        i18n.set_language('en')
        self.assertEqual(i18n.format_datetime('2026-11-15T10:20:00'),
                         '11/15/2026 10:20')
        i18n.set_language('pt_BR')
        self.assertEqual(i18n.format_datetime('2026-11-15T10:20:00'),
                         '15/11/2026 10:20')
        i18n.set_language('es')
        self.assertEqual(i18n.format_datetime('2026-11-15T10:20:00'),
                         '15/11/2026 10:20')

    def test_invalid_date_returns_input(self):
        self.assertEqual(i18n.format_datetime('ontem'), 'ontem')


class DetectTest(unittest.TestCase):
    def test_env_prefixes(self):
        self.assertEqual(i18n.detect_language({'LANG': 'pt_BR.UTF-8'}), 'pt_BR')
        self.assertEqual(i18n.detect_language({'LANG': 'en_US.UTF-8'}), 'en')
        self.assertEqual(i18n.detect_language({'LANG': 'es_ES.UTF-8'}), 'es')
        self.assertEqual(i18n.detect_language({'LANG': 'fr_FR.UTF-8'}), 'pt_BR')

    def test_lc_all_wins(self):
        env = {'LANG': 'fr_FR.UTF-8', 'LC_ALL': 'en_US.UTF-8'}
        self.assertEqual(i18n.detect_language(env), 'en')


class AstKeysTest(unittest.TestCase):
    """Toda chave literal usada em t()/tn() precisa existir nos catálogos."""

    def _literal_keys(self):
        keys = set()
        root = Path(i18n.__file__).parent
        for path in root.glob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not isinstance(func, ast.Name) or func.id not in ('t', 'tn'):
                    continue
                if not node.args:
                    continue
                arg = node.args[0]
                if not isinstance(arg, ast.Constant):
                    continue
                if not isinstance(arg.value, str):
                    continue
                if func.id == 'tn':
                    keys.add(f'{arg.value}.one')
                    keys.add(f'{arg.value}.other')
                else:
                    keys.add(arg.value)
        return keys

    def test_literal_keys_exist(self):
        catalog = i18n.catalog_keys('pt_BR')
        for key in self._literal_keys():
            self.assertIn(key, catalog, key)


if __name__ == '__main__':
    unittest.main()
