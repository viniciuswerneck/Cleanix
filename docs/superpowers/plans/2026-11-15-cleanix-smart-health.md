# Cleanix SMART Disk Health Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add on-demand SMART health checks for physical disks in the home screen, showing trust/reliability status (PASS/FAIL and key attributes) with clear guidance when `smartctl` is unavailable.

**Architecture:** Extend `cleanix/systeminfo.py` with helpers to detect physical disks for SMART checks and to parse `smartctl` text output into a structured summary. Expose a per-disk "Saúde (SMART)" action in the connected-disks UI (`cleanix/cleanixwindow.py`) that runs the check in a background thread, using `execute_command(..., as_root=True)`/`pkexec` for privileged access, and presents results/errors in a dialog (`cleanix/dialogs.py`). Keep space/usage display separate from SMART reliability.

**Tech Stack:** Python 3, GTK4/PyGObject, `smartctl` (smartmontools, optional external tool), existing `execute_command`/`pkexec`, JSON locale catalogs.

**Spec:** Approved design in conversation (2026-11-15): per physical disk SMART button in "Discos conectados"; on-demand `smartctl -H -A /dev/<disk>` with admin graphical prompt when needed; dialog shows overall PASS/FAIL/unavailable + key attributes (reallocated, pending, uncorrectable) and details; if `smartctl` missing, explain and guide to install `smartmontools` or use GNOME Disks, no auto-install and no incomplete alternative backend; keep partitions listed, i18n pt_BR/en/es, preserve current layout/tests.

## Global Constraints

- Do not auto-install packages. If `smartctl` is missing, show clear guidance (`sudo apt install smartmontools`) and suggest GNOME Disks (SMART Data & Self-Tests).
- Privileged SMART reads must use the existing graphical admin flow (`execute_command` with `as_root=True` / `pkexec`) and keep errors/logs visible to the user.
- SMART reliability is separate from space/usage "saúde"; do not label percent-used as SMART trust.
- Preserve existing home layout contract checked by `tools/check_layout.py` (card titles/order and expected labels/text expectations).
- Add/update i18n keys in `cleanix/locale/pt_BR.json`, `cleanix/locale/en.json`, `cleanix/locale/es.json` with parity.
- Do not add new Python dependencies.

## Review Focus

- **`smartctl` not installed:** clicking SMART shows helpful dialog (install/use Discos) and does not crash or show a raw traceback.
- **Permission/auth failure or pkexec dismissed:** result surfaces a friendly/clear error (existing friendly_error path) and UI remains usable.
- **Disk has no SMART or returns unknown:** dialog reports "indisponível/desconhecido" with available detail instead of claiming PASS/FAIL.
- **Non-disk/partition entries:** SMART button appears only for physical disks (`type == 'disk'`), not for partitions.
- **Locale/layout regression:** `tools/check_layout.py`, `tools/check_language.py` (if relevant) and `python3 -m unittest discover -s tests -v` stay green.

---

### Task 1: SMART helpers and parsing in `systeminfo`

**Files:**
- Modify: `cleanix/systeminfo.py`
- Test: `tests/test_systeminfo.py`

**Interfaces:**
- Produces: `systeminfo.smartctl_available() -> bool` (checks `shutil.which('smartctl')`).
- Produces: `systeminfo.physical_disks_for_smart(disks: list[dict] | None = None) -> list[dict]` returning entries with `type == 'disk'` and `size_total > 0`, excluding loop/zram/ram.
- Produces: `systeminfo.parse_smartctl(text: str) -> dict` with keys `overall` (`'passed'|'failed'|'unknown'`), `overall_text` (str), `attributes` (list of dicts with `name`, `value`, `raw`, `critical` bool for reallocated/pending/uncorrectable when detected), `notes` (list[str]).
- Consumes: existing `_scan_disks()` output shape.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_systeminfo.py`:
```python
import shutil
from unittest import mock
from cleanix import systeminfo as si

class SmartParseTest(unittest.TestCase):
    PASSED = """
=== START OF READ SMART DATA SECTION ===
SMART overall-health self-assessment test result: PASSED

ID# ATTRIBUTE_NAME          VALUE WORST THRESH TYPE      UPDATED  WHEN_FAILED RAW_VALUE
  5 Reallocated_Sector_Ct   100   100   010    Pre-fail  Always       -       0
197 Current_Pending_Sector  100   100   000    Old_age   Always       -       0
198 Offline_Uncorrectable   100   100   000    Old_age   Always       -       0
"""
    FAILED = "SMART overall-health self-assessment test result: FAILED!\n"
    UNKNOWN = "some output without health line\n"

    def test_passed_and_key_attributes(self):
        r = si.parse_smartctl(self.PASSED)
        self.assertEqual(r['overall'], 'passed')
        names = [a['name'] for a in r['attributes']]
        self.assertIn('Reallocated_Sector_Ct', names)

    def test_failed(self):
        r = si.parse_smartctl(self.FAILED)
        self.assertEqual(r['overall'], 'failed')

    def test_unknown(self):
        r = si.parse_smartctl(self.UNKNOWN)
        self.assertEqual(r['overall'], 'unknown')

