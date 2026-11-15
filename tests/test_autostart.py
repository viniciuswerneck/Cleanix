import tempfile
import unittest
from pathlib import Path

from cleanix import autostart


SYSTEM_ENTRY = """\
[Desktop Entry]
Type=Application
Name=Backup Automático
Comment=Faz backup todo dia
Exec=/usr/bin/backup --daily
Hidden=false
"""

ANOTHER_ENTRY = """\
[Desktop Entry]
Type=Application
Name=Sync
Exec=/usr/bin/sync-tool
X-GNOME-Autostart-enabled=false
"""


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class ParseDesktopFileTest(unittest.TestCase):
    def test_reads_desktop_entry_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(Path(tmp) / "backup.desktop", SYSTEM_ENTRY)
            values = autostart.parse_desktop_file(path)
        self.assertEqual(values["Name"], "Backup Automático")
        self.assertEqual(values["Exec"], "/usr/bin/backup --daily")

    def test_ignores_other_sections_and_comments(self):
        text = (
            "# comentário\n"
            "[Desktop Entry]\n"
            "Name=Teste\n"
            "\n"
            "[Desktop Action novo]\n"
            "Name=Outro\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = write(Path(tmp) / "t.desktop", text)
            values = autostart.parse_desktop_file(path)
        self.assertEqual(values, {"Name": "Teste"})

    def test_prefers_portuguese_name(self):
        text = "[Desktop Entry]\nName=Backup\nName[pt_BR]=Cópia\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = write(Path(tmp) / "t.desktop", text)
            values = autostart.parse_desktop_file(path)
        self.assertEqual(autostart.display_name(values, path), "Cópia")


class ListEntriesTest(unittest.TestCase):
    def test_merges_system_and_user_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            system = root / "system"
            home = root / "home"
            write(system / "backup.desktop", SYSTEM_ENTRY)
            write(home / ".config" / "autostart" / "sync.desktop",
                  ANOTHER_ENTRY)
            entries = autostart.list_entries(home, system_dirs=(system,))
        names = sorted(entry.name for entry in entries)
        self.assertEqual(names, ["Backup Automático", "Sync"])

    def test_user_file_overrides_system_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            system = root / "system"
            home = root / "home"
            write(system / "app.desktop", SYSTEM_ENTRY)
            write(home / ".config" / "autostart" / "app.desktop",
                  SYSTEM_ENTRY.replace("Hidden=false", "Hidden=true"))
            entries = autostart.list_entries(home, system_dirs=(system,))
            self.assertEqual(len(entries), 1)
            self.assertTrue(entries[0].hidden)
            self.assertTrue(entries[0].user_file)

    def test_ignores_non_desktop_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            system = root / "system"
            write(system / "leia-me.txt", "nada")
            entries = autostart.list_entries(root / "home", system_dirs=(system,))
        self.assertEqual(entries, [])

    def test_x_gnome_autostart_enabled_false_means_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            system = root / "system"
            write(system / "sync.desktop", ANOTHER_ENTRY)
            entries = autostart.list_entries(root / "home", system_dirs=(system,))
        self.assertTrue(entries[0].hidden)


class SetEnabledTest(unittest.TestCase):
    def test_disable_system_entry_creates_user_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            system = root / "system"
            home = root / "home"
            write(system / "backup.desktop", SYSTEM_ENTRY)
            entry = autostart.list_entries(home, system_dirs=(system,))[0]
            autostart.set_enabled(entry, False, home)

            override = home / ".config" / "autostart" / "backup.desktop"
            self.assertTrue(override.exists())
            entries = autostart.list_entries(home, system_dirs=(system,))
            self.assertEqual(len(entries), 1)
            self.assertTrue(entries[0].hidden)

    def test_enable_system_entry_removes_user_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            system = root / "system"
            home = root / "home"
            write(system / "backup.desktop", SYSTEM_ENTRY)
            write(home / ".config" / "autostart" / "backup.desktop",
                  SYSTEM_ENTRY.replace("Hidden=false", "Hidden=true"))

            entry = autostart.list_entries(home, system_dirs=(system,))[0]
            autostart.set_enabled(entry, True, home)

            entries = autostart.list_entries(home, system_dirs=(system,))
            self.assertEqual(len(entries), 1)
            self.assertFalse(entries[0].hidden)

    def test_enable_user_entry_keeps_exec_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            path = write(home / ".config" / "autostart" / "sync.desktop",
                         ANOTHER_ENTRY)
            entry = autostart.list_entries(home, system_dirs=())[0]
            autostart.set_enabled(entry, True, home)

            values = autostart.parse_desktop_file(path)
            self.assertEqual(values["Exec"], "/usr/bin/sync-tool")
            self.assertEqual(values["Hidden"], "false")


if __name__ == "__main__":
    unittest.main()
