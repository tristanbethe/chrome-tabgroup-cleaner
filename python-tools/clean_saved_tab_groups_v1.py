"""
🧹 Saved Tab Groups Cleaner v1
===============================

De-duplicates Chrome's "Saved tab groups" down to one group per name. Removes the
duplicate groups + their tabs + sync metadata from `Sync Data/LevelDB`, surgically,
via deletion records in the log (Chrome's own engine applies them). Other data
types (bookmarks sync, reading list, preferences) are left untouched.

Tool-agnostic: operates on Chrome's native store, no matter which session manager
(Tab Session Manager, or another) is causing the duplicates.

🔒 SAFETY — staged:
  • DRY_RUN=True    → only shows what WOULD be removed, writes NOTHING.
  • WORK_ON_COPY=True → operates on a copy under backups/, not your live profile.
  • Always makes a full backup of the LevelDB folder first.
  • Chrome MUST be fully closed.

Recommended order:
  1. DRY_RUN=True                       → preview
  2. DRY_RUN=False, WORK_ON_COPY=True   → run on a copy + verify
  3. (after checking) WORK_ON_COPY=False → apply to your real profile

Usage:  python clean_saved_tab_groups_v1.py
"""

import re
import sys
import shutil
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import chrome_paths as CP
from chrome_leveldb import (
    read_leveldb_dir, build_deletion_batch, append_batch_to_log,
    max_sequence, active_log_file, TYPE_VALUE,
)

# ============================================================
# ⚙️  CONFIG
# ============================================================
DRY_RUN = True                  # True = preview only, write nothing (set False to run)
WORK_ON_COPY = False            # True = operate on a copy instead of the live profile
# How many groups to keep per name:
#   0 = WIPE EVERYTHING (best when a tool like a session manager recreates a fresh
#       set on every startup — you end up with exactly 1 clean set after launch)
#   1 = keep the newest (live/open) set per name (best when nothing recreates them)
KEEP_PER_TITLE = 0
PROFILE_NAME = "Default"
REQUIRE_CHROME_CLOSED = True
AUTO_CONFIRM = False            # True = skip the y/n confirmation
# Test override: set a path to operate directly on that LevelDB folder (for tests)
OVERRIDE_LEVELDB_DIR = None
# ============================================================

PREFIX_DT = b"saved_tab_group-dt-"
PREFIX_MD = b"saved_tab_group-md-"

# URL schemes that reveal a record is a TAB (a group has no url)
URL_SCHEMES = [b"http://", b"https://", b"chrome://", b"chrome-extension://",
               b"file://", b"about:", b"data:", b"blob:", b"ftp://",
               b"edge://", b"view-source:"]

try:
    from colorama import init, Fore, Style
    init()
    GREEN, RED, YELLOW, CYAN = Fore.GREEN, Fore.RED, Fore.YELLOW, Fore.CYAN
    BOLD, RESET = Style.BRIGHT, Style.RESET_ALL
except ImportError:
    GREEN = RED = YELLOW = CYAN = BOLD = RESET = ""


def is_tab_value(value):
    """True if this dt record is a TAB (contains a url scheme)."""
    return any(s in value for s in URL_SCHEMES)


_GUID_ANY = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                       r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def extract_title(value):
    """Extract the group title from the value: first strip all guids, then split
    on punctuation and pick the longest token containing letters (= the name)."""
    txt = bytes(b if 32 <= b < 127 else 10 for b in value).decode("latin1")
    txt = _GUID_ANY.sub(" ", txt)                 # remove guids (also present in value)
    cand = []
    for tok in re.split(r"[^A-Za-z0-9 ]+", txt):  # split on punctuation
        tok = tok.strip()
        if not tok or not re.search(r"[A-Za-z]", tok):
            continue
        if re.fullmatch(r"[0-9a-fA-F]{4,}", tok):  # stray hex fragment
            continue
        cand.append(tok)
    if not cand:
        return "(empty)"
    return max(cand, key=len)


def guid_from_key(key):
    """The storage key (guid) after the dt/md prefix, as an ascii string."""
    if key.startswith(PREFIX_DT):
        return key[len(PREFIX_DT):].decode("latin1")
    if key.startswith(PREFIX_MD):
        return key[len(PREFIX_MD):].decode("latin1")
    return None


