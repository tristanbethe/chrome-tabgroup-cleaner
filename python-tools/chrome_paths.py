"""
🌐 chrome_paths.py — cross-platform Chrome helpers
==================================================

One place for everything that differs per OS: profile paths, whether Chrome is
running, closing Chrome and (re)launching it. Used by the cleaner, the
"Clean & Launch" wrapper and the close-watcher.

Works on Windows, macOS and Linux. Uses psutil if available, otherwise falls
back to OS commands (tasklist/pgrep/taskkill/osascript/pkill).
"""

import os
import sys
import time
import shutil
import platform
import subprocess
from pathlib import Path

IS_WIN = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"

try:
    import psutil
    HAVE_PSUTIL = True
except ImportError:
    HAVE_PSUTIL = False


# ------------------------------------------------------------------
# 📂 Profile and LevelDB paths
# ------------------------------------------------------------------
def chrome_user_data_dir():
    """Chrome's 'User Data' folder for the current OS."""
    home = Path.home()
    if IS_WIN:
        base = os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local"))
        return Path(base) / "Google" / "Chrome" / "User Data"
    if IS_MAC:
        return home / "Library" / "Application Support" / "Google" / "Chrome"
    # Linux (and variants)
    for cand in ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]:
        p = home / ".config" / cand
        if p.exists():
            return p
    return home / ".config" / "google-chrome"


def profile_dir(profile_name="Default"):
    return chrome_user_data_dir() / profile_name


def leveldb_dir(profile_name="Default"):
    """The Sync Data/LevelDB folder that holds the saved tab groups."""
    return profile_dir(profile_name) / "Sync Data" / "LevelDB"


# ------------------------------------------------------------------
# 🔎 Is Chrome running?
# ------------------------------------------------------------------
def _process_names():
    if IS_WIN:
        return ("chrome.exe",)
    if IS_MAC:
        return ("Google Chrome", "Chromium")
    return ("chrome", "google-chrome", "chromium", "chromium-browser")


def chrome_is_running():
    """True if a Chrome (main) process is running."""
    names = [n.lower() for n in _process_names()]
    if HAVE_PSUTIL:
        for p in psutil.process_iter(["name"]):
            try:
                nm = (p.info["name"] or "").lower()
            except Exception:
                continue
            if any(nm == n or nm.startswith(n) for n in names):
                return True
        return False
    # Fallback via OS command
    try:
        if IS_WIN:
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/NH"],
                                 capture_output=True, text=True, timeout=15)
            return "chrome.exe" in out.stdout.lower()
        else:
            for n in _process_names():
                r = subprocess.run(["pgrep", "-x", n], capture_output=True, timeout=15)
                if r.returncode == 0:
                    return True
            return False
    except Exception:
        return False


# ------------------------------------------------------------------
# 🚪 Close Chrome (graceful → force if needed)
# ------------------------------------------------------------------
def _graceful_close():
    try:
        if IS_WIN:
            subprocess.run(["taskkill", "/IM", "chrome.exe"], capture_output=True, timeout=15)
        elif IS_MAC:
            subprocess.run(["osascript", "-e", 'quit app "Google Chrome"'],
                           capture_output=True, timeout=15)
        else:
            subprocess.run(["pkill", "-TERM", "-x", "chrome"], capture_output=True, timeout=15)
            subprocess.run(["pkill", "-TERM", "chrome"], capture_output=True, timeout=15)
    except Exception:
        pass


def _force_close():
    try:
        if IS_WIN:
            subprocess.run(["taskkill", "/IM", "chrome.exe", "/F", "/T"],
                           capture_output=True, timeout=15)
        elif IS_MAC:
            subprocess.run(["pkill", "-9", "-x", "Google Chrome"], capture_output=True, timeout=15)
        else:
            subprocess.run(["pkill", "-9", "-x", "chrome"], capture_output=True, timeout=15)
            subprocess.run(["pkill", "-9", "chrome"], capture_output=True, timeout=15)
    except Exception:
        pass


def close_chrome(force_after=0, poll=0.5, hard_timeout=20):
    """Close Chrome. force_after=0 → force immediately (Chrome often ignores the
    graceful signal on Windows anyway). >0 → try graceful first, then force.
    Returns True if Chrome is closed."""
    if not chrome_is_running():
        return True
    if force_after > 0:
        _graceful_close()

    waited = 0.0
    forced = False
    while chrome_is_running() and waited < hard_timeout:
        if waited >= force_after and not forced:
            forced = True
            _force_close()
        time.sleep(poll)
        waited += poll
    return not chrome_is_running()


# ------------------------------------------------------------------
# 🚀 Launch Chrome
# ------------------------------------------------------------------
def find_chrome_executable():
    """Find the Chrome launch command for this OS."""
    if IS_WIN:
        cands = []
        for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if base:
                cands.append(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe")
        for c in cands:
            if c.exists():
                return [str(c)]
        return None
    if IS_MAC:
        return ["open", "-a", "Google Chrome"]
    for exe in ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]:
        if shutil.which(exe):
            return [exe]
    return None


def launch_chrome():
    """Launch Chrome (detached). Returns True on success."""
    cmd = find_chrome_executable()
    if not cmd:
        return False
    try:
        if IS_WIN:
            subprocess.Popen(cmd, creationflags=0x00000008)  # DETACHED_PROCESS
        else:
            subprocess.Popen(cmd, start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def enable_utf8_output():
    """Force UTF-8 stdout/stderr (emoji-safe when piped/redirected on Windows)."""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
