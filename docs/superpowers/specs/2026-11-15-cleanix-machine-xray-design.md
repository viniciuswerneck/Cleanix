# Cleanix Machine X-Ray (Raio-X da Máquina) — Design

## Intent and why
Add a new **"Raio-X da máquina"** menu/entry in Cleanix so users can quickly understand their computer: BIOS/firmware information, detailed hardware, and all installed programs. The primary use is a **fast summary by topic** with the ability to **open each topic for details** (not a single raw dump), suitable for quick inspection and troubleshooting.

## Goals
- Provide a quick, readable summary by topic: **BIOS/Sistema**, **Hardware**, **Programas instalados**.
- Let the user expand/open each topic to see details on demand.
- Show installed programs separated by origin (**APT/dpkg**, **Snap**, **Flatpak**) with counts, search/filter, and scrollable lists.
- Collect as much information as possible without admin privileges; offer an explicit action to fetch **complete privileged details** (BIOS/hardware via tools like `dmidecode`/`lshw`) using the existing graphical admin flow (`pkexec`).
- Keep the UI responsive (background collection) and present errors/limitations clearly.
- Integrate with existing i18n (pt_BR/en/es), sidebar/navigation, and dialog/window patterns.

## Non-goals
- Real-time monitoring or benchmarking beyond basic inventory.
- Editing BIOS settings, installing/removing packages, or modifying hardware state.
- Export/share report generation (PDF/HTML/file) in this iteration.
- Guaranteeing exhaustive hardware detection on every system; show best-effort results and tool availability/limitations.
- Supporting every package manager beyond dpkg/snap/flatpak in this iteration.

## Anti-goals (would be a failure even if "working")
- Blocking the UI while collecting large inventories.
- Dumping thousands of packages/hardware lines into the view without structure or search.
- Requesting admin password automatically on open; privileged collection must be user-initiated.
- Misleading labels (e.g. claiming "completo" when collected without privileges or when tools are missing).

## Constraints
- Python 3 / GTK4 app; follow existing patterns (`cleanixwindow.py` sidebar/dialog openers, `dialogs.py` windows, `execution.execute_command`, `systeminfo` helpers, i18n catalogs, CSS).
- Admin actions must use `pkexec` via `execute_command(..., as_root=True)` and show friendly errors.
- `dmidecode`/`lshw`/`lspci`/`lsusb` may exist but privileged data often requires root; must degrade gracefully to unprivileged sources (`/sys/class/dmi/id`, `/proc/cpuinfo`, `lscpu`, `lsblk`, `lspci`, `lsusb` where possible).
- Program lists can be very large (thousands of dpkg packages); UI must virtualize/limit rendering reasonably (scrollable container, filter narrows results) and compute counts efficiently.
- Preserve existing layout/harness expectations where applicable; add i18n keys in all three locales.

## Approaches (considered)

### 1) Single dialog with expandable topic sections (chosen)
- A `Gtk.Window` dialog "Raio-X da máquina" with a summary header and three expandable sections (`Gtk.Expander`): **BIOS e sistema**, **Hardware**, **Programas instalados**.
- Summary shows key facts and counts; expanding a section reveals details (and triggers on-demand detail collection if needed). A "Detalhes completos" (🔒) action per relevant topic runs privileged collection for that topic.
- Programs details contain three sub-sections/tabs (APT, Snap, Flatpak) each with search entry and scrollable list.
- **Pros:** matches "resumo por tópicos e ir abrindo em detalhes" directly, fits existing dialog pattern, keeps context in one place, easy to load details lazily.
- **Cons:** needs careful scrolling/layout and list performance for large package sets.
- **Trade-off:** slightly denser dialog, but best UX for the stated goal.

### 2) Summary dialog opening a sub-dialog per topic
- **Pros:** focused views. **Cons:** context switching across windows, weaker overview. Rejected for this goal.

### 3) Replace main content area with a dedicated X-Ray page
- **Pros:** more space. **Cons:** larger navigation/state refactor (home is currently fixed; actions open dialogs). Rejected as unnecessary complexity.

**Decision:** Approach 1.

## Design

### Navigation / entry point
- Add sidebar item **"Raio-X"** (icon e.g. `computer-symbolic` or `find-location-symbolic`) in `CleanixWindow._sidebar` (main group or near Ajustes/Histórico) wired to `_open_xray()`.
- `_open_xray()` opens `dialogs.XRayDialog(self)` (non-blocking collection in threads).
- Add i18n keys: `sidebar.xray`, dialog titles/labels, topic names, states, buttons (pt_BR/en/es).

