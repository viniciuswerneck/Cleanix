# Cleanix Machine X-Ray (Raio-X da Máquina) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Raio-X da máquina" feature that shows a quick summary by topic (BIOS/system, hardware, installed programs) with expandable on-demand details, including privileged BIOS/hardware details and installed programs separated by origin.

**Architecture:** Implement a pure-data module `cleanix/xray.py` to collect and parse system inventory (DMI/sysfs, cpu/mem/disk/pci/usb, dpkg/snap/flatpak, and privileged dmidecode/lshw via `execution.execute_command`). Add `XRayDialog` in `cleanix/dialogs.py` and a sidebar entry in `cleanix/cleanixwindow.py` to present summary + expandable sections with lazy/background loading and search-filtered program lists. Keep UI responsive and admin prompts user-initiated.

**Tech Stack:** Python 3, GTK4/PyGObject, standard library (`subprocess` via existing `execution`, `pathlib`, `re`, `json`/parsing), system tools when available (`dmidecode`, `lshw`, `lspci`, `lsusb`, `lscpu`, `dpkg-query`, `snap`, `flatpak`).

**Spec:** `docs/superpowers/specs/2026-11-15-cleanix-machine-xray-design.md`

## Global Constraints

- Privileged data only on explicit user action (buttons with 🔒); never auto-prompt on open. Use `execute_command(..., as_root=True)`/`pkexec`.
- Unprivileged best-effort collection must work when tools/files are missing; show limitations/errors, do not crash.
- Flatpak: list installed **apps**; show **runtimes only as count** in summary/totals (decision 1A).
- Privileged "Detalhes completos" results **replace** unprivileged details in that section and are clearly labeled complete/admin-sourced (decision 2A).
- Programs separated by origin (**APT/dpkg, Snap, Flatpak apps**) with counts, search/filter, and scrollable lists; handle thousands of entries without freezing UI (render filtered/capped view).
- Add i18n keys in `cleanix/locale/pt_BR.json`, `en.json`, `es.json` with parity. Preserve existing tests/harness behavior.
- No new Python dependencies.

## Review Focus

- **dmidecode/lshw missing or permission denied / pkexec cancelled:** UI shows friendly limitation/error and keeps unprivileged info usable (no traceback).
- **No snap/flatpak/dpkg or empty outputs:** sections show "indisponível"/empty states with counts 0, not crashes.
- **Very large dpkg list:** expanding/searching programs remains responsive (filtered/capped rendering), counts remain correct.
- **Flatpak runtimes not listed as programs:** app list contains only apps; runtime count appears in summary/totals only.
- **Privileged details replace (not duplicate ambiguously) unprivileged details** and are labeled as complete/admin-sourced.

---

### Task 1: X-Ray data collection and parsers (`xray.py`)

**Files:**
- Create: `cleanix/xray.py`
- Test: `tests/test_xray.py`

**Interfaces:**
- Produces: `xray.read_dmi_fields(base_path: str | Path = '/sys/class/dmi/id') -> dict[str, str]` reading known keys (`bios_vendor,bios_version,bios_date,sys_vendor,product_name,product_version,board_vendor,board_name,chassis_vendor`) when present/readable.
- Produces: `xray.parse_dpkg_query(text: str) -> list[tuple[str, str]]` returning installed packages as `(name, version)` from `dpkg-query -W -f='${Package}\t${Version}\t${db:Status-Status}\n'` or status-filtered input; include only installed.
- Produces: `xray.parse_snap_list(text: str) -> list[tuple[str, str]]` returning `(name, version)` skipping header.
- Produces: `xray.parse_flatpak_list(text: str) -> list[tuple[str, str]]` returning app `(id_or_name, version)` rows; `xray.parse_flatpak_runtimes_count(text: str) -> int` counting runtime rows from `flatpak list --runtime`.
- Produces: `xray.collect_unprivileged() -> dict` with keys: `bios` (summary str, details str, fields dict), `hardware` (summary str, details str), `programs` (dict with `apt`, `snap`, `flatpak_apps` lists of `(name,version)`, `flatpak_runtimes` int, and summary/count strings), `limitations` (list[str]).
- Produces: `xray.collect_privileged_bios() -> dict` and `xray.collect_privileged_hardware() -> dict` running dmidecode/lshw via `execute_command(..., as_root=True)` returning `{ok, details, source, error}`.
- Consumes: `execution.execute_command` for command-based collection.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_xray.py` with:
```python
import tempfile, unittest
from pathlib import Path
from cleanix import xray

