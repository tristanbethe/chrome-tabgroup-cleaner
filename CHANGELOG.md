# Changelog

All notable changes to this project are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/), and this project aims to follow
[Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-06-02

First public release. 🎉

Fixes Chrome's **"Saved tab groups"** that keep duplicating on every restart
(session-manager bloat) and slow Chrome's startup — by safely cleaning Chrome's
internal `Sync Data/LevelDB` while Chrome is closed.

### Added
- **Surgical cleaner** (`clean_saved_tab_groups_v1.py`): de-duplicates saved tab
  groups to one per name (keeping the live/open one) **or** wipes them entirely,
  and removes orphaned tab records — the real source of the bloat.
- **Pure-Python LevelDB reader + writer** (`chrome_leveldb.py`): parses `.log` and
  `.ldb` files (snappy decompression, CRC32C log appends), no external deps.
- **One-click tools**:
  - `clean_and_launch_chrome` — close Chrome → wipe → relaunch (for session-manager users).
  - `clean_and_launch_keep_one` — same, but keeps one set per name (no session manager).
  - `watch_and_clean` — background watcher that cleans on every Chrome close.
  - `inspect_tab_groups_db_v2` — read-only diagnostic / bloat meter.
- **Cross-platform support** (`chrome_paths.py`): Windows, macOS and Linux paths,
  process detection and close/launch.
- **Prebuilt Windows executables** (no Python needed) + a plain-language guide
  (`docs/EXECUTABLES.md`) on which one to use.
- `build_exe.py` to package the tools with PyInstaller.

### Safety
- Always makes a full LevelDB backup before writing; Chrome must be closed.
- Dry-run by default in the manual cleaner; result is re-verified after writing.
- Only `saved_tab_group-*` keys are touched — bookmarks, reading list and
  preferences in the same shared database are left untouched.
- Fully reversible by restoring the automatic backup.

### Notes
- Not affiliated with or endorsed by Google. Use at your own risk.
- Tested on Chrome 148 / Windows 11. The storage format is internal to Chrome and
  may change in future versions.

[1.0.0]: https://github.com/tristanbethe/chrome-tabgroup-cleaner/releases/tag/v1.0.0
