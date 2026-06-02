"""
📊 Chrome Saved Tab Groups Inspector v2
========================================

Read-only diagnostic that locates and measures Chrome's MODERN 'Saved Tab Groups'
storage. The old v1 looked for a 'Tab Groups' SQLite file that no longer exists in
Chrome 148 — saved tab groups now live in the sync data layer (a LevelDB under
'Sync Data/LevelDB'), even when Chrome sync is turned off.

What this script does:
  1. 🔍 Scans the whole Chrome profile (UTF-8 and UTF-16) for your known group
     names, skipping the large cache folders.
  2. 📊 Counts how often each name appears on disk = the BLOAT METER.
     Baseline (just cleaned) ~1x per name; after restarts this grows.
  3. 🗄️ Inspects any SQLite database found (tables, rows, duplicates).
  4. 🔒 Makes a backup of the store found (file or whole LevelDB folder).

⚠️  Chrome must be FULLY closed (otherwise the DB is locked + read errors).
🔒 This script WRITES NOTHING to Chrome — read-only + makes a backup.

Usage:  python inspect_tab_groups_db_v2.py
"""

import os
import sys
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import chrome_paths as CP

# ============================================================
# ⚙️  CONFIG — edit everything here (no CLI args needed)
# ============================================================
PROFILE_NAME = "Default"            # which Chrome profile (Default, Profile 1, ...)
REQUIRE_CHROME_CLOSED = True        # ❌ stop if Chrome is still running
AUTO_CONFIRM = False                # True = skip the y/n confirmation

# Distinctive names for the LOCATE phase. Replace these with YOUR OWN group names.
# NOTE: short/common names give false positives — they appear as substrings all
# over History/URLs. Prefer names that do NOT occur in normal browsing history.
LOCATE_NAMES = ["stocks", "graphs", "Badkamer", "Nasses", "socials"]

# 🎯 SIGNATURE: names that appear ~0x in browsing history but DO appear in a
# saved-tab-groups store. A file containing >=2 of these is almost certainly a
# real tab-group store (not History/Favicons noise).
SIGNATURE_NAMES = ["Nasses", "socials", "graphs"]

SEARCH_ENCODINGS = ["utf-8", "utf-16-le"]   # how names are encoded on disk

# Large/noisy folders we skip (cache, crash dumps, etc.)
SKIP_DIRS = {
    "Cache", "Code Cache", "GPUCache", "GrShaderCache", "ShaderCache",
    "Crashpad", "component_crx_cache", "Service Worker", "blob_storage",
    "Media Cache", "DawnCache", "DawnGraphiteCache", "DawnWebGPUCache",
    "Network", "extensions_crx_cache",
}
MAX_FILE_MB = 300                   # skip files larger than this during the raw scan
# ============================================================

CP.enable_utf8_output()

# 🎨 Console colors (optional via colorama)
try:
    from colorama import init, Fore, Style
    init()
    GREEN, RED, YELLOW, CYAN = Fore.GREEN, Fore.RED, Fore.YELLOW, Fore.CYAN
    BOLD, RESET = Style.BRIGHT, Style.RESET_ALL
except ImportError:
    GREEN = RED = YELLOW = CYAN = BOLD = RESET = ""


def find_profile():
    """📂 Find the Chrome profile folder for this OS."""
    p = CP.profile_dir(PROFILE_NAME)
    if not p.exists():
        print(f"{RED}❌ Profile not found: {p}{RESET}")
        return None
    return p


def iter_files(root):
    """🚶 Walk all files, skipping SKIP_DIRS and oversized files."""
    for dirpath, dirnames, filenames in os.walk(root):
        # filter in place so os.walk does not descend into SKIP_DIRS
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            fp = Path(dirpath) / fn
            try:
                if fp.stat().st_size > MAX_FILE_MB * 1024 * 1024:
                    continue
            except OSError:
                continue
            yield fp


def count_names_in_bytes(data, names):
    """🔢 Count how often each name occurs (across all SEARCH_ENCODINGS)."""
    counts = {}
    for name in names:
        total = 0
        for enc in SEARCH_ENCODINGS:
            try:
                total += data.count(name.encode(enc))
            except Exception:
                pass
        if total:
            counts[name] = total
    return counts


def is_sqlite(path):
    """🧪 SQLite header check."""
    try:
        with open(path, "rb") as f:
            return f.read(16).startswith(b"SQLite format 3")
    except Exception:
        return False