def plan_cleanup(records, keep_per_title=KEEP_PER_TITLE):
    """Decide which keys to delete. Pure function (no I/O).
    Returns a dict with the plan + reporting info."""
    live = [r for r in records if r.type == TYPE_VALUE]
    dt_live = [r for r in live if r.key.startswith(PREFIX_DT)]

    groups = [r for r in dt_live if not is_tab_value(r.value)]
    tabs = [r for r in dt_live if is_tab_value(r.value)]

    # groups per title
    by_title = defaultdict(list)
    for r in groups:
        by_title[extract_title(r.value)].append(r)

    keep_guids, drop_guids = set(), set()
    per_title = {}
    for title, recs in by_title.items():
        recs_sorted = sorted(recs, key=lambda r: r.seq, reverse=True)  # newest first
        keep = recs_sorted[:keep_per_title]
        drop = recs_sorted[keep_per_title:]
        for r in keep:
            keep_guids.add(guid_from_key(r.key))
        for r in drop:
            drop_guids.add(guid_from_key(r.key))
        per_title[title] = {
            "total": len(recs), "keep": len(keep), "drop": len(drop),
            "keep_info": [(guid_from_key(r.key)[:8], r.seq) for r in keep],
            "drop_info": [(guid_from_key(r.key)[:8], r.seq) for r in drop],
        }

    # Clean up TABS: keep only tabs that reference a KEPT group. Everything else is
    # dead weight: tabs of the removed duplicates AND orphaned tabs of groups that
    # are long gone (from earlier cleanups).
    keep_guid_bytes = [g.encode("latin1") for g in keep_guids]

    def tab_linked(v):
        return any(gb in v for gb in keep_guid_bytes)

    tabs_to_drop = [r for r in tabs if not tab_linked(r.value)]

    # all dt keys to delete (duplicate groups + unlinked/orphaned tabs)
    delete_dt = set()
    for r in groups:
        if guid_from_key(r.key) in drop_guids:
            delete_dt.add(r.key)
    for r in tabs_to_drop:
        delete_dt.add(r.key)

    # matching md keys (same guid suffix)
    delete_keys = set(delete_dt)
    for k in delete_dt:
        suffix = k[len(PREFIX_DT):]
        delete_keys.add(PREFIX_MD + suffix)

    wipe_all = (keep_per_title == 0)
    if wipe_all:
        # Thorough wipe: ALL live saved_tab_group data + metadata records.
        delete_keys = set(r.key for r in live
                          if r.key.startswith(PREFIX_DT) or r.key.startswith(PREFIX_MD))

    return {
        "n_groups_live": len(groups),
        "n_tabs_live": len(tabs),
        "by_title": per_title,
        "keep_guids": keep_guids,
        "drop_guids": drop_guids,
        "tabs_to_drop": len(tabs_to_drop),
        "tabs_kept": 0 if wipe_all else len(tabs) - len(tabs_to_drop),
        "wipe_all": wipe_all,
        "keep_per_title": keep_per_title,
        "delete_keys": sorted(delete_keys),
    }


def print_plan(plan):
    mode = "WIPE ALL (session manager rebuilds 1 set on startup)" if plan.get("wipe_all") \
        else f"de-duplicate to {plan.get('keep_per_title', KEEP_PER_TITLE)} per name"
    print(f"\n{CYAN}{'='*64}")
    print(f"🧹 Cleanup plan — {mode}")
    print(f"{'='*64}{RESET}\n")
    print(f"  Live groups: {plan['n_groups_live']}  |  live tabs: {plan['n_tabs_live']}\n")
    if plan.get("wipe_all"):
        print(f"  {YELLOW}🧨 All {plan['n_groups_live']} groups + {plan['n_tabs_live']} "
              f"tab records will be wiped. Your session manager creates a fresh set "
              f"on the next startup.{RESET}")
    else:
        print(f"  {BOLD}Per name (🟢 = kept guid+seq = the live/open group):{RESET}")
        for title, info in sorted(plan["by_title"].items(),
                                  key=lambda kv: kv[1]["drop"], reverse=True):
            mark = "🔴" if info["drop"] > 0 else "✅"
            keep_str = ", ".join(f"{g}…(seq {s})" for g, s in info["keep_info"])
            print(f"    {mark} {title[:24]:24} {info['total']:>3} groups  "
                  f"🟢 keep {keep_str}  🗑️ {info['drop']} removed")
    print(f"\n  📑 Tabs: {plan['tabs_kept']} kept (linked to a group), "
          f"{BOLD}{plan['tabs_to_drop']}{RESET} removed (duplicate + orphaned)")
    print(f"  🗑️  Total keys to delete (groups+tabs+metadata): "
          f"{BOLD}{len(plan['delete_keys'])}{RESET}")


