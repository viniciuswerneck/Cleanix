# Linux CCleaner-Style Program - Design Plan

## Intent and Why
Creating a CCleaner-like utility for Linux that helps users clean system junk, optimize performance, and adjust system parameters safely. Many Linux users want the convenience of Windows' CCleaner but need a tool that respects Linux file system hierarchy and system safety.

## Goals
- [x] Clean system trash and temporary files
- [x] Clean browser caches, thumbnail caches, and user temp directories
- [x] Provide Ubuntu-specific parameter adjustments
- [x] Offer system optimization/refinement options
- [x] Ensure safety - never break user system
- [x] Provide sensible defaults and suggestions
- [x] Work on Ubuntu/Debian-based systems
- [x] Feature fluid, modern and intuitive interface with graphics/charts for visualization

## Non-Goals
- Do not target other Linux distributions primarily (though may work)
- Do not modify system-critical configuration
- Do not remove user data intentionally
- Do not provide registry editing (Linux doesn't have registry)

## Anti-Goals
- Do not auto-delete important user files
- Do not modify system services without explicit user confirmation
- Do not run dangerous commands without validation
- Do not claim to fix all performance issues

## Constraints
- Must be safe - "não estragar nada" (don't break anything)
- Should work on modern Ubuntu versions
- Should have GUI interface for accessibility
- Should provide preview before deletion
- Must respect user consent for all changes

## Approaches Considered

### Approach 1: Command-Line Tool Only
- Pros: Lightweight, scriptable, no dependency on GUI libraries
- Cons: Less accessible to average users, harder to discover features
- Decision: Rejected - user wants user-friendly experience like CCleaner

### Approach 2: GUI Application with Python/GTK
- Pros: Native look on Ubuntu, easy to use, can use built-in tools
- Cons: Requires Python and GTK dependencies
- Decision: Considered as primary approach

### Approach 3: Hybrid - CLI with optional GUI
- Pros: Flexible, can be used both ways
- Cons: More complex to maintain
- Decision: Selected as the best approach

### Approach 4: Bash Script with Zenity Dialogs
- Pros: Simple, no major dependencies, works out-of-the-box
- Cons: Limited functionality, basic UI
- Decision: Considered for minimal viable version

## Selected Approach: Python3 + GTK4 Application
- Uses Python (likely already installed on Ubuntu)
- GTK4 for modern native-looking interface
- leverages existing Linux tools (bleachbit, apt, etc.)
- Can safely preview changes before applying
- Easy to extend with additional features

## Design Overview

### Main Window Sections

The interface features a modern, fluid design with GTK4 and incorporates charts/graphs for visualization:

1. **Cleaner Tab**
   - System Trash cleanup
   - Package cache (apt autoclean)
   - Thumbnail cache
   - Documentation cache
   - User cache directories (~/tmp, /tmp)
   - Browser caches (Chrome, Firefox)
   - **Storage chart**: Visual progress bar with space freed summary

2. **Optimizer Tab**
   - System parameter adjustments
   - Startup application management
   - Service optimization suggestions
   - File system optimization (fstrim)
   - **System health chart**: Real-time metrics of cleanup impact

3. **Adjustments Tab**
   - Ubuntu-specific settings
   - Desktop experience tweaks
   - Privacy settings
   - Performance tweaks

4. **Graphics/Charts Section** (integrated throughout)
   - Disk usage pie chart: before/after cleanup comparison
   - Memory optimization graph: real-time performance tracking
   - Temp file categories donut chart: visual breakdown by type
   - Real-time progress bars with ETA: progress during operations
   - Before/after comparison charts: side-by-side space recovered visualization
   - System health dashboard: summary metrics with sparkline trends

### Safety Features
- **Preview mode**: Show what will be cleaned before doing it
- **Undo support**: Keep records of changes for reversal
- **User confirmation**: Major changes require explicit approval
- **Backup**: Config backups before modifications
- **Dry-run mode**: Simulate changes without applying
- **Visual feedback**: Real-time charts showing cleanup progress and space recovered
- **Safe mode**: All operations have confirmation dialogs before execution

### Ubuntu-Specific Adjustments Suggestions

1. **APT Auto-clean**: Regular `apt autoremove && apt clean`
2. **Journal Vacuum**: Clean old system logs (`journalctl --vacuum-time=7d`)
3. **Thumbnail Cache**: Clear `~/.cache/thumbnails`
4. **AppIndicator Cache**: Clear session caches
5. **Font Cache**: Update font information (`fc-cache -fv`)
6. **Find recent large files**: Identify space hogs
7. **Startup Apps**: Manage startup applications
8. **Timezone & locale cleanup**

### Technical Implementation Plan

#### Phase 1: Foundation
- [ ] Project structure setup
- [ ] Python package configuration
- [ ] GTK4 window setup
- [ ] Basic UI layout

#### Phase 2: Cleaning Functionality
- [ ] Trash detection and cleanup
- [ ] Package cache cleanup
- [ ] User cache management (~/tmp, /tmp)
- [ ] Thumbnail cache cleanup
- [ ] Browser cache cleanup (Chrome, Firefox)
- [ ] **Temporary files scanner** with category detection
- [ ] Preview system with space savings estimation
- [ ] **Charts generation** showing file types and sizes

#### Phase 3: Optimization Features
- [ ] APT auto-clean integration
- [ ] Journal vacuum integration
- [ ] Systemd service management
- [ ] Startup application editor

#### Phase 4: Adjustments & Tweaks
- [ ] Ubuntu settings panel
- [ ] Desktop experience options
- [ ] Privacy controls
- [ ] Performance suggestions

#### Phase 5: Safety & UX
- [ ] Confirmation dialogs
- [ ] Undo/redo system
- [ ] Log of all actions
- [ ] Help/documentation

### Dependencies
- Python 3.12+
- GTK4 (pygobject)
- **Charting libraries**: matplotlib or plotly for graphics
- System tools: bleachbit, apt, journalctl, etc.

### Installation
- PPA or direct install via pip/apt
- Optional: system integration for startup

### User Flow
1. Launch application - welcome screen with system overview chart
2. Scan system for junk/files - progress chart shows scanning phases
3. Present findings with checkboxes and category donut chart
4. "Preview" mode shows detailed view with pie chart of space to be freed
5. User confirms actions - real-time progress bar with ETA chart
6. Apply changes with progress feedback - before/after comparison charts
7. Report results with summary graphics showing total freed space

### Code Organization (without actual code)
```
cleanix/
├── main.py              # Application entry point
├── cleaner.py           # Cleaning operations
├── optimizer.py         # System optimization
├── adjustments.py       # Ubuntu tweaks
├── ui.py               # GTK interface
├── safety.py           # Safety checks and confirmations
└── utils.py            # Helper functions
```

### Risk Mitigation
- All operations have dry-run mode first
- Critical systems protected from accidental modification
- User must confirm before system-wide changes
- Operations logged for audit/reversal
- Falls back gracefully on errors

### Testing Considerations
- Test on clean Ubuntu install
- Test on Ubuntu with accumulated junk
- Test safety: verify no important files deleted
- Test edge cases: full trash, no cache, etc.

### Future Enhancements
- Docker container cleanup
- Flatpak cache management
- Snap package cleanup
- Dual-boot system detection
- Cloud storage leak detection