class PhysicalDisksForSmartTest(unittest.TestCase):
    def test_filters_physical_disks(self):
        disks = [
            {'name':'sda','type':'disk','size_total':100},
            {'name':'sda1','type':'part','size_total':50},
            {'name':'zram0','type':'disk','size_total':10},
            {'name':'loop0','type':'disk','size_total':10},
        ]
        out = si.physical_disks_for_smart(disks)
        self.assertEqual([d['name'] for d in out], ['sda'])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_systeminfo.SmartParseTest tests.test_systeminfo.PhysicalDisksForSmartTest -v`
Expected: FAIL with missing `parse_smartctl` / `physical_disks_for_smart` (and/or `smartctl_available`).

- [ ] **Step 3: Implement helpers in `cleanix/systeminfo.py`**

Add `import shutil, re` as needed. Implement:
- `smartctl_available()` via `shutil.which('smartctl') is not None`.
- `physical_disks_for_smart(disks=None)` using `_scan_disks()` when None; keep only `type=='disk'`, `size_total>0`, name not starting with loop/zram/ram.
- `parse_smartctl(text)`:
  - overall: search `SMART overall-health self-assessment test result:\s*(PASSED|FAILED)` (case-insensitive) -> passed/failed else unknown; keep matched line as `overall_text`.
  - attributes: parse lines matching attribute rows `^\s*\d+\s+(\S+)\s+...` capturing name and RAW_VALUE (last column tokens joined); collect especially critical names in `{Reallocated_Sector_Ct, Current_Pending_Sector, Offline_Uncorrectable, Reported_Uncorrect, Reallocated_Event_Count}`; include them (and other parsed rows, capped reasonably e.g. 40) in `attributes` with `critical` flag.
  - `notes`: empty list by default.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_systeminfo.SmartParseTest tests.test_systeminfo.PhysicalDisksForSmartTest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cleanix/systeminfo.py tests/test_systeminfo.py
git commit -m "feat: add SMART helper parsing for disk health"
```

### Task 2: SMART dialog/action and UI button

**Files:**
- Modify: `cleanix/dialogs.py`
- Modify: `cleanix/cleanixwindow.py`

**Interfaces:**
- Consumes: `systeminfo.smartctl_available()`, `systeminfo.parse_smartctl`, `execute_command` from `.execution`.
- Produces (dialogs): `SmartHealthDialog(parent, disk_name, disk_model)` window with a "Verificar" action (or auto-runs on open) that runs in a thread: if smartctl missing -> show guidance message; else `execute_command(f'smartctl -H -A /dev/{disk_name}', as_root=True)` and render parsed summary + details.
- Produces (window): per physical disk row in `_refresh_disks_list` includes a small button (e.g. `disks.smart_check`) calling `dialogs.SmartHealthDialog(self, name, model).present()`; only for `is_disk` entries from physical disks.

- [ ] **Step 1: Add `SmartHealthDialog` in `cleanix/dialogs.py`**

Implement dialog similar to `MemoryDialog` style:
- Header with disk name/model, explanatory label (SMART = confiabilidade).
- Status/detail labels and a text view or wrapped labels for overall + key attributes list.
- On present/start: disable button, set status running; thread runs check:
  - if not `systeminfo.smartctl_available()`: return special result -> show i18n guidance with install command and GNOME Disks hint.
  - else run `execute_command(f"smartctl -H -A /dev/{disk_name}", as_root=True)` (disk_name validated to simple `[A-Za-z0-9_-]+`), parse via `systeminfo.parse_smartctl(result.output or result.error or '')` and include `result.error` on failure.
- On done (idle): show overall state text and attributes; on command failure still display parsed info if any plus error.
- Close button. Keep UI responsive (thread + GLib.idle_add).

- [ ] **Step 2: Add button in `cleanix/cleanixwindow.py`**

In `_refresh_disks_list`, when `is_disk` is True append a button `Gtk.Button(label=i18n.t('disks.smart_check'))` with class `status-btn` (or `btn-secondary`) before/after detail text, wired to open `dialogs.SmartHealthDialog(self, name, model)`. Ensure layout remains compact (button in row). Store no global ref required except dialog is modal to window.

- [ ] **Step 3: Manual/syntax check**

Run: `python3 -m py_compile cleanix/systeminfo.py cleanix/dialogs.py cleanix/cleanixwindow.py`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add cleanix/dialogs.py cleanix/cleanixwindow.py
git commit -m "feat: add on-demand SMART health check dialog for disks"
```

### Task 3: i18n and verification

**Files:**
- Modify: `cleanix/locale/pt_BR.json`
- Modify: `cleanix/locale/en.json`
- Modify: `cleanix/locale/es.json`

**Interfaces:**
- Consumes: new keys referenced by UI/dialog, e.g. `disks.smart_check`, `smart.title`, `smart.subtitle`, `smart.running`, `smart.not_installed.title`, `smart.not_installed.body`, `smart.overall.passed`, `smart.overall.failed`, `smart.overall.unknown`, `smart.attrs_title`, `smart.no_attrs`, `smart.error`, `smart.disk_label`.

- [ ] **Step 1: Add locale keys with parity**

Add keys to all three catalogs (pt_BR primary text, en/es translations). Include install hint `sudo apt install smartmontools` and mention "Discos (GNOME Disks) → Dados SMART e autotestes" in pt_BR (localized equivalents in en/es).

- [ ] **Step 2: Run full verification**

Run: `python3 -m unittest discover -s tests -v`
Expected: all tests pass (existing + new SMART tests).

Run: `timeout 60 python3 tools/check_layout.py`
Expected: `OK: tela inicial reorganizada`.

Run: `timeout 60 python3 tools/check_language.py` (if present in repo workflow)
Expected: OK / no failures.

- [ ] **Step 3: Commit**

```bash
git add cleanix/locale/pt_BR.json cleanix/locale/en.json cleanix/locale/es.json
git commit -m "feat: add SMART health i18n strings"
```