def locate_phase(profile):
    """🔍 Scan the profile for LOCATE_NAMES; return hit files with counts."""
    print(f"\n{CYAN}{'='*64}")
    print(f"🔍 PHASE 1 — Locate the storage (scan {profile.name})")
    print(f"{'='*64}{RESET}\n")

    hits = []          # list of (path, {name:count})
    scanned = 0
    for fp in iter_files(profile):
        scanned += 1
        try:
            with open(fp, "rb") as f:
                data = f.read()
        except (PermissionError, OSError):
            # probably locked → Chrome still open?
            continue
        c = count_names_in_bytes(data, LOCATE_NAMES)
        if c:
            hits.append((fp, c))

    print(f"  📁 {scanned} files scanned (cache folders skipped)\n")

    if not hits:
        print(f"{YELLOW}⚠️ None of your group names found as text on disk.{RESET}")
        print(f"{YELLOW}   Possibly: (a) Chrome was still open (locks), or{RESET}")
        print(f"{YELLOW}   (b) the data is compressed (snappy in LevelDB).{RESET}")
        return hits

    # 🎯 Rank by SIGNATURE score first (how many SIGNATURE_NAMES present), then by
    # total. This floats real tab-group stores to the top and sinks History noise.
    def sig_score(counts):
        return sum(1 for n in SIGNATURE_NAMES if counts.get(n, 0) > 0)

    hits.sort(key=lambda h: (sig_score(h[1]), sum(h[1].values())), reverse=True)
    print(f"{GREEN}✅ Names found in {len(hits)} file(s) "
          f"(⭐ = real tab-group store):{RESET}\n")
    for fp, c in hits:
        rel = fp.relative_to(profile)
        total = sum(c.values())
        kind = "SQLite" if is_sqlite(fp) else "raw/leveldb"
        star = "⭐" if sig_score(c) >= 2 else "  "
        print(f"  {star}{BOLD}{rel}{RESET}  [{kind}]")
        print(f"       total {total} hits: " +
              ", ".join(f"{n}={v}" for n, v in sorted(c.items())))
    return hits


def classify_store(rel_str):
    """🏷️ Classify what kind of store a path is, based on its location."""
    low = rel_str.lower()
    if "sync data\\leveldb" in low or "sync data/leveldb" in low:
        return "🌐 Chrome native saved tab groups (THE BAR)"
    if "indexeddb" in low:
        return "🧩 Extension IndexedDB (e.g. a session manager — the SOURCE)"
    if low.startswith("sessions"):
        return "💾 Chrome session restore (normal)"
    return "❔ Unknown store"


def bloat_meter(profile, hits):
    """📊 Bloat meter: group the REAL tab-group stores (signature >=2) per folder
    and count the distinctive names. Ignores History/Favicons noise."""
    print(f"\n{CYAN}{'='*64}")
    print(f"📊 PHASE 2 — Bloat meter (real tab-group stores only)")
    print(f"{'='*64}{RESET}\n")

    def sig_score(counts):
        return sum(1 for n in SIGNATURE_NAMES if counts.get(n, 0) > 0)

    real = [(fp, c) for fp, c in hits if sig_score(c) >= 2]
    if not real:
        print(f"{YELLOW}⚠️ No real tab-group store recognized "
              f"(no file with >=2 of {SIGNATURE_NAMES}).{RESET}")
        return None

    # Group per parent folder (a LevelDB/IndexedDB is a folder full of .ldb/.log)
    stores = {}                       # parent_dir -> bool(is_leveldb)
    for fp, _ in real:
        parent = fp.parent
        is_ldb = (parent / "CURRENT").exists() or any(
            p.suffix in (".ldb", ".log") for p in parent.glob("*"))
        key = parent if is_ldb else fp
        stores[key] = is_ldb

    sync_store = None                 # path we want to back up for cleanup
    for store_path, is_ldb in sorted(stores.items(), key=lambda kv: str(kv[0])):
        rel = store_path.relative_to(profile)
        label = classify_store(str(rel))
        targets = list(store_path.glob("*")) if is_ldb else [store_path]

        total = defaultdict(int)
        for t in targets:
            if not t.is_file():
                continue
            try:
                data = t.read_bytes()
            except OSError:
                continue
            # count only distinctive names (no short-name noise)
            for name, cnt in count_names_in_bytes(data, LOCATE_NAMES).items():
                total[name] += cnt

        grand = sum(total.values())
        print(f"  {label}")
        print(f"    {BOLD}{rel}{RESET}")
        print(f"    " + "  ".join(f"{n}={total.get(n,0)}" for n in LOCATE_NAMES)
              + f"   →  Σ {grand}")
        print()

        if "Sync Data" in str(rel):
            sync_store = store_path

    print(f"  {YELLOW}💡 'native' = what you see in the bar; the extension IndexedDB"
          f" is the source that keeps feeding it.{RESET}")
    print(f"  {YELLOW}   .log/.ldb counts include old writes too; the real LIVE count"
          f" needs LevelDB parsing (see the cleaner).{RESET}")
    # prefer backing up Chrome's native store (the one we will clean later)
    return sync_store or next(iter(stores))


