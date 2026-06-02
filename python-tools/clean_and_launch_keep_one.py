"""
🚀 Clean & Launch Chrome — KEEP ONE SET variant
================================================

Same as clean_and_launch_chrome.py, but instead of wiping everything it KEEPS one
group per name (the newest = the live/open one) and removes only the duplicates
and orphaned tabs.

Use this when nothing automatically rebuilds your saved tab groups (i.e. you are
NOT relying on a session manager to recreate them) — so you keep your groups but
lose the duplicate bloat.

Double-click `clean_and_launch_keep_one.bat` (Windows) or run this script directly.

🔒 Always makes a backup of the LevelDB first (in python-tools/backups/).
"""

import sys

from clean_and_launch_chrome import clean_and_launch

if __name__ == "__main__":
    sys.exit(clean_and_launch(keep_per_title=1))
