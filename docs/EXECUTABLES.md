# Tab Group Cleaner — which file does what?

These tools fix Chrome's **"Saved tab groups"** that keep duplicating on every
restart (and slowly make Chrome start slower). You don't need Python — just
double-click the right `.exe` for your situation.

## Read first

- The tools **close Chrome** to clean up, then reopen it. Save any unfinished work
  first (open tabs come back; unsaved form text may not).
- A **backup is made automatically** before every cleanup (in a `backups` folder
  next to the tool).
- Pick **one** of the tools below depending on your situation.

## Which one do I use?

### 1. `CleanAndLaunchChrome.exe` — “Wipe all + relaunch”
Use this if you use a **session manager** (like Tab Session Manager) that restores
your tab groups on startup. It closes Chrome, removes **all** saved tab groups, and
reopens Chrome — your session manager then rebuilds exactly **one clean set**.

→ Double-click whenever the bar gets cluttered.

### 2. `CleanAndLaunch_KeepOneSet.exe` — “Keep one set + relaunch”
Use this if you do **not** use a session manager that rebuilds your groups. It keeps
**one** copy of each group (your real, open one) and removes only the duplicates and
leftover tabs, then reopens Chrome — so you keep your groups but lose the bloat.

→ Double-click whenever the bar gets cluttered.

### 3. `WatchAndClean.exe` — “Automatic (set & forget)”
Runs quietly in the background. **Every time you close Chrome** it cleans up
automatically (wipe-all style). Put a shortcut in your Startup folder
(`shell:startup`) to run it at login. Stop it by closing its window.

## Safety

- A backup is saved before every cleanup, in a `backups` folder next to the tool.
- If anything looks wrong: close Chrome, open the newest backup folder, and copy its
  contents back into:
  `%LOCALAPPDATA%\Google\Chrome\User Data\Default\Sync Data\LevelDB`
- Not affiliated with Google. Use at your own risk.

## Notes

- Using a non-default Chrome profile (e.g. "Profile 1")? Use the Python scripts and
  set `PROFILE_NAME`, or open an issue on GitHub.
- Project & source code: https://github.com/tristanbethe/chrome-tabgroup-cleaner
