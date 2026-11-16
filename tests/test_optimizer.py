import unittest

from cleanix import optimizer


APT_EMPTY_PT = '''NOTA: Esta é apenas uma simulação!
      apt-get precisa de privilégios de root para execução real.
Lendo listas de pacotes...
Construindo árvore de dependências...
Lendo informação de estado...
0 pacotes atualizados, 0 pacotes novos instalados, 0 a serem removidos e 11 não atualizados.
'''

APT_REMOVE = '''NOTE: This is only a simulation!
The following packages will be REMOVED:
  linux-image-6.8.0-40-generic linux-modules-6.8.0-40-generic
0 upgraded, 0 newly installed, 2 to remove and 0 not upgraded.
Remv linux-image-6.8.0-40-generic [6.8.0-40.40]
Remv linux-modules-6.8.0-40-generic [6.8.0-40.40]
After this operation, 350 MB disk space will be freed.
'''

SNAP_LIST = '''Name                       Version                         Rev    Tracking         Publisher                      Notes
audacity                   3.7.9                           1239   latest/stable    snapcrafters*                  -
brave                      1.99.56                         708    latest/stable    brave**                        disabled
code                       c4453f8e                        278    latest/stable    vscode**                       disabled,classic
core18                     20261023                        3267   latest/stable    canonical**                    base
'''


class AptAutoremoveParseTest(unittest.TestCase):
    def test_empty(self):
        data = optimizer.parse_apt_autoremove(APT_EMPTY_PT)
        self.assertTrue(data['empty'])
        self.assertEqual(data['items'], [])

    def test_with_removals(self):
        data = optimizer.parse_apt_autoremove(APT_REMOVE)
        self.assertFalse(data['empty'])
        self.assertIn('linux-image-6.8.0-40-generic', data['items'])
        self.assertIn('350', data.get('freed_text', ''))


class SnapDisabledParseTest(unittest.TestCase):
    def test_parses_disabled_only(self):
        items = optimizer.parse_snap_disabled(SNAP_LIST)
        names = [i['name'] for i in items]
        self.assertEqual(names, ['brave', 'code'])
        self.assertEqual(items[0]['rev'], '708')
        self.assertIn('disabled', items[1]['notes'])

    def test_ignores_header_and_active(self):
        items = optimizer.parse_snap_disabled(SNAP_LIST)
        self.assertFalse(any(i['name'] == 'audacity' for i in items))
        self.assertFalse(any(i['name'] == 'Name' for i in items))


class FlatpakUnusedParseTest(unittest.TestCase):
    def test_empty_pt(self):
        data = optimizer.parse_flatpak_unused('Nada não usado para desinstalar\n')
        self.assertTrue(data['empty'])
        self.assertEqual(data['items'], [])

    def test_empty_en(self):
        data = optimizer.parse_flatpak_unused('Nothing unused to uninstall.\n')
        self.assertTrue(data['empty'])

    def test_with_items(self):
        text = ('Unused runtimes:\n'
                ' org.gnome.Platform.Locale  45\n'
                ' org.freedesktop.Platform  23.08\n')
        data = optimizer.parse_flatpak_unused(text)
        self.assertFalse(data['empty'])
        self.assertTrue(len(data['items']) >= 1)


if __name__ == '__main__':
    unittest.main()
