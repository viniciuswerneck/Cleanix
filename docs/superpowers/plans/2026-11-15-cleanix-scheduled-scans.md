# Scheduled Scans and Automatic Maintenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add scheduled/automatic scanning and maintenance features to Cleanix, allowing the app to periodically check the system without user interaction, with user-configurable intervals and safe defaults.

**Architecture:** Introduce a GLib timeout-based scheduler in `cleanix/main.py` that triggers `_start_scan()` at user-selected intervals. Add a new "Agendamento" page in `SettingsDialog` with interval selector (every 1h, 6h, 12h, 24h, desabilitado). When enabled, the first scan runs after a short delay. All scan results accumulate in memory; the UI reflects the most recent scan. Add `settings.scheduled_scan.enabled` and `settings.scheduled_scan.interval` to the persisted JSON config. No changes to scan logic or cleanup commands.

**Tech Stack:** Python 3.10+, GTK4/PyGObject, Cairo, `unittest`, GLib timeout. Existing `i18n.py` and `settings.py` extensions.

**Spec:** `docs/superpowers/specs/2026-11-15-cleanix-ux-i18n-design.md` (tasks 1–10 complete); this plan extends the same branch.

**Global Constraints:**
- No new runtime dependencies (only stdlib + already-used GTK4/PyGObject/Cairo).
- Scan frequency respects the existing `COMMAND_TIMEOUT = 600` seconds.
- User can disable the scheduler at any time; settings persist across runs.
- Interval selection limited to: Desabilitado, 1 hora, 6 horas, 12 horas, 24 horas.
- First scheduled scan delays 30 seconds after startup to let the UI settle.
- `_busy` guard prevents overlapping scans.

**Review Focus:**
1. **Scheduler does not overlap** — if a scan is already running, the next timeout is postponed until it finishes.
2. **Settings persist** — `scheduled_scan.enabled` and `interval` survive language switches and app restarts.
3. **Invalid interval defaults to disabled** — if the saved value is corrupted or out-of-range, the scheduler starts disabled.
4. **UI remains responsive** — the interval selector does not block the dialog; `_recording` guard applies.

---
### Task 1: Add scheduled_scan fields to Settings model

**Files:**
- Modify: `cleanix/settings.py` — add `scheduled_scan: dict` field with defaults `{"enabled": False, "interval": "disabled"}`.
- Modify: `cleanix/main.py` — import `settings` and read the new fields at startup.

**Interfaces:**
- Consumes: `settings.load_settings()` returning a `Settings` dict with `scheduled_scan` key.
- Produces: `Settings.scheduled_scan.enabled` (bool) and `Settings.scheduled_scan.interval` (str in `["disabled", "1h", "6h", "12h", "24h"]`).

- [ ] **Step 1: Write the failing test**

```python
def test_scheduled_scan_defaults(self):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.json"
        original = settings.Settings()
        settings.save_settings(original, path)
        loaded = settings.load_settings(path)
        self.assertFalse(loaded.scheduled_scan.enabled)
        self.assertEqual(loaded.scheduled_scan.interval, "disabled")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_settings.SaveSettingsTest.test_scheduled_scan_defaults -v`
Expected: FAIL (field does not exist yet).

- [ ] **Step 3: Implement** — add the nested dict field and defaults to `cleanix/settings.py` and update `cleanix/main.py` to read it.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_settings.SaveSettingsTest.test_scheduled_scan_defaults -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cleanix/settings.py cleanix/main.py tests/test_settings.py
git commit -q -m "feat(settings): add scheduled_scan fields"
```

### Task 2: Add interval selector UI in SettingsDialog

**Files:**
- Modify: `cleanix/dialogs.py` — `SettingsDialog.__init__()`: add a `Gtk.ComboBoxText` with items "Desabilitado", "1 hora", "6 horas", "12 horas", "24 horas"; pre-select the current interval; connect `notify::active` to a handler.

**Interfaces:**
- Consumes: `settings.Settings.scheduled_scan.interval`.
- Produces: `SettingsDialog` UI element that, when changed, updates `settings.Settings.scheduled_scan.interval` and persists via `settings.save_settings()`.

- [ ] **Step 1: Write the failing test** (add to `tests/test_dialogs.py`)

```python
def test_settings_has_scheduled_scan_combobox(self):
    i18n.set_language('pt_BR')
    #Dialog construction + check combobox items exist
```

- [ ] **Step 2: Run test to verify it fails** (no combobox yet).

- [ ] **Step 3: Implement** — add the `Gtk.ComboBoxText` to `SettingsDialog`, populate it, wire the signal to update settings and persist.

- [ ] **Step 4: Run test to verify it passes**.

- [ ] **Step 5: Commit**.

### Task 3: Wire the scheduler in CleanixWindow

**Files:**
- Modify: `cleanix/cleanixwindow.py` — add `_schedule_next_scan()` and `_run_scheduled_scan()` methods. `_run_scheduled_scan()` mirrors `_start_scan()` but reads from `settings.load_settings().scheduled_scan` and does not prompt for confirmation. Add `GLib.timeout_add()` to start the scheduler after the initial 30-second delay.

**Interfaces:**
- Consumes: `settings.Settings.scheduled_scan.enabled`, `interval`.
- Produces: `GLib.timeout_add` in seconds matching the chosen interval (3600, 21600, 43200, 86400). The timeout calls `_start_scan()` internally.

- [ ] **Step 1: Write the failing test** (add to `tests/test_cleanixwindow.py` or a new file)

```python
def test_scheduler_starts_after_startup(self):
    # Integration-ish: verify GLib.timeout_add is called with correct period