def apply_cleanup(target_dir, delete_keys, all_records, chunk=2000):
    """Write deletion records for `delete_keys` to the active log, in chunks
    (safer for large cleanups; each chunk is its own WriteBatch)."""
    log = active_log_file(target_dir)
    if log is None:
        raise RuntimeError("No active .log file found in the LevelDB folder")
    seq = max_sequence(all_records) + 1
    total = 0
    for i in range(0, len(delete_keys), chunk):
        part = delete_keys[i:i + chunk]
        batch = build_deletion_batch(part, seq)
        total += append_batch_to_log(log, batch)
        seq += len(part)            # next batch gets a higher seq
    print(f"\n{GREEN}✍️  Wrote {len(delete_keys)} deletions to "
          f"{log.name} (+{total} bytes){RESET}")


def backup_dir(src):
    bdir = Path(__file__).parent / "backups"
    bdir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = bdir / f"LevelDB_precleanup_{ts}"
    shutil.copytree(src, dest)
    return dest


def verify(target_dir, keep_per_title):
    """Re-read and confirm: how many live groups per name remain?"""
    recs = read_leveldb_dir(target_dir)
    plan = plan_cleanup(recs, keep_per_title)
    dups = {t: i for t, i in plan["by_title"].items() if i["total"] > max(keep_per_title, 1)}
    print(f"\n{CYAN}🔎 Verification after cleanup:{RESET}")
    print(f"   Live groups now: {plan['n_groups_live']}  |  live tabs: {plan['n_tabs_live']}")
    if keep_per_title == 0:
        ok = plan["n_groups_live"] == 0
        print(f"   {GREEN}✅ Everything wiped — session manager builds 1 set on startup{RESET}"
              if ok else f"   {RED}❌ {plan['n_groups_live']} groups still present{RESET}")
        return ok
    if dups:
        print(f"   {RED}❌ Duplicates remain: {dups}{RESET}")
        return False
    print(f"   {GREEN}✅ No more duplicates — 1 group per name{RESET}")
    return True


def run_cleanup(keep_per_title=KEEP_PER_TITLE, dry_run=DRY_RUN, work_on_copy=WORK_ON_COPY,
                profile_name=PROFILE_NAME, require_closed=REQUIRE_CHROME_CLOSED,
                confirm=False, override_dir=OVERRIDE_LEVELDB_DIR):
    """Run the cleanup. Callable programmatically (wrapper/watcher).
    Returns a result dict; never calls sys.exit."""
    print(f"\n{CYAN}{'='*64}")
    print(f"🧹 Saved Tab Groups Cleaner v1")
    print(f"{'='*64}{RESET}")
    print(f"  Mode: {'DRY-RUN (preview)' if dry_run else 'EXECUTE'}  |  "
          f"target: {'COPY' if (work_on_copy and not dry_run) else 'LIVE PROFILE'}")

    if require_closed and CP.chrome_is_running():
        print(f"\n{RED}❌ Chrome is still running! Close Chrome completely.{RESET}")
        return {"ok": False, "reason": "chrome_running"}

    live = Path(override_dir) if override_dir else CP.leveldb_dir(profile_name)
    if not live.exists():
        print(f"{RED}❌ Sync Data/LevelDB not found: {live}{RESET}")
        return {"ok": False, "reason": "no_leveldb"}
    print(f"\n{GREEN}✅ LevelDB: {live}{RESET}")

    backup = backup_dir(live)
    print(f"{GREEN}🔒 Backup: {backup}{RESET}")

    target = backup_dir(live) if (work_on_copy and not dry_run) else live
    if work_on_copy and not dry_run:
        print(f"{YELLOW}📋 Working on copy: {target}{RESET}")

    records = read_leveldb_dir(target)
    plan = plan_cleanup(records, keep_per_title)
    print_plan(plan)

    if dry_run:
        print(f"\n{YELLOW}🅿️  DRY_RUN — nothing was written. "
              f"Set DRY_RUN=False to execute.{RESET}")
        return {"ok": True, "dry_run": True, "would_delete": len(plan["delete_keys"]),
                "backup": str(backup), "plan": plan}

    if confirm:
        ans = input(f"\n{CYAN}Delete {len(plan['delete_keys'])} keys from "
                    f"{'COPY' if work_on_copy else 'LIVE PROFILE'}? (y/n): {RESET}").strip().lower()
        if ans != "y":
            print(f"{RED}Cancelled.{RESET}")
            return {"ok": False, "reason": "cancelled"}

    apply_cleanup(target, plan["delete_keys"], records)
    ok = verify(target, keep_per_title)
    print(f"\n{GREEN}{'='*64}")
    print(f"✅ Done. Backup is in: {backup}")
    if work_on_copy:
        print(f"   (This was the COPY. Set WORK_ON_COPY=False for your real profile.)")
    print(f"{'='*64}{RESET}")
    return {"ok": ok, "deleted": len(plan["delete_keys"]), "backup": str(backup)}


def main():
    run_cleanup(confirm=not AUTO_CONFIRM)


if __name__ == "__main__":
    CP.enable_utf8_output()
    main()
