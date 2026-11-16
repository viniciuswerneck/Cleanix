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
        text = ("bash\t5.2\tinstalled\t6000\n"
                "foo\t1.0\tconfig-files\t10\n")
        pkgs = xray.parse_dpkg_query(text)
        self.assertEqual(len(pkgs), 1)
        self.assertEqual(pkgs[0][:2], ('bash', '5.2'))
        self.assertTrue(pkgs[0][2])

    def test_parse_snap_list(self):
        text = "Name  Version  Rev\ncore  16-2    1\nfirefox  120  10\n"
        pkgs = xray.parse_snap_list(text)
        self.assertIn(('firefox', '120', ''), pkgs)
        self.assertNotIn(('Name', 'Version', ''), pkgs)

    def test_parse_flatpak_apps_and_runtimes(self):
        apps = xray.parse_flatpak_list(
            "org.gimp.GIMP\t2.10\t120 MB\n")
        self.assertEqual(apps, [('org.gimp.GIMP', '2.10', '120 MB')])
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



class RedactionTest(unittest.TestCase):
    def test_masks_dmidecode_identifiers(self):
        text = ("Serial Number: ABC123\n"
                "UUID: 1234-5678\n"
                "SKU Number: SKU-9\n"
                "Asset Tag: TAG-1\n"
                "  serial: LSHW-99\n"
                "Version: 1.0\n")
        out = xray.redact_sensitive(text)
        for secret in ('ABC123', '1234-5678', 'SKU-9', 'TAG-1', 'LSHW-99'):
            self.assertNotIn(secret, out)
        self.assertIn('[oculto]', out)
        self.assertIn('Version: 1.0', out)

    def test_masking_is_case_insensitive(self):
        out = xray.redact_sensitive("SERIAL NUMBER: zzz\n")
        self.assertNotIn('zzz', out)


class TranslatedDetailsTest(unittest.TestCase):
    def test_bios_details_follow_language(self):
        from cleanix import i18n
        i18n.set_language('en')
        try:
            text = xray._bios_details({
                'bios_vendor': 'ACME', 'bios_version': '1.0'})
        finally:
            i18n.set_language('pt_BR')
        self.assertIn('vendor', text.lower())
        self.assertIn('ACME', text)


class NetworkAndSystemTest(unittest.TestCase):
    def test_parse_ip_brief(self):
        text = ("lo               UNKNOWN        127.0.0.1/8 ::1/128\n"
                "enp3s0           UP             192.168.0.10/24 fe80::1/64\n"
                "wlan0            DOWN\n")
        ifaces = xray.parse_ip_brief(text)
        self.assertEqual([i['name'] for i in ifaces], ['lo', 'enp3s0', 'wlan0'])
        self.assertEqual(ifaces[1]['state'], 'UP')
        self.assertIn('192.168.0.10/24', ifaces[1]['addresses'])
        self.assertEqual(ifaces[2]['addresses'], [])

    def test_parse_ip_brief_ignores_empty_output(self):
        self.assertEqual(xray.parse_ip_brief(''), [])
        self.assertEqual(xray.parse_ip_brief('\n\n'), [])

    @mock.patch.object(xray, '_read_mac', return_value='aa:bb:cc:dd:ee:ff')
    @mock.patch.object(xray, '_cmd',
                       return_value='lo UNKNOWN 127.0.0.1/8\n'
                                    'enp3s0 UP 10.0.0.2/24\n')
    def test_collect_network_excludes_loopback(self, _cmd, _mac):
        net = xray.collect_network()
        self.assertEqual([i['name'] for i in net['interfaces']], ['enp3s0'])
        self.assertEqual(net['interfaces'][0]['mac'], 'aa:bb:cc:dd:ee:ff')
        self.assertIn('10.0.0.2/24', net['details'])

    def test_parse_uptime(self):
        self.assertEqual(xray.parse_uptime('90061.5 1000.0\n'), 90061)
        self.assertEqual(xray.parse_uptime(''), 0)
        self.assertEqual(xray.parse_uptime('lixo'), 0)

    def test_format_uptime(self):
        text = xray.format_uptime(90061)
        self.assertIn('1', text)
        self.assertTrue(text)

    def test_parse_apt_upgradable(self):
        text = ("Listing...\n"
                "foo/jammy 1.0 amd64 [upgradable from: 0.9]\n"
                "bar/jammy 2.0 amd64 [upgradable from: 1.0]\n")
        self.assertEqual(xray.parse_apt_upgradable(text), 2)
        self.assertEqual(xray.parse_apt_upgradable('Listing...\n'), 0)

    def test_secure_boot_state(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            self.assertEqual(xray.secure_boot_state(d), '')
            f = base / 'SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c'
            f.write_bytes(b'\x06\x00\x00\x00\x01')
            self.assertEqual(xray.secure_boot_state(d), 'enabled')
            f.write_bytes(b'\x06\x00\x00\x00\x00')
            self.assertEqual(xray.secure_boot_state(d), 'disabled')


class AlertsTest(unittest.TestCase):
    def test_build_alerts(self):
        disks = [
            {'mount_point': '/', 'pct_used': 95},
            {'mount_point': '/home', 'pct_used': 40},
        ]
        alerts = xray.build_alerts('09/25/2015', disks, 22, 0, 2026)
        levels = [a['level'] for a in alerts]
        self.assertEqual(levels.count('warn'), 2)
        self.assertEqual(levels.count('info'), 1)
        self.assertTrue(all(a.get('text') for a in alerts))

    def test_build_alerts_quiet_machine(self):
        disks = [{'mount_point': '/', 'pct_used': 30}]
        self.assertEqual(
            xray.build_alerts('01/01/2025', disks, 2, 0, 2026), [])

    def test_build_alerts_pending_updates(self):
        alerts = xray.build_alerts('', [], 0, 5, 2026)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['level'], 'info')

    def test_build_alerts_tolerates_bad_bios_date(self):
        self.assertEqual(xray.build_alerts('???', [], 0, 0, 2026), [])


