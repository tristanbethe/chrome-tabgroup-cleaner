"""
📦 build_exe.py — bundle the tools into standalone executables
==============================================================

Packages the cleaner tools with PyInstaller so other people can run them without
installing Python. Produces one-file executables in ./dist.

Prerequisites (one-time):
    pip install pyinstaller colorama psutil

Then run:
    python build_exe.py

Output (in ./dist):
    • CleanAndLaunchChrome(.exe)  — close Chrome → wipe → relaunch
    • WatchAndClean(.exe)         — background watcher, cleans on every Chrome close

Works on Windows, macOS and Linux (the .exe suffix is Windows-only). PyInstaller
follows imports automatically, so chrome_paths/chrome_leveldb/clean_saved_tab_groups
are bundled in too.
"""

import sys
import shutil
import subprocess
from pathlib import Path

# ============================================================
# ⚙️  CONFIG — which scripts to build
# ============================================================
TARGETS = [
    {"script": "clean_and_launch_chrome.py", "name": "CleanAndLaunchChrome"},
    {"script": "watch_and_clean.py",         "name": "WatchAndClean"},
]
ONEFILE = True          # single self-contained executable
CONSOLE = True          # keep a console window so users see the result
# ============================================================

HERE = Path(__file__).parent


def have_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
        return True
    except ImportError:
        return False


def main():
    if not have_pyinstaller():
        print("❌ PyInstaller is not installed.")
        print("   Install the build dependencies first:")
        print("     pip install pyinstaller colorama psutil")
        return 1

    for t in TARGETS:
        script = HERE / t["script"]
        if not script.exists():
            print(f"⚠️  Skipping missing script: {script.name}")
            continue
        cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
               "--name", t["name"]]
        if ONEFILE:
            cmd.append("--onefile")
        cmd.append("--console" if CONSOLE else "--windowed")
        cmd.append(str(script))
        print(f"\n📦 Building {t['name']} from {t['script']} ...")
        subprocess.run(cmd, cwd=str(HERE), check=True)

    # tidy: PyInstaller leaves build/ and .spec files behind
    for junk in ["build"]:
        p = HERE / junk
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)
    for spec in HERE.glob("*.spec"):
        spec.unlink(missing_ok=True)

    print(f"\n✅ Done. Executables are in: {HERE / 'dist'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
