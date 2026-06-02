"""
👁️ Watch & Clean — auto cleanup when Chrome closes
===================================================

A small background watcher: every time Chrome fully closes, it cleans up the
saved-tab-group bloat. So the next time you open Chrome, your session manager
rebuilds exactly one clean set — set and forget.

How it works: it polls whether Chrome is running. On the running → closed
transition it waits a moment (for the DB lock to release) and then runs the
cleanup once. It never touches the DB while Chrome is open.

Run in the background:
  • Windows: double-click `watch_and_clean.bat` (or put it in your Startup folder)
  • Stop it with Ctrl+C in the console.

🔒 Each cleanup makes a backup first (in python-tools/backups/).
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
POLL_SEC = 5                # how often to check whether Chrome is running
SETTLE_SEC = 3              # wait after Chrome closes before cleaning (lock release)
CLEAN_ON_START_IF_CLOSED = False   # also clean once at startup if Chrome is already closed
# ============================================================

GREEN = RED = YELLOW = CYAN = RESET = ""
try:
    from colorama import init, Fore, Style
    init()
    GREEN, RED, YELLOW, CYAN, RESET = Fore.GREEN, Fore.RED, Fore.YELLOW, Fore.CYAN, Style.RESET_ALL
except ImportError:
    pass


def clean_now(reason):
    print(f"\n{CYAN}🧹 Cleaning ({reason})...{RESET}")
    try:
        result = run_cleanup(keep_per_title=KEEP_PER_TITLE, dry_run=False,
                             work_on_copy=False, profile_name=PROFILE_NAME,
                             require_closed=True, confirm=False)
        if result.get("ok"):
            print(f"{GREEN}✅ Cleaned ({result.get('deleted', 0)} keys removed).{RESET}")
        else:
            print(f"{YELLOW}⏭️  Skipped ({result.get('reason', '?')}).{RESET}")
    except Exception as e:
        print(f"{RED}❌ Cleanup error: {e}{RESET}")


def main():
    CP.enable_utf8_output()
    print(f"\n{CYAN}{'='*64}")
    print(f"👁️  Watch & Clean — auto cleanup when Chrome closes")
    print(f"{'='*64}{RESET}")
    print(f"  Profile: {PROFILE_NAME}  |  mode: "
          f"{'wipe all' if KEEP_PER_TITLE == 0 else f'keep {KEEP_PER_TITLE}/name'}  |  "
          f"poll: {POLL_SEC}s")
    print(f"  {YELLOW}Running. Press Ctrl+C to stop.{RESET}\n")

    was_running = CP.chrome_is_running()
    print(f"  Chrome is currently {'running' if was_running else 'closed'}.")
    if not was_running and CLEAN_ON_START_IF_CLOSED:
        clean_now("Chrome already closed at startup")

    try:
        while True:
            time.sleep(POLL_SEC)
            now = CP.chrome_is_running()
            if was_running and not now:
                # Chrome just closed — wait for the lock to release, then clean
                time.sleep(SETTLE_SEC)
                if not CP.chrome_is_running():
                    clean_now("Chrome closed")
            was_running = now
    except KeyboardInterrupt:
        print(f"\n{CYAN}👋 Watcher stopped.{RESET}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
