"""
🚀 Clean & Launch Chrome
=========================

One-click solution: close Chrome (if open) → clean up the saved-tab-group bloat
→ relaunch Chrome cleanly. Your session manager (Tab Session Manager, etc.) builds
one fresh set on startup, so you start every time with exactly one clean group row.

Double-click `clean_and_launch.bat` (Windows) or run this script directly.

🔒 Always makes a backup of the LevelDB first (in python-tools/backups/).
"""

import sys
import time

import chrome_paths as CP
from clean_saved_tab_groups_v1 import run_cleanup

# ============================================================
# ⚙️  CONFIG
# ============================================================
KEEP_PER_TITLE = 0          # 0 = wipe all (session manager rebuilds 1 set); 1 = keep 1 set
PROFILE_NAME = "Default"
CLOSE_CHROME_IF_RUNNING = True   # automatically close Chrome if it is running
# How long to wait for a graceful close before forcing.
# Chrome often ignores the graceful signal on Windows (multi-process + background
# apps), so waiting has little point. 0 = force immediately (fastest; your session
# manager restores your session anyway). Set higher to spare unsaved form data if
# Chrome does close gracefully for you.
FORCE_CLOSE_AFTER_SEC = 0
LAUNCH_AFTER = True              # relaunch Chrome after the cleanup
LOCK_SETTLE_SEC = 1.5            # brief wait so the DB lock is released after closing
# ============================================================

GREEN = RED = YELLOW = CYAN = RESET = ""
try:
    from colorama import init, Fore, Style
    init()
    GREEN, RED, YELLOW, CYAN, RESET = Fore.GREEN, Fore.RED, Fore.YELLOW, Fore.CYAN, Style.RESET_ALL
except ImportError:
    pass


def main():
    CP.enable_utf8_output()
    print(f"\n{CYAN}{'='*64}")
    print(f"🚀 Clean & Launch Chrome")
    print(f"{'='*64}{RESET}")

    # 1) Close Chrome if needed
    if CP.chrome_is_running():
        if not CLOSE_CHROME_IF_RUNNING:
            print(f"{RED}❌ Chrome is running. Close it or set CLOSE_CHROME_IF_RUNNING=True.{RESET}")
            return 1
        print(f"{YELLOW}🚪 Chrome is running — closing "
              f"(force after {FORCE_CLOSE_AFTER_SEC}s)...{RESET}")
        if not CP.close_chrome(force_after=FORCE_CLOSE_AFTER_SEC):
            print(f"{RED}❌ Could not close Chrome. Close it manually and try again.{RESET}")
            return 1
        print(f"{GREEN}✅ Chrome closed.{RESET}")
        time.sleep(LOCK_SETTLE_SEC)   # wait a moment for the DB lock to release

    # 2) Clean up
    result = run_cleanup(keep_per_title=KEEP_PER_TITLE, dry_run=False,
                         work_on_copy=False, profile_name=PROFILE_NAME,
                         require_closed=True, confirm=False)
    if not result.get("ok"):
        print(f"{RED}❌ Cleanup not performed ({result.get('reason', '?')}).{RESET}")
        return 1

    # 3) Relaunch Chrome
    if LAUNCH_AFTER:
        print(f"\n{CYAN}🚀 Relaunching Chrome...{RESET}")
        if CP.launch_chrome():
            print(f"{GREEN}✅ Chrome launched — you now have one clean group row.{RESET}")
        else:
            print(f"{YELLOW}⚠️ Could not launch Chrome automatically — start it yourself.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