### Data collection (new module `cleanix/xray.py`, pure logic/helpers)
- **Unprivileged (default, fast):**
  - BIOS/sistema summary: read `/sys/class/dmi/id/{sys_vendor,product_name,product_version,bios_vendor,bios_version,bios_date,board_vendor,board_name}` when readable; kernel/arch via `platform`/`os.uname()`.
  - Hardware summary: CPU model/cores/threads (`lscpu` parse or `/proc/cpuinfo`), total RAM (`/proc/meminfo`), disks (`lsblk -Jb`/existing scan info), GPU names (`lspci` filtered VGA/3D/Display if available).
  - Programs: `dpkg-query -W -f='${Package}\t${Version}\t${Status}\n'` (filter installed), `snap list` (name/version), `flatpak list --app --columns=application,version` for the app list — run only if commands exist; collect counts and lists. **Flatpak:** list installed **apps** in the Flatpak section; include **runtime count** separately in the summary/totals (do not list runtimes as programs).
- **Privileged (on user request, per topic):**
  - BIOS completo: `dmidecode -t bios -t system -t baseboard -t chassis` (pkexec).
  - Hardware completo: `lshw -short` and/or `lshw` (pkexec) as detailed text; optionally supplement with `lspci -nn`, `lsusb` (can try unprivileged first). When privileged details are fetched successfully, they **replace** the unprivileged details in that section and are clearly labeled as complete/admin-sourced.
- Return structured results with `available`, `source` (unprivileged/privileged/tool), `summary` strings, `details` text/rows, and `error/limitation` notes. Never raise to UI; capture timeouts/missing tools.

### UI (dialogs)
- `XRayDialog(Gtk.Window)` with scrollable root:
  - Header: title "Raio-X da máquina" + brief subtitle, **Atualizar** button (re-collect unprivileged summary/counts).
  - **Resumo** card: key lines for BIOS, Hardware, Programas totals (APT/Snap/Flatpak).
  - **Expander: BIOS e sistema** — summary label; on first expand (or button) show unprivileged details; button **"Detalhes completos"** (admin) to fetch dmidecode; on success, privileged details **replace** unprivileged details in this section and are labeled as complete/admin-sourced.
  - **Expander: Hardware** — summary; categorized detail text/subsections (CPU, Memória, Discos, PCI/USB/GPU) from unprivileged sources; **"Detalhes completos"** for `lshw` (admin); on success, privileged details **replace** unprivileged details and are labeled as complete/admin-sourced.
  - **Expander: Programas instalados** (option A chosen) — summary totals (APT, Snap, Flatpak apps, and Flatpak runtimes count shown separately in summary); inside: a notebook/stack or three labeled sub-expanders for **APT (dpkg)**, **Snap**, **Flatpak** (apps list), each with: count, `Gtk.SearchEntry` filter, and scrollable list view (`Gtk.ListBox`/`Gtk.ColumnView` or simple labels in scrolled box with filtered subset rendering, e.g. show filtered results capped for performance with "mostrando N de M" hint). Lists populated on expand. Runtimes are not listed as programs.
- Background threads + `GLib.idle_add` for all collection; show "coletando…" states and disable relevant actions while running.

### Program list presentation (performance)
- Store full lists in memory per source; render only filtered/current view (e.g. limit displayed rows, update on search text change) to keep UI responsive with thousands of dpkg entries.
- Display package name and version (and origin implied by section).

### Error handling & permissions
- Missing tool/source: show "indisponível" with reason. Privileged fetch cancelled/fails: show friendly error (reuse `execution` messages) but keep unprivileged info.
- Mark privileged actions with lock indicator and clear text that senha may be requested.

### Testing
- Unit tests for `xray.py` parsers/collectors (parse dpkg-query lines, snap/flatpak output, dmi id file reading, lscpu/lspci summary extraction) using sample strings/fixtures.
- Keep `python3 -m unittest discover -s tests -v` green; verify UI manually/integration as needed (layout harness unchanged by dialog-only addition).

### Out of scope / future
- Export report to file, copy-all, hardware sensors/temperatures, driver/firmware update hints, package removal.

## Decisions resolved with partner
- **1A:** Flatpak — list installed **apps** in the programs list; show **runtimes only as a count** in summary/totals (not listed as programs).
- **2A:** Privileged "Detalhes completos" results **replace** unprivileged details in that section, clearly labeled as complete/admin-sourced.

## Calls I am making (defaults, unless corrected)
- Entry as a **sidebar menu item** opening a **dialog** (consistent with current app).
- Privileged data only on explicit user action (button with 🔒), never auto-prompt on open.
- "Todos os programas instalados" = union of installed **APT/dpkg + Snap + Flatpak apps** available on the system, shown **separately by origin** (A), with Flatpak runtimes counted in summary only.
- Best-effort unprivileged details shown immediately/cheaply; full details via `dmidecode`/`lshw` replace unprivileged details when requested and successful.
