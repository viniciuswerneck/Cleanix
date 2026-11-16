import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cleanix import xray
from cleanix.execution import Result


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


class PrivilegedCollectTest(unittest.TestCase):
    def test_single_call_parses_both_sections(self):
        output = (f"{xray.PRIV_BIOS_MARK}\nBIOS-LINE\n"
                  f"{xray.PRIV_HW_MARK}\nHW-LINE\n")
        with mock.patch.object(xray.shutil, 'which', return_value='/usr/bin/x'), \
                mock.patch.object(xray, 'execute_command',
                                  return_value=Result(True, output, '')) as run:
            res = xray.collect_privileged_all()
        self.assertTrue(res['ok'])
        self.assertEqual(res['bios']['details'], 'BIOS-LINE')
        self.assertEqual(res['hardware']['details'], 'HW-LINE')
        self.assertTrue(res['bios']['ok'])
        self.assertTrue(res['hardware']['ok'])
        self.assertEqual(run.call_count, 1)
        self.assertTrue(run.call_args.kwargs.get('as_root'))

    def test_cancelled_password_reports_error(self):
        with mock.patch.object(xray.shutil, 'which', return_value='/usr/bin/x'), \
                mock.patch.object(xray, 'execute_command',
                                  return_value=Result(False, '', 'Not authorized')):
            res = xray.collect_privileged_all()
        self.assertFalse(res['ok'])
        self.assertIn('Not authorized', res['error'])
        self.assertEqual(res['bios']['details'], '')
        self.assertEqual(res['hardware']['details'], '')


class ReportHtmlTest(unittest.TestCase):
    def _snapshot(self):
        return {
            'bios': {
                'summary': 'BIOS: ACME 1.2',
                'details': 'basic bios',
                'fields': {'product_name': 'Widget <Pro>'},
            },
            'hardware': {'summary': 'CPU: Test', 'details': 'basic hw'},
            'programs': {
                'apt': [('bash', '5.2'), ('<script>alert(1)</script>', '1.0')],
                'snap': [('firefox', '120')],
                'flatpak_apps': [('org.gimp.GIMP', '2.10')],
                'flatpak_runtimes': 3,
                'summary': 'APT: 2 | Snap: 1 | Flatpak: 1 apps',
            },
            'limitations': ['lspci indisponível'],
        }

    def test_report_contains_privileged_details_and_programs(self):
        html = xray.build_report_html(
            self._snapshot(),
            bios_details='DMIDECODE-BIOS-X',
            hw_details='LSHW-HW-Y',
            bios_source='detalhes completos (admin)',
            hw_source='detalhes completos (admin)',
        )
        self.assertIn('<!doctype html>', html)
        self.assertIn('DMIDECODE-BIOS-X', html)
        self.assertIn('LSHW-HW-Y', html)
        self.assertIn('firefox', html)
        self.assertIn('org.gimp.GIMP', html)
        self.assertIn('xray-search', html)
        self.assertIn('lspci indisponível', html)
        self.assertIn('detalhes completos (admin)', html)

    def test_report_escapes_program_names(self):
        html = xray.build_report_html(self._snapshot())
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', html)
        self.assertIn('Widget &lt;Pro&gt;', html)

    def test_report_shows_notice_when_privileged_fails(self):
        html = xray.build_report_html(
            self._snapshot(), priv_error='Not authorized')
        self.assertIn('Detalhes completos não incluídos', html)
        self.assertIn('Not authorized', html)
