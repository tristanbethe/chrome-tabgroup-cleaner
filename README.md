# Tab Group Cleaner 🧹

**Fix Chrome's endlessly duplicating "Saved tab groups" that pile up on every
restart and slow Chrome's startup to a crawl.**

If you use a session manager (like **Tab Session Manager**) and your Chrome
*Saved tab groups* bar keeps growing — the same group names doubling on every
restart until there are hundreds — this tool cleans it up, safely, and can keep
it clean automatically.

---

## The problem

Modern Chrome stores *Saved tab groups* in an internal **LevelDB** database
(`Sync Data/LevelDB`), even when sync is off. Some session managers recreate a
fresh set of saved groups on every startup **without removing the old ones**, so
the saved groups (and their tab records) accumulate without bound:

- The bar fills with duplicate group names (8 → 16 → 24 → …).
- Thousands of orphaned tab records pile up underneath, invisible in the UI.
- Chrome has to load and render all of it on startup → slower and slower launches.

### Why a Chrome extension can't fix this

A regular extension runs in a sandbox. It **cannot** read or delete *saved* tab
groups (there is no `chrome.savedTabGroups` API — `chrome.tabGroups` only sees the
*live* groups in open windows) and it **cannot** touch the profile's LevelDB on
disk. That blind spot is exactly why this problem has gone unfixed for so long.
So the fix has to be a small external tool that edits Chrome's LevelDB while
Chrome is closed — which is what this project is.

---

## What's in the box

| Tool | What it does |
|---|---|
| **`clean_and_launch_chrome.py`** + `.bat` | One click: close Chrome → clean up → relaunch. Your daily driver. |
| **`watch_and_clean.py`** + `.bat` | Background watcher: cleans automatically every time Chrome closes. Set & forget. |
| **`clean_saved_tab_groups_v1.py`** | The cleaner itself (preview/dry-run, de-dup, or full wipe). |
| **`inspect_tab_groups_db_v2.py`** | Read-only diagnostic: locates the store and measures the bloat. |
| **`chrome_leveldb.py`** | Dependency-free pure-Python LevelDB reader + writer (snappy + CRC32C). |
| **`chrome_paths.py`** | Cross-platform Chrome paths / process control (Windows, macOS, Linux). |

---

## Quick start

> Requires **Python 3.8+**. Optional: `pip install colorama psutil` (nicer colored
> output and faster process detection — both optional).

### Option A — one-click clean & launch (recommended)

1. Make sure your group names are intact (clean state) at least once.
2. Double-click **`python-tools/clean_and_launch.bat`** (Windows), or run:
   ```bash
   cd python-tools
   python clean_and_launch_chrome.py
   ```
   It closes Chrome, wipes the saved-tab-group bloat, and relaunches Chrome. Your
   session manager rebuilds exactly **one clean set** on startup.

### Option B — fully automatic (set & forget)

Run the watcher in the background; it cleans every time you quit Chrome:
```bash
cd python-tools
python watch_and_clean.py
```
On Windows, put a shortcut to `watch_and_clean.bat` in your Startup folder
(`shell:startup`) to run it at login.

### Option C — manual / careful

Edit the config at the top of `clean_saved_tab_groups_v1.py` and run it. It starts
in **`DRY_RUN = True`** (preview only). Set `DRY_RUN = False` to actually clean.

---

## Keep your group names vs. wipe everything

There's one switch — `KEEP_PER_TITLE`:

- **`0` (default): wipe all.** Best when a session manager recreates a fresh set on
  every startup. You end up with exactly **one clean set** after launch.
- **`1`: keep the newest set per name.** Best when *nothing* recreates your groups
  (so you don't want to lose them). Keeps the live/open group, removes the
  duplicates and orphaned tabs.

---

## Safety

- 🔒 **Always makes a full backup** of the LevelDB folder before writing
  (`python-tools/backups/LevelDB_precleanup_<timestamp>/`).
- ⛔ **Chrome must be fully closed** while writing (the tools check this).
- 🧪 **Dry-run by default** in the manual cleaner; the de-dup/wipe logic is verified
  by re-reading the database after writing.
- ↩️ **Fully reversible.** If anything looks off, close Chrome and copy the backup
  folder's contents back over `…/Default/Sync Data/LevelDB`.
- 🎯 **Surgical.** Only `saved_tab_group-*` keys are touched. Bookmarks sync,
  reading list and preferences in the same shared LevelDB are left untouched.

---

## How it works (for the curious)

1. Chrome's saved tab groups live in the sync DataTypeStore LevelDB at
   `…/Default/Sync Data/LevelDB`, under keys prefixed `saved_tab_group-dt-`
   (data: group + tab entities) and `saved_tab_group-md-` (sync metadata).
2. `chrome_leveldb.py` parses the `.log` (write-ahead log) and `.ldb` (SSTable)
   files — including snappy decompression — and merges them into the *live*
   records (tombstones removed) by keeping the highest sequence number per key.
3. The cleaner identifies duplicate groups (one entity per name, keeping the
   newest = the live/open one) and orphaned tabs, then **appends LevelDB deletion
   records** to the active log with correct framing and CRC32C. Chrome's own
   engine applies them on next launch — no risky in-place SSTable rewriting.

No external dependencies are required; everything is implemented in pure Python.

---

## Build standalone executables (optional)

So others can run it without installing Python:

```bash
pip install pyinstaller colorama psutil
cd python-tools
python build_exe.py
```

Produces `CleanAndLaunchChrome` and `WatchAndClean` in `python-tools/dist/`.

---

## Configuration

The important knobs are named variables at the top of each script (no CLI flags):

- `clean_saved_tab_groups_v1.py`: `DRY_RUN`, `WORK_ON_COPY`, `KEEP_PER_TITLE`, `PROFILE_NAME`
- `clean_and_launch_chrome.py`: `KEEP_PER_TITLE`, `FORCE_CLOSE_AFTER_SEC`, `LAUNCH_AFTER`
- `watch_and_clean.py`: `KEEP_PER_TITLE`, `POLL_SEC`, `SETTLE_SEC`
- `inspect_tab_groups_db_v2.py`: `LOCATE_NAMES` / `SIGNATURE_NAMES` (set to your own group names)

Using a non-default Chrome profile? Set `PROFILE_NAME` (e.g. `"Profile 1"`).

---

## Disclaimer

This tool edits Chrome's internal database. It is careful (backups, dry-run,
verification) and has been tested, but it is **not** affiliated with or endorsed by
Google. Use at your own risk, and keep the backups it makes. Always close Chrome
before running it.

## License

MIT — see [LICENSE](LICENSE).