class DmiReadTest(unittest.TestCase):
    def test_reads_available_fields(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p/'bios_vendor').write_text('ACME\n')
            (p/'bios_version').write_text('1.2\n')
            (p/'product_name').write_text('Widget\n')
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
        rt = xray.parse_flatpak_runtimes_count("org.freedesktop.Platform\t23.08\norg.gnome.Platform\t45\n")
        self.assertEqual(rt, 2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_xray -v`
Expected: FAIL with missing module/functions.

- [ ] **Step 3: Implement `cleanix/xray.py`**

Implement file-reading and parsing functions per interfaces (tolerant parsing, strip whitespace, skip headers/empty). Implement `collect_unprivileged()` using best-effort: read DMI, gather CPU (`lscpu` or `/proc/cpuinfo`), RAM (`/proc/meminfo` via systeminfo if convenient), disks summary (`lsblk -S/-d` or `lsblk -Jb`), GPU via `lspci` if present; run dpkg-query/snap/flatpak commands via `execute_command` when `shutil.which` finds them, capture limitations on missing tools/errors. Build human-readable `summary` and `details` strings (pt-neutral labels avoided in data? keep data neutral; UI translates labels — but summaries can be simple key:value text). Implement `collect_privileged_bios()`/`collect_privileged_hardware()` calling dmidecode/lshw with pkexec if tools exist else return error. No GTK imports.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_xray -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cleanix/xray.py tests/test_xray.py
git commit -m "feat: add machine x-ray data collection and parsers"
```

### Task 2: X-Ray dialog and sidebar integration

**Files:**
- Modify: `cleanix/dialogs.py`
- Modify: `cleanix/cleanixwindow.py`

**Interfaces:**
- Consumes: `xray.collect_unprivileged`, `xray.collect_privileged_bios`, `xray.collect_privileged_hardware`.
- Produces (dialogs): `XRayDialog(Gtk.Window)` as specified (summary, expanders BIOS/Hardware/Programs with APT/Snap/Flatpak sections, search+scrollable capped lists, Atualizar, Detalhes completos 🔒 replacing details with admin-sourced label on success, background collection).
- Produces (window): sidebar item `sidebar.xray` and `CleanixWindow._open_xray()` opening `dialogs.XRayDialog(self).present()`.

- [ ] **Step 1: Implement `XRayDialog` in `cleanix/dialogs.py`**

Add dialog with: scrollable content, header, summary labels, `Gtk.Expander` sections. BIOS/Hardware expanders show summary/details text labels and a privileged-details button; run privileged collection in thread on click and replace detail text on success with source label. Programs expander contains three sub-sections (APT, Snap, Flatpak apps) each with count, search entry, and scrollable list area; store full lists, render filtered results (e.g. cap displayed rows like 500 and show "mostrando N de M") updating on search change; populate lazily on expand/first load. Initial unprivileged collection runs in background on open/refresh. Disable busy actions while running. Keep memory of privileged state per section.

- [ ] **Step 2: Wire sidebar entry in `cleanix/cleanixwindow.py`**

Add `('xray', i18n.t('sidebar.xray'), 'computer-symbolic')` or similar icon to sidebar items and handler `_open_xray` opening `dialogs.XRayDialog(self)`. Ensure placement fits existing menu (e.g. in main group or near Ajustes).

- [ ] **Step 3: Syntax check**

Run: `python3 -m py_compile cleanix/xray.py cleanix/dialogs.py cleanix/cleanixwindow.py`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add cleanix/dialogs.py cleanix/cleanixwindow.py
git commit -m "feat: add X-Ray machine dialog and sidebar entry"
```

### Task 3: i18n, docs touch-up, and verification

**Files:**
- Modify: `cleanix/locale/pt_BR.json`
- Modify: `cleanix/locale/en.json`
- Modify: `cleanix/locale/es.json`
- Modify (optional if needed): `README.md`

**Interfaces:**
- Consumes: keys used by UI (`sidebar.xray`, `xray.title`, `xray.subtitle`, `xray.refresh`, `xray.summary`, `xray.bios`, `xray.hardware`, `xray.programs`, `xray.details_full`, `xray.collecting`, `xray.source_unprivileged`, `xray.source_privileged`, `xray.programs.apt`, `xray.programs.snap`, `xray.programs.flatpak`, `xray.programs.runtimes`, `xray.search`, `xray.showing`, `xray.empty`, `xray.unavailable`, etc.).

- [ ] **Step 1: Add locale keys with parity**

Add all X-Ray strings to pt_BR/en/es (include labels for BIOS fields summary, hardware groups, totals, "Detalhes completos", loading, unavailable, showing N of M).

- [ ] **Step 2: Run full verification**

Run: `python3 -m unittest discover -s tests -v`
Expected: all tests pass (including `tests.test_xray`).

Run: `timeout 60 python3 tools/check_layout.py`
Expected: OK (sidebar change must not break expected home layout checks; if harness asserts sidebar text set, update harness accordingly only if necessary and justified).

Run: `timeout 60 python3 tools/check_language.py`
Expected: OK.

- [ ] **Step 3: Commit**

```bash
git add cleanix/locale/pt_BR.json cleanix/locale/en.json cleanix/locale/es.json README.md
git commit -m "feat: add X-Ray i18n and docs"
```

(Include `README.md` in commit only if updated to mention X-Ray; otherwise omit it from this commit.)