def inspect_sqlite_hits(profile, hits):
    """🗄️ Inspect only SQLite hits that have a tab-group SIGNATURE.
    History/Favicons (substring noise) are skipped on purpose."""
    def sig_score(counts):
        return sum(1 for n in SIGNATURE_NAMES if counts.get(n, 0) > 0)

    sqlite_hits = [fp for fp, c in hits if is_sqlite(fp) and sig_score(c) >= 2]
    if not sqlite_hits:
        print(f"\n{CYAN}{'='*64}")
        print(f"🗄️  PHASE 3 — SQLite inspection")
        print(f"{'='*64}{RESET}")
        print(f"\n  ✅ No SQLite tab-group store found — the saved groups live in "
              f"LevelDB, not in a SQLite DB. (History/Favicons were substring noise "
              f"and were skipped.)")
        return
    print(f"\n{CYAN}{'='*64}")
    print(f"🗄️  PHASE 3 — SQLite inspection ({len(sqlite_hits)} database(s))")
    print(f"{'='*64}{RESET}")
    for db in sqlite_hits:
        print(f"\n{BOLD}📂 {db.relative_to(profile)}{RESET}")
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cur.fetchall()]
            for t in tables:
                cur.execute(f"SELECT COUNT(*) FROM '{t}'")
                n = cur.fetchone()[0]
                print(f"   • table {t:30} {n} rows")
            conn.close()
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                print(f"   {RED}❌ LOCKED — Chrome still open{RESET}")
            else:
                print(f"   {RED}❌ {e}{RESET}")
        except Exception as e:
            print(f"   {RED}❌ {e}{RESET}")


def backup_store(store):
    """🔒 Back up the store found (file or whole folder)."""
    if not store:
        return
    backup_dir = Path(__file__).parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        dest = backup_dir / f"{store.name.replace(' ', '_')}_{ts}"
        if store.is_dir():
            shutil.copytree(store, dest)
        else:
            shutil.copy2(store, dest)
        print(f"\n{GREEN}🔒 Backup made: {dest}{RESET}")
    except Exception as e:
        print(f"\n{RED}❌ Backup failed: {e}{RESET}")


def main():
    print(f"\n{CYAN}{'='*64}")
    print(f"📊 Chrome Saved Tab Groups Inspector v2")
    print(f"{'='*64}{RESET}")

    if REQUIRE_CHROME_CLOSED and CP.chrome_is_running():
        print(f"\n{RED}❌ Chrome is still running! Close Chrome COMPLETELY.{RESET}")
        if not AUTO_CONFIRM:
            sys.exit(1)
        print(f"{YELLOW}   (AUTO_CONFIRM on — continuing anyway, expect read errors){RESET}")

    if not AUTO_CONFIRM:
        ans = input(f"\n{CYAN}Is Chrome fully closed? (y/n): {RESET}").strip().lower()
        if ans != "y":
            print(f"{RED}❌ Close Chrome first.{RESET}")
            sys.exit(1)

    profile = find_profile()
    if not profile:
        sys.exit(1)
    print(f"\n{GREEN}✅ Profile: {profile}{RESET}")

    hits = locate_phase(profile)
    store = bloat_meter(profile, hits)
    inspect_sqlite_hits(profile, hits)
    backup_store(store)

    print(f"\n{GREEN}{'='*64}")
    print(f"✅ Done! The bloat meter shows WHERE and HOW MUCH the duplicates are.")
    print(f"{'='*64}{RESET}")


if __name__ == "__main__":
    main()