```

- [ ] **Step 2: Run test to verify it fails**.

- [ ] **Step 3: Implement** — add `_schedule_next_scan()`, adjust `_build_ui()` or `__init__()` to start the timeout, `_run_scheduled_scan()` that calls `_start_scan()` without confirmation.

- [ ] **Step 4: Run test to verify it passes**.

- [ ] **Step 5: Commit**.

### Task 4: Add i18n keys for scheduler UI

**Files:**
- Modify: `cleanix/locale/pt_BR.json`, `cleanix/locale/en.json`, `cleanix/locale/es.json` — add keys: `settings.scheduled.title`, `settings.scheduled.subtitle`, `settings.scheduled.interval.disabled`, `settings.scheduled.interval.one`, `settings.scheduled.interval.six`, `settings.scheduled.interval.twelve`, `settings.scheduled.interval.twenty_four`.

**Interfaces:**
- Consumes: none (catalog update).
- Produces: translatable strings in all three languages.

- [ ] **Step 1: Write the failing test** — catalog keys test (similar to `AstKeysTest`) will flag missing keys.

- [ ] **Step 2: Run test to verify it fails** (missing keys).

- [ ] **Step 3: Implement** — add the keys to all three JSON catalogs.

- [ ] **Step 4: Run test to verify it passes**.

- [ ] **Step 5: Commit**.

### Task 5: Wire SettingsDialog interval change to persist immediately

**Files:**
- Modify: `cleanix/dialogs.py` — `_on_toggle` or the combobox changed handler: when the user selects a new interval, immediately call `settings.save_settings()` with the updated `scheduled_scan` dict; keep `_recording` guard.

**Interfaces:**
- Consumes: updated `settings.Settings.scheduled_scan.interval`.
- Produces: persisted config file updated without closing/reopening Settings.

- [ ] **Step 1: Write the failing test** — verify `settings.save_settings` is called with the new interval.

- [ ] **Step 2: Run test to verify it fails**.

- [ ] **Step 3: Implement** — add the signal handler.

- [ ] **Step 4: Run test to verify it passes**.

- [ ] **Step 5: Commit**.

### Task 6: Ensure scheduler does not overlap running scans

**Files:**
- Modify: `cleanix/cleanixwindow.py` — `_run_scheduled_scan()` checks `self._busy` before starting; if busy, reschedules the timeout for 30 seconds after the current scan finishes (using a small GLib timeout cascade).

**Interfaces:**
- Consumes: `self._busy` flag from `_set_busy()`.
- Produces: no overlapping scans; next scheduled run starts after the busy flag clears.

- [ ] **Step 1: Write the failing test** — simulate a running scan and verify the scheduler waits.

- [ ] **Step 2: Run test to verify it fails**.

- [ ] **Step 3: Implement** — add the overlap guard.

- [ ] **Step 4: Run test to verify it passes**.

- [ ] **Step 5: Commit**.

### Task 7: Run full test suite and verify no regressions

**Files:**
- Run: `python3 -m unittest discover -s tests -v` across all modules.

**Interfaces:** none (verification only).

- [ ] **Step 1: Run tests**

- [ ] **Step 2: Verify 108 tests still pass** plus any new tests.

- [ ] **Step 3: Commit** if all green.

### Task 8: Screenshot verification in three languages

**Files:**
- Run: `python3 tools/screenshot.py --out /tmp/opencode/cleanix_sched_pt.png --language pt_BR`
- Run: `python3 tools/screenshot.py --out /tmp/opencode/cleanix_sched_en.png --language en`
- Run: `python3 tools/screenshot.py --out /tmp/opencode/cleanix_sched_es.png --language es`

**Interfaces:** visual confirmation (no code change).

- [ ] **Step 1: Run screenshots** with the scheduler enabled in each language.

- [ ] **Step 2: Confirm no UI breakage** — no crashed windows, no truncated text.

### Task 9: Update documentation

**Files:**
- Modify: `README.md` — add a "Agendamento e manutenção automática" section explaining the new feature.
- Modify: `implementation-status.md` — add the new capability to the features list.

**Interfaces:** documentation updates only.

- [ ] **Step 1: Write the sections**.

- [ ] **Step 2: Commit**.

### Task 10: Final verification and ledger

**Files:**
- Run all previous verification commands one final time.
- `/home/vinicius/.cache/opencode/npm/git-superpowers-0958a5557860/1794309740817/node_modules/superpowers/skills/executing-plans/scripts/task-done docs/superpowers/plans/2026-11-15-cleanix-ux-i18n.md 11 <last-base-commit>`.
- Record in the ledger.

**Interfaces:** ledger update.

- [ ] **Step 1: Run verification commands**.

- [ ] **Step 2: Record task-done**.

- [ ] **Step 3: Close the plan**.

---