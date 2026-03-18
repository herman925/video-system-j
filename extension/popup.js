const APP_URL = "http://localhost:8765";

const JAV_RE = /\b([A-Z]{2,7}-\d{2,5})\b/g;

const SITE_LABELS = [
  [/javdb\.com/,        "JavDB"],
  [/javlibrary\.com/,   "JavLibrary"],
  [/dmm\.co\.jp/,       "DMM"],
  [/dmm\.com/,          "DMM"],
  [/mgstage\.com/,      "MGS"],
  [/caribbeancom\.com/, "Caribbean"],
  [/1pondo\.tv/,        "1Pondo"],
  [/10musume\.com/,     "10Musume"],
  [/heyzo\.com/,        "Heyzo"],
  [/fc2\.com/,          "FC2"],
  [/sukebei\.nyaa\.si/, "Nyaa"],
];

function siteLabel(url) {
  for (const [re, label] of SITE_LABELS) {
    if (re.test(url)) return label;
  }
  try { return new URL(url).hostname.replace(/^www\./, ""); }
  catch { return "—"; }
}

function refsFromText(text) {
  const m = [...text.matchAll(JAV_RE)];
  return [...new Set(m.map(x => x[1].toUpperCase()))];
}

// ── State ─────────────────────────────────────────────────────────────────────
// view: 'select' | 'confirm' | 'done'
let view = "select";

// items: { ref, label, tabTitle, tabUrl, windowId, windowIndex, checked, editRef }
let items = [];
// windowMap: windowId -> window index (1-based, sorted by focused first)
let windowMap = {};
let scanStats = { windows: 0, tabs: 0, withRefs: 0 };

// ── Scan ──────────────────────────────────────────────────────────────────────
async function scanAllWindows() {
  const windows = await chrome.windows.getAll({ populate: true, windowTypes: ["normal"] });
  const seen    = new Map(); // ref -> item (first occurrence wins)

  // Sort: focused window first
  windows.sort((a, b) => (b.focused ? 1 : 0) - (a.focused ? 1 : 0));
  windows.forEach((w, idx) => { windowMap[w.id] = idx + 1; });
  scanStats.windows = windows.length;

  for (const win of windows) {
    for (const tab of (win.tabs || [])) {
      const url   = tab.url   || "";
      const title = tab.title || "";
      if (url.startsWith(APP_URL) || /^(chrome|edge|about|moz-extension):/.test(url)) continue;
      scanStats.tabs++;
      const label = siteLabel(url);
      const refs  = refsFromText(url + " " + title);
      if (refs.length) scanStats.withRefs++;
      for (const ref of refs) {
        if (!seen.has(ref)) {
          seen.set(ref, {
            ref, label, tabTitle: title, tabUrl: url,
            windowId: win.id, windowIndex: windowMap[win.id],
            checked: true, editRef: ref,
          });
        }
      }
    }
  }
  items = [...seen.values()];
}

// ── Render dispatcher ─────────────────────────────────────────────────────────
function render() {
  if      (view === "select")  renderSelect();
  else if (view === "confirm") renderConfirm();
  else if (view === "done")    renderDone();
}

