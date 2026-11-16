import tempfile
import unittest
from pathlib import Path

from cleanix import xray


class DmiReadTest(unittest.TestCase):
    def test_reads_available_fields(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / 'bios_vendor').write_text('ACME\n')
            (p / 'bios_version').write_text('1.2\n')
            (p / 'product_name').write_text('Widget\n')
            fields = xray.read_dmi_fields(d)
            self.assertEqual(fields.get('bios_vendor'), 'ACME')
            self.assertEqual(fields.get('bios_version'), '1.2')
            self.assertEqual(fields.get('product_name'), 'Widget')


class ProgramParseTest(unittest.TestCase):
    def test_parse_dpkg_query_installed_only(self):
        text = "bash\t5.2\tinstalled\nfoo\t1.0\tconfig-files\n"
        pkgs = xray.parse_dpkg_query(text)
        self.assertEqual(pkgs, [('bash', '5.2')])

    def test_parse_snap_list(self):
        text = "Name  Version  Rev\ncore  16-2    1\nfirefox  120  10\n"
        pkgs = xray.parse_snap_list(text)
        self.assertIn(('firefox', '120'), pkgs)
        self.assertNotIn(('Name', 'Version'), pkgs)

    def test_parse_flatpak_apps_and_runtimes(self):
        apps = xray.parse_flatpak_list("org.gimp.GIMP\t2.10\tstable\n")
        self.assertEqual(apps, [('org.gimp.GIMP', '2.10')])
        rt = xray.parse_flatpak_runtimes_count(
            "org.freedesktop.Platform\t23.08\norg.gnome.Platform\t45\n")
        self.assertEqual(rt, 2)