class ReportHtmlV2Test(unittest.TestCase):
    def _snapshot(self):
        return {
            'bios': {'summary': 'BIOS: ACME', 'details': 'basic',
                     'fields': {}},
            'hardware': {'summary': 'CPU: Test', 'details': 'basic'},
            'programs': {'apt': [], 'snap': [], 'flatpak_apps': [],
                         'flatpak_runtimes': 0, 'summary': ''},
            'network': {
                'summary': '1 interface',
                'details': 'enp3s0 UP\n    IP: 10.0.0.2/24\n'
                           '    MAC: aa:bb:cc:dd:ee:ff',
                'interfaces': [{
                    'name': 'enp3s0', 'state': 'UP',
                    'addresses': ['10.0.0.2/24'],
                    'mac': 'aa:bb:cc:dd:ee:ff',
                }],
            },
            'system': {'summary': 'Uptime: 1 d', 'details': 'sistema',
                       'uptime': '1 d', 'updates': 3,
                       'secure_boot': 'enabled', 'tpm': True},
            'disks': [{
                'name': 'sda', 'type': 'disk',
                'size_total': 500107862016, 'size_used': 475102469000,
                'pct_used': 95, 'mount_point': '',
            }],
            'alerts': [{'level': 'warn',
                        'text': 'Partição / com 95% de uso'}],
            'limitations': [],
        }

    def test_report_contains_new_sections(self):
        html = xray.build_report_html(self._snapshot())
        for anchor in ('id="destaques"', 'id="rede"', 'id="sistema"',
                       'id="discos"'):
            self.assertIn(anchor, html)
        self.assertIn('enp3s0', html)
        self.assertIn('sda', html)
        self.assertIn('95%', html)

    def test_report_has_actions_and_version(self):
        from cleanix import version
        html = xray.build_report_html(self._snapshot())
        for anchor in ('id="xray-print"', 'id="xray-theme"', 'id="xray-top"'):
            self.assertIn(anchor, html)
        self.assertIn(version, html)

    def test_report_redacts_identifiers_by_default(self):
        details = 'Serial Number: SECRET-1\nUUID: SECRET-2\n'
        html = xray.build_report_html(
            self._snapshot(), bios_details=details)
        self.assertNotIn('SECRET-1', html)
        self.assertNotIn('SECRET-2', html)

    def test_report_can_keep_identifiers(self):
        details = 'Serial Number: SECRET-1\n'
        html = xray.build_report_html(
            self._snapshot(), bios_details=details, redact=False)
        self.assertIn('SECRET-1', html)

    def test_report_redacts_network_mac(self):
        html = xray.build_report_html(self._snapshot())
        self.assertNotIn('aa:bb:cc:dd:ee:ff', html)
        html = xray.build_report_html(self._snapshot(), redact=False)
        self.assertIn('aa:bb:cc:dd:ee:ff', html)