// ── Select view ───────────────────────────────────────────────────────────────
function renderSelect() {
  const list   = document.getElementById("list");
  const footer = document.getElementById("footer");
  setStatus("");

  // Summary
  const summary = document.getElementById("summary");
  if (items.length === 0) {
    summary.textContent =
      `${scanStats.tabs} tab${scanStats.tabs !== 1 ? "s" : ""} scanned across ` +
      `${scanStats.windows} window${scanStats.windows !== 1 ? "s" : ""} — no JAV refs found`;
    list.innerHTML = '<div class="empty">No JAV references found in open tabs.</div>';
    footer.innerHTML = "";
    return;
  }
  summary.textContent =
    `${scanStats.tabs} tab${scanStats.tabs !== 1 ? "s" : ""} · ` +
    `${scanStats.windows} window${scanStats.windows !== 1 ? "s" : ""} · ` +
    `${items.length} ref${items.length !== 1 ? "s" : ""} found`;

  // Group by window
  const byWindow = new Map();
  for (const item of items) {
    if (!byWindow.has(item.windowId)) byWindow.set(item.windowId, []);
    byWindow.get(item.windowId).push(item);
  }

  list.innerHTML = "";

  for (const [winId, winItems] of byWindow) {
    const winIdx = windowMap[winId] || "?";
    const hdr = document.createElement("div");
    hdr.className = "win-hdr";
    hdr.textContent = `Window ${winIdx}${winIdx === 1 ? " (active)" : ""} — ${winItems.length} ref${winItems.length !== 1 ? "s" : ""}`;
    list.appendChild(hdr);

    for (const item of winItems) {
      const row = document.createElement("div");
      row.className = "item" + (item.checked ? " checked" : "");

      const safeTitle = (item.tabTitle || "").replace(/</g, "&lt;");
      const safeUrl   = (item.tabUrl   || "").replace(/</g, "&lt;");
      const id = `cb-${item.ref}`;

      row.innerHTML = `
        <div class="item-top">
          <input type="checkbox" id="${id}" ${item.checked ? "checked" : ""}>
          <label for="${id}" class="ref">${item.ref}</label>
          <span class="site-badge">${item.label}</span>
        </div>
        <div class="item-meta">
          <span class="tab-title">${safeTitle}</span>
          <span class="tab-url">${safeUrl}</span>
        </div>
      `;

      const cb = row.querySelector("input");
      const toggle = () => {
        item.checked = cb.checked;
        row.className = "item" + (item.checked ? " checked" : "");
        updateNextBtn();
      };
      cb.addEventListener("change", toggle);
      row.addEventListener("click", e => {
        if (e.target.tagName === "INPUT" || e.target.tagName === "LABEL") return;
        cb.checked = !cb.checked;
        toggle();
      });

      list.appendChild(row);
    }
  }

  function updateNextBtn() {
    const n = items.filter(i => i.checked).length;
    const btn = document.getElementById("btn-next");
    if (btn) btn.textContent = `Review & Send (${n})`;
  }

  footer.innerHTML = `
    <button id="btn-selall"   class="btn-ghost">Select All</button>
    <button id="btn-deselall" class="btn-ghost">Deselect All</button>
    <button id="btn-next" class="btn-primary">Review &amp; Send (${items.filter(i => i.checked).length})</button>
  `;

  document.getElementById("btn-selall").addEventListener("click", () => {
    items.forEach(i => i.checked = true); render();
  });
  document.getElementById("btn-deselall").addEventListener("click", () => {
    items.forEach(i => i.checked = false); render();
  });
  document.getElementById("btn-next").addEventListener("click", () => {
    const selected = items.filter(i => i.checked);
    if (!selected.length) { setStatus("Nothing selected.", "#ef4444"); return; }
    selected.forEach(i => i.editRef = i.ref);
    view = "confirm";
    render();
  });
}

// ── Confirm view ──────────────────────────────────────────────────────────────
function renderConfirm() {
  const list   = document.getElementById("list");
  const footer = document.getElementById("footer");
  setStatus("");

  const selected = items.filter(i => i.checked);

  list.innerHTML = `<div class="confirm-hdr">Review and edit refs if needed:</div>`;
  for (const item of selected) {
    const safeTitle = (item.tabTitle || "").replace(/</g, "&lt;");
    const row = document.createElement("div");
    row.className = "confirm-row";
    row.innerHTML = `
      <input class="ref-edit" type="text" value="${item.editRef}">
      <span class="confirm-meta" title="${safeTitle}">${item.label} · ${safeTitle}</span>
    `;
    row.querySelector(".ref-edit").addEventListener("input", e => {
      item.editRef = e.target.value.trim().toUpperCase();
    });
    list.appendChild(row);
  }

  footer.innerHTML = `
    <button id="btn-back" class="btn-ghost">← Back</button>
    <button id="btn-send" class="btn-primary">Add ${selected.length} to Queue</button>
  `;
  document.getElementById("btn-back").addEventListener("click", () => { view = "select"; render(); });
  document.getElementById("btn-send").addEventListener("click", sendRefs);
}

// ── Done view ─────────────────────────────────────────────────────────────────
function renderDone() {
  const footer = document.getElementById("footer");
  footer.innerHTML = `<button id="btn-close" class="btn-primary">Close</button>`;
  document.getElementById("btn-close").addEventListener("click", () => window.close());
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function setStatus(msg, colour = "#4b5563") {
  const el = document.getElementById("status");
  el.textContent = msg;
  el.style.color = colour;
}

async function sendRefs() {
  const refs = items.filter(i => i.checked).map(i => i.editRef).filter(Boolean);
  if (!refs.length) return;
  document.getElementById("btn-send").disabled = true;
  setStatus(`Sending ${refs.length} ref(s)…`, "#818cf8");
  try {
    const res = await fetch(`${APP_URL}/api/queue`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refs }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    document.getElementById("list").innerHTML =
      `<div class="empty" style="color:#4ade80;padding:28px 14px">
         ✓ ${data.added} ref${data.added !== 1 ? "s" : ""} sent to queue!
      </div>`;
    setStatus(`${data.skipped} skipped / invalid`, "#4b5563");
    view = "done";
    renderDone();
  } catch (err) {
    setStatus(`Error: ${err.message} — is the app running?`, "#ef4444");
    document.getElementById("btn-send").disabled = false;
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────
scanAllWindows().then(render);
