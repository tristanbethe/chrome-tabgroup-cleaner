// 📊 Tab Group Diagnostic Tool v1
// Goal: see exactly what chrome.tabGroups.query({}) returns
// and figure out where the duplicates come from.

const output = document.getElementById('output');
let lastScanData = null;

// 🔍 Full scan - everything at once
document.getElementById('scan').addEventListener('click', async () => {
  output.innerHTML = '<div class="stat">⏳ Scanning...</div>';

  try {
    const groups = await chrome.tabGroups.query({});
    const windows = await chrome.windows.getAll({ populate: false });
    const tabs = await chrome.tabs.query({});

    // Count groups per name
    const nameCount = {};
    groups.forEach(g => {
      const name = g.title || '(no name)';
      nameCount[name] = (nameCount[name] || 0) + 1;
    });

    // Count how many tabs are in each group
    const tabsPerGroup = {};
    tabs.forEach(t => {
      if (t.groupId && t.groupId !== -1) {
        tabsPerGroup[t.groupId] = (tabsPerGroup[t.groupId] || 0) + 1;
      }
    });

    // Find "empty" groups (no tabs)
    const emptyGroups = groups.filter(g => !tabsPerGroup[g.id]);

    lastScanData = { groups, windows, tabs, nameCount, tabsPerGroup, emptyGroups };

    let html = '';
    html += '<h3>📈 Statistics</h3>';
    html += `<div class="stat">🪟 Number of Chrome windows: <b>${windows.length}</b></div>`;
    html += `<div class="stat">📁 Total tab groups (via API): <b>${groups.length}</b></div>`;
    html += `<div class="stat">🏷️ Unique group names: <b>${Object.keys(nameCount).length}</b></div>`;
    html += `<div class="stat">📑 Total open tabs: <b>${tabs.length}</b></div>`;

    const emptyClass = emptyGroups.length > 0 ? 'warn' : 'ok';
    html += `<div class="stat ${emptyClass}">👻 Empty groups (no tabs): <b>${emptyGroups.length}</b></div>`;

    html += '<h3>🏷️ Groups per name</h3><pre>';
    const sorted = Object.entries(nameCount).sort((a,b) => b[1] - a[1]);
    sorted.forEach(([name, count]) => {
      const cls = count > 1 ? 'dup' : 'ok';
      const icon = count > 1 ? '🔴' : '✅';
      html += `<span class="${cls}">${icon} ${name.padEnd(20)} ${count}x</span>\n`;
    });
    html += '</pre>';

    if (emptyGroups.length > 0) {
      html += '<h3>👻 Empty groups (likely duplicates)</h3><pre>';
      emptyGroups.slice(0, 50).forEach(g => {
        html += `  id=${g.id} title="${g.title || '(none)'}" color=${g.color} window=${g.windowId}\n`;
      });
      if (emptyGroups.length > 50) {
        html += `  ... and ${emptyGroups.length - 50} more\n`;
      }
      html += '</pre>';
    }

    output.innerHTML = html;

  } catch (err) {
    output.innerHTML = `<div class="stat" style="color:#f87171">❌ Error: ${err.message}<br><br>Stack:<pre>${err.stack}</pre></div>`;
  }
});

// 🪟 Per-window breakdown
document.getElementById('windows').addEventListener('click', async () => {
  output.innerHTML = '<div class="stat">⏳ Scanning...</div>';

  try {
    const windows = await chrome.windows.getAll({ populate: true });
    const groups = await chrome.tabGroups.query({});

    let html = `<h3>🪟 ${windows.length} windows found</h3>`;

    windows.forEach((win, idx) => {
      const winGroups = groups.filter(g => g.windowId === win.id);
      const activeMarker = win.focused ? ' 🎯 ACTIVE' : '';
      const stateMarker = win.state !== 'normal' ? ` [${win.state}]` : '';

      html += `<h3>Window ${idx + 1} (id=${win.id})${activeMarker}${stateMarker}</h3>`;
      html += `<div class="stat">📑 ${win.tabs.length} tabs, 📁 ${winGroups.length} groups</div>`;

      if (winGroups.length > 0) {
        html += '<pre>';
        winGroups.forEach(g => {
          const tabCount = win.tabs.filter(t => t.groupId === g.id).length;
          const marker = tabCount === 0 ? '👻' : '✅';
          html += `  ${marker} ${(g.title || '(none)').padEnd(20)} [${g.color}] ${tabCount} tabs\n`;
        });
        html += '</pre>';
      }
    });

    output.innerHTML = html;

  } catch (err) {
    output.innerHTML = `<div class="stat" style="color:#f87171">❌ Error: ${err.message}</div>`;
  }
});

// 🔴 Show duplicates only
document.getElementById('duplicates').addEventListener('click', async () => {
  output.innerHTML = '<div class="stat">⏳ Scanning...</div>';

  try {
    const groups = await chrome.tabGroups.query({});

    // Group by name
    const byName = {};
    groups.forEach(g => {
      const key = g.title || '(no name)';
      if (!byName[key]) byName[key] = [];
      byName[key].push(g);
    });

    // Keep only where count > 1
    const duplicates = Object.entries(byName).filter(([_, gs]) => gs.length > 1);

    let html = `<h3>🔴 ${duplicates.length} group names have duplicates</h3>`;

    duplicates.sort((a, b) => b[1].length - a[1].length);

    duplicates.forEach(([name, gs]) => {
      html += `<h3>${name} (${gs.length}x)</h3>`;
      html += '<pre>';
      gs.forEach(g => {
        html += `  id=${g.id} color=${g.color} window=${g.windowId} collapsed=${g.collapsed}\n`;
      });
      html += '</pre>';
    });

    if (duplicates.length === 0) {
      html += '<div class="stat ok">✅ No duplicates found in the chrome.tabGroups API!<br>So the duplicates live elsewhere (e.g. Chrome\'s internal saved tab groups database).</div>';
    }

    output.innerHTML = html;

  } catch (err) {
    output.innerHTML = `<div class="stat" style="color:#f87171">❌ Error: ${err.message}</div>`;
  }
});

// 📋 Export as JSON
document.getElementById('export').addEventListener('click', async () => {
  try {
    const groups = await chrome.tabGroups.query({});
    const windows = await chrome.windows.getAll({ populate: true });
    const tabs = await chrome.tabs.query({});

    const data = {
      timestamp: new Date().toISOString(),
      chromeVersion: navigator.userAgent,
      summary: {
        totalGroups: groups.length,
        totalWindows: windows.length,
        totalTabs: tabs.length,
      },
      groups: groups,
      windowSummary: windows.map(w => ({
        id: w.id,
        focused: w.focused,
        state: w.state,
        tabCount: w.tabs.length,
        groupIds: [...new Set(w.tabs.map(t => t.groupId).filter(id => id !== -1))]
      }))
    };

    const json = JSON.stringify(data, null, 2);
    await navigator.clipboard.writeText(json);

    output.innerHTML = `<div class="stat ok">✅ JSON copied to clipboard (${json.length} chars)<br>Paste it somewhere to analyze</div><pre>${json.substring(0, 2000)}${json.length > 2000 ? '\n\n... (truncated, full data in clipboard)' : ''}</pre>`;

  } catch (err) {
    output.innerHTML = `<div class="stat" style="color:#f87171">❌ Error: ${err.message}</div>`;
  }
});

// 🧹 Clear output
document.getElementById('clear').addEventListener('click', () => {
  output.innerHTML = '';
});
