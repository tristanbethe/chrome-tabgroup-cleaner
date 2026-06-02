# Tab Group Cleaner Project

## 🎯 Het probleem

Tristan gebruikt **Tab Session Manager (TSM)** in Chrome om sessies te bewaren en herstellen.
Bij elke restart (of handmatige restore) dupliceert TSM zijn tab groups in het Chrome tab groups menu.

Het probleem groeit elke restart: ~9 unieke group namen (stocks, AI, graphs, HA, Badkamer, YT, Gmail, Nasses, socials) verspreid over 5 windows, maar het menu toont **honderden tot duizenden** entries.

## 🔍 Wat we al weten

- ✅ Chrome sync is **uit** (Tab groups, Open tabs, Saved tab groups allemaal disabled)
- ✅ "Save Tab Groups for Tab Session Manager" companion extensie is verwijderd
- ✅ Het is **niet** een bookmark-issue (gechecked via `chrome://bookmarks`)
- ✅ Het is **niet** simpel het aantal windows × unieke groups (lijst blijft groeien bij identieke 5 windows)
- ❌ "Save tab groups" in TSM uitzetten lost het op, maar verliest dan de group namen — geen optie

## 🤔 Hypotheses (te testen)

**Hypothese A:** Er zijn "ghost" tab groups — groups die bestaan in Chrome's interne state maar geen actieve tabs/window meer hebben. Zou via `chrome.tabGroups.query({})` zichtbaar moeten zijn.

**Hypothese B:** Het zijn "saved tab groups" in Chrome's interne database, opgeslagen in:
```
%LOCALAPPDATA%\Google\Chrome\User Data\Default\Tab Groups
```
Deze zijn **niet** via een extension API benaderbaar — alleen via direct SQLite access op disk.

**Hypothese C:** TSM zelf houdt een eigen interne registry bij die parallel groeit en Chrome dwingt deze te tonen.

## 🛠️ Toolkit in dit project

### `diagnostic-extension/`
Een mini Chrome extensie die laat zien wat `chrome.tabGroups.query({})` precies teruggeeft. Eerste stap om te bepalen welke hypothese klopt.

### `python-tools/`
Python scripts om Chrome's interne SQLite database te inspecteren (en eventueel op te schonen). Veiliger dan direct edit — maakt altijd eerst backup.

## 🎬 Workflow

**Fase 1 — Diagnose** 🔬
1. Installeer `diagnostic-extension/` als unpacked extensie in Chrome
2. Klik "Scan tab groups" → noteer aantal vs. wat het menu toont
3. Run `python-tools/inspect_tab_groups_db.py` → zie wat er in de SQLite zit
4. **Conclusie**: hypothese A, B of C?

**Fase 2 — Cleanup tool bouwen** 🧹
Op basis van fase 1, kies de juiste aanpak:
- Hypothese A → extensie uitbreiden met cleanup functie
- Hypothese B → Python script dat database opschoont (Chrome moet dicht)
- Hypothese C → uitzoeken waar TSM zijn state bewaart (chrome.storage.local van die extensie)

**Fase 3 — Preventie** 🛡️
Eenmalige cleanup is leuk maar het blijft gebeuren. Final tool moet ofwel:
- Auto-cleanup draaien bij elke Chrome start
- Of een knop die je 1x per week indrukt
- Of TSM gedrag onderscheppen (lastiger)

## 👤 User context

- Tristan is geen programmeur maar wel technisch (HTML/CSS/PHP achtergrond, 25+ jaar 3D)
- Geef altijd **complete scripts**, geen patches
- Versie nummers (`v1`, `v2`) i.p.v. `_FINAL` of `_FIXED`
- Emoji in scripts voor visuele scanning is OK en gewenst 📊
- Communiceert in Nederlands, maar code en docs in Engels
- Windows machine, gebruikt UNC/backslash paths
- Directory Opus voor file management

## 🚨 Veiligheidsregels

- Voor je iets in Chrome's `User Data` folder aanraakt: **ALTIJD backup eerst**
- Chrome moet **volledig afgesloten** zijn voor SQLite file edits (anders database lock)
- Test elke destructive operatie eerst op een kopie van de database
- Bij twijfel: alleen READ operations, vraag bevestiging voor WRITE/DELETE

## 📋 Useful paths op Windows

```
Chrome profile:        %LOCALAPPDATA%\Google\Chrome\User Data\Default\
Tab Groups DB:         %LOCALAPPDATA%\Google\Chrome\User Data\Default\Tab Groups
Bookmarks:             %LOCALAPPDATA%\Google\Chrome\User Data\Default\Bookmarks
Session storage:       %LOCALAPPDATA%\Google\Chrome\User Data\Default\Sessions\
TSM extension storage: %LOCALAPPDATA%\Google\Chrome\User Data\Default\Local Extension Settings\iaiomicjabeggjcfkbimgmglanimpnae\
```

(TSM extension ID `iaiomicjabeggjcfkbimgmglanimpnae` te verifiëren via `chrome://extensions`)

## 🎯 Eindresultaat

Een tool (extensie + eventueel Python helper) die:
1. De huidige duplicate explosion opruimt
2. Detecteert wanneer het opnieuw gebeurt
3. Eventueel auto-cleanup doet
4. Open source op GitHub als help voor anderen met hetzelfde probleem 🦸
