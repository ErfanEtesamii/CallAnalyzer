/* Content script: تزریق UI داخل Shadow DOM به جدول DataTables پنل Issabel. */
(() => {
  /* بعد از به‌روزرسانی افزونه، نمونه‌ی قدیمیِ این اسکریپت در صفحه می‌ماند (مرده)؛ آثار سراسری‌اش (ستون انتخاب‌همه و نوار پایین) را پاک می‌کنیم
     تا نمونه‌ی جدید بدون تکرار جایگزین شود. هاست‌های ردیف‌ها بازاستفاده می‌شوند (decorateRow wrap قدیمی را عوض می‌کند). */
  document.querySelectorAll('th.ca-th, .ca-bar-host').forEach((n) => n.remove());
  /* هر نمونه شناسه‌ای روی <html> می‌گذارد؛ نمونه‌ی قدیمی که کنار آمده دیگر چیزی در صفحه نمی‌کشد (observerهایش بی‌اثر می‌شوند). */
  const INSTANCE = Math.random().toString(36).slice(2);
  document.documentElement.dataset.caInstance = INSTANCE;
  const alive = () => document.documentElement.dataset.caInstance === INSTANCE;
  const P = self.CAParser, CS = self.CASettings;
  const CAQ = self.CAQueue || { isActive: (j) => ['queued', 'downloading', 'uploading', 'processing'].includes(j.state), totalMinutes: () => 0 };
  const state = { rows: new Map(), selected: new Set(), jobs: {}, results: {}, minSeconds: 20, cdr: {}, s: CS.normalize({}), extList: [], order: [], lastUid: null, selectAll: null };
  /* دانلود صوت از طرف service worker: این‌جا اجرا می‌شود چون همین صفحه گواهی و نشست پنل را دارد. */
  if (self.CATransfer && chrome.runtime.onMessage) {
    const fetcher = self.CATransfer.createPanelFetcher({ fetchFn: (u, o) => fetch(u, o), baseHref: location.href });
    chrome.runtime.onMessage.addListener((msg, _sender, send) => {
      if (!msg || !/^WAV_|^FETCH_WAV$/.test(msg.type)) return false;
      fetcher.handle(msg).then(send, (e) => send({ ok: false, code: 'panel_network', message: String(e && e.message || e) }));
      return true;
    });
  }
  const IS_CDR = /[?&]menu=cdrreport/.test(location.search);
  const CSS = `
:host{all:initial;font-family:Vazirmatn,Tahoma,system-ui,sans-serif;direction:rtl}
*{box-sizing:border-box;font-family:inherit}
.wrap{display:inline-flex;align-items:center;gap:6px;min-width:190px;direction:rtl;font-size:12px}
.btn{border:1px solid #14919B;background:#fff;color:#0E7C86;border-radius:999px;padding:3px 10px;cursor:pointer;font-size:12px;line-height:1.6}
.btn:hover{background:#E8F6F7}.btn:focus-visible{outline:3px solid rgba(20,145,155,.35)}.btn:active{transform:scale(.98)}
.btn.primary{background:#0E7C86;color:#fff}.btn.primary:hover{background:#0B646C}
.cb{width:16px;height:16px;accent-color:#0E7C86;cursor:pointer}
.pill{border-radius:999px;padding:2px 9px;font-size:11px;background:#F1EFEA;color:#5B6168;white-space:nowrap}
.pill.queued{background:#E3F0FA;color:#2B6CA3}.pill.run{background:#E8F6F7;color:#0E7C86}
.pill.A{background:#1E9E6A;color:#fff}.pill.B{background:#14919B;color:#fff}.pill.C{background:#E0A526;color:#1F2428}
.pill.D{background:#E9742F;color:#fff}.pill.F{background:#D64545;color:#fff}.pill.err{background:#FBE5E5;color:#B03030;cursor:pointer}
.dis{opacity:.45}
.th{display:inline-flex;align-items:center;gap:6px}
.bar{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#1F2428;color:#fff;border-radius:16px;
 padding:10px 16px;display:flex;gap:12px;align-items:center;box-shadow:0 6px 20px rgba(20,30,40,.3);font-size:13px;z-index:2147483647;
 animation:up .25s cubic-bezier(.2,.8,.2,1)}
@keyframes up{from{transform:translate(-50%,20px);opacity:0}}
@media (prefers-reduced-motion:reduce){.bar{animation:none}}
.bar .btn{border-color:transparent}.bar .ghost{background:transparent;color:#fff;border:1px solid #fff4}
.toast{position:fixed;bottom:20px;left:20px;background:#fff;border:1px solid #E4E1DA;border-radius:12px;padding:10px 14px;font-size:13px;color:#1F2428;box-shadow:0 6px 20px rgba(20,30,40,.12);z-index:2147483647;max-width:340px;direction:rtl}`;

  const mk = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const fmt = (n) => new Intl.NumberFormat('fa-IR').format(n);

  function findTable() {
    for (const t of document.querySelectorAll('table')) {
      const heads = [...t.querySelectorAll('thead th, tr:first-child th')].map((h) => h.textContent);
      const map = P.mapColumns(heads);
      if ('duration' in map && 'message' in map) return { table: t, map, heads };
    }
    return null;
  }

  function readRows(found) {
    const out = [];
    for (const tr of found.table.querySelectorAll('tbody tr')) {
      const tds = [...tr.children];
      if (tds.length < 3 || tr.querySelector('.dataTables_empty')) continue;
      const links = [...tr.querySelectorAll('a[href]')].map((a) => a.getAttribute('href'));
      const row = P.parseRow(found.map, tds.map((td) => td.textContent), links, location.href);
      if (row) out.push({ tr, row });
    }
    return out;
  }


  function reasonFor(row) {
    const cdr = state.cdr[row.uniqueId];
    const c = cdr && cdr.internal && state.s.includeInternal ? { ...cdr, internal: false } : cdr;
    const base = P.ineligibleReason(row, state.minSeconds, c);
    if (base) return base;
    const ext = (cdr && cdr.extension) || row.extension;
    if (state.extList.length && !state.extList.includes(String(ext))) return 'خارج از داخلی‌های انتخاب‌شده در تنظیمات';
    return P.isPrimary(row, state.rows) ? null : 'ردیف تکراری (نسخه‌ی کامل‌تر همین تماس در جدول هست)';
  }

  function statusPill(uid, row) {
    const j = state.jobs[uid], r = state.results[uid];
    const why = reasonFor(row);
    const p = mk('span', 'pill');
    if (j && j.state === 'error') { p.className = 'pill err'; p.textContent = 'خطا'; p.title = j.error || ''; p.onclick = () => chrome.runtime.sendMessage({ type: 'RETRY', uniqueId: uid }); return p; }
    if (j && j.state === 'queued') { p.className = 'pill queued'; p.textContent = 'در صف'; return p; }
    if (j && ['downloading', 'uploading', 'processing'].includes(j.state)) { p.className = 'pill run'; p.textContent = 'در حال تحلیل…'; return p; }
    const done = (j && j.state === 'done') ? j : (r && r.status === 'done' ? { score: r.overall_score, grade: r.grade } : null);
    if (done && done.score != null) { p.className = 'pill ' + (done.grade || ''); p.textContent = state.s.showScoreInPill ? `امتیاز ${fmt(Math.round(done.score))} ${done.grade || ''}` : `درجه ${done.grade || '-'}`; p.title = 'باز کردن در پنل'; p.style.cursor = 'pointer'; p.onclick = () => openPanel(uid); return p; }
    if (done) { p.textContent = 'تحلیل‌پذیر نبود'; return p; }
    if (why) { p.textContent = 'غیرقابل‌تحلیل'; p.title = why; return p; }
    p.textContent = 'تحلیل‌نشده';
    return p;
  }

  function payloadRows(uids) {
    return uids.map((u) => state.rows.get(u)).filter(Boolean).map((r) => ({ ...r, extension: (state.cdr[r.uniqueId] || {}).extension || r.extension, talkSec: (state.cdr[r.uniqueId] || {}).talkSec ?? null }));
  }
  const busyOrDone = (uid) => { const j = state.jobs[uid], r = state.results[uid]; return !!((j && (CAQ.isActive(j) || j.state === 'done')) || (r && r.status === 'done')); };
  const isSelectable = (row) => !reasonFor(row) && !busyOrDone(row.uniqueId);

  async function openPanel(uid) {
    await chrome.storage.local.set({ focusUid: uid });
    chrome.runtime.sendMessage({ type: 'OPEN_PANEL' });
  }

  async function enqueue(uids, force) {
    const rows = payloadRows(uids);
    if (!rows.length) return;
    if (rows.length > state.s.confirmBulkOver) {
      const min = CAQ.totalMinutes(rows);
      if (!confirm(`${fmt(rows.length)} تماس (حدود ${fmt(min)} دقیقه صوت) به صف تحلیل اضافه شود؟ این کار هزینه‌ی API دارد.`)) return;
    }
    const r = await chrome.runtime.sendMessage({ type: 'ENQUEUE', rows, force });
    if (r && r.ok) toast(r.skipped ? `${fmt(r.added)} تماس به صف رفت؛ ${fmt(r.skipped)} مورد از قبل در صف بود.` : `${fmt(r.added)} تماس به صف تحلیل اضافه شد.`);
    else toast('ارسال به صف ناموفق بود. افزونه را دوباره بارگذاری کنید.');
  }

  function decorateRow(tr, row) {
    let host = tr.querySelector(':scope > td.ca-cell > .ca-host');
    if (!host) {
      const td = mk('td', 'ca-cell'); td.style.whiteSpace = 'nowrap';
      host = mk('div', 'ca-host'); td.appendChild(host); tr.appendChild(td);
      host.attachShadow({ mode: 'open' }).appendChild(Object.assign(document.createElement('style'), { textContent: CSS }));
    }
    const sr = host.shadowRoot;
    sr.querySelector('.wrap')?.remove();
    const wrap = mk('div', 'wrap');
    const why = reasonFor(row);
    const cb = mk('input', 'cb'); cb.type = 'checkbox'; cb.checked = state.selected.has(row.uniqueId);
    cb.setAttribute('aria-label', 'انتخاب تماس برای تحلیل');
    if (why) { cb.disabled = true; wrap.classList.add('dis'); wrap.title = why; } else if (busyOrDone(row.uniqueId)) cb.disabled = true;
    cb.onclick = (e) => {
      const on = cb.checked;
      if (e.shiftKey && state.lastUid && state.lastUid !== row.uniqueId) {
        const a = state.order.indexOf(state.lastUid), b2 = state.order.indexOf(row.uniqueId);
        if (a >= 0 && b2 >= 0) for (let i = Math.min(a, b2); i <= Math.max(a, b2); i++) {
          const r = state.rows.get(state.order[i]);
          if (r && isSelectable(r)) on ? state.selected.add(r.uniqueId) : state.selected.delete(r.uniqueId);
        }
      } else on ? state.selected.add(row.uniqueId) : state.selected.delete(row.uniqueId);
      state.lastUid = row.uniqueId; refresh();
    };
    const b = mk('button', 'btn', '✦ تحلیل'); b.disabled = !!why;
    b.onclick = () => enqueue([row.uniqueId], false);
    wrap.append(cb, b, statusPill(row.uniqueId, row));
    sr.appendChild(wrap);
  }

  let barHost = null;
  function renderBar() {
    if (!alive()) return;
    if (!barHost) {
      barHost = mk('div', 'ca-bar-host'); barHost.attachShadow({ mode: 'open' }).appendChild(Object.assign(document.createElement('style'), { textContent: CSS }));
      document.body.appendChild(barHost);
    }
    const sr = barHost.shadowRoot; sr.querySelector('.bar')?.remove();
    const n = state.selected.size; if (!n) return;
    const bar = mk('div', 'bar'); bar.setAttribute('role', 'region'); bar.setAttribute('aria-label', 'عملیات انتخاب‌شده‌ها');
    const mins = CAQ.totalMinutes(payloadRows([...state.selected]));
    const go = mk('button', 'btn primary', mins ? `تحلیل (حدود ${fmt(mins)} دقیقه)` : 'تحلیل'); go.onclick = async () => { const uids = [...state.selected]; state.selected.clear(); refresh(); await enqueue(uids, false); };
    const clr = mk('button', 'btn ghost', 'پاک‌کردن'); clr.onclick = () => { state.selected.clear(); refresh(); };
    const panel = mk('button', 'btn ghost', 'باز کردن پنل تحلیل'); panel.onclick = () => chrome.runtime.sendMessage({ type: 'OPEN_PANEL' });
    bar.append(mk('span', '', `${fmt(n)} تماس انتخاب شد`), go, panel, clr);
    sr.appendChild(bar);
  }

  function toast(msg) {
    if (!barHost) renderBar();
    const t = mk('div', 'toast', msg); t.setAttribute('role', 'status');
    (barHost || document.body).shadowRoot.appendChild(t); setTimeout(() => t.remove(), 4000);
  }

  let busy = false, dirty = false;
  function refresh() {
    if (!alive()) return;
    if (busy) { dirty = true; return; } // فراخوانیِ حین مشغولی گم نشود
    busy = true;
    try {
      const found = findTable(); if (!found) return;
      const rows = readRows(found);
      const header = found.table.querySelector('thead tr, tr');
      if (header && !header.querySelector('th.ca-th')) {
        const th = mk('th', 'ca-th'); const lab = mk('label', 'th'); lab.style.cursor = 'pointer';
        const all = mk('input'); all.type = 'checkbox'; all.title = 'انتخاب همه‌ی تماس‌های قابل‌تحلیل'; all.setAttribute('aria-label', 'انتخاب همه‌ی تماس‌های قابل‌تحلیل');
        lab.addEventListener('click', (e) => e.stopPropagation());
        all.onchange = () => {
          const sel = [...state.rows.values()].filter(isSelectable);
          const everySelected = sel.length && sel.every((r) => state.selected.has(r.uniqueId));
          sel.forEach((r) => (everySelected ? state.selected.delete(r.uniqueId) : state.selected.add(r.uniqueId)));
          refresh();
        };
        lab.append(all, document.createTextNode('تحلیل')); th.append(lab); header.appendChild(th); state.selectAll = all;
      } else if (header) state.selectAll = header.querySelector('th.ca-th input');
      const bestRows = P.dedupe(rows.map((x) => x.row));
      bestRows.forEach((r) => state.rows.set(r.uniqueId, r));
      state.order = [...new Set(rows.map((x) => x.row).filter((r) => P.isPrimary(r, state.rows)).map((r) => r.uniqueId))];
      state.selected.forEach((u) => { const r = state.rows.get(u); if (!r || !isSelectable(r)) state.selected.delete(u); });
      rows.forEach(({ tr, row }) => decorateRow(tr, row));
      if (state.selectAll) {
        const sel = [...state.rows.values()].filter(isSelectable), n = sel.filter((r) => state.selected.has(r.uniqueId)).length;
        state.selectAll.disabled = !sel.length; state.selectAll.checked = !!sel.length && n === sel.length; state.selectAll.indeterminate = n > 0 && n < sel.length;
      }
      renderBar();
    } finally { setTimeout(() => { busy = false; if (dirty) { dirty = false; refresh(); } }, 0); }
  }

  async function syncStatuses() {
    if (!alive()) return;
    const uids = [...state.rows.keys()].filter((u) => !state.jobs[u]);
    if (!uids.length) return;
    const r = await chrome.runtime.sendMessage({ type: 'BATCH_STATUS', uniqueIds: uids.slice(0, 200) });
    if (r && r.data) { Object.assign(state.results, r.data); refresh(); }
  }


  // ---------- صفحه‌ی ریز مکالمات: خواندن و ذخیره‌ی داده‌ی CDR ----------
  async function scrapeCdr() {
    if (!alive()) return;
    const rows = [];
    for (const tr of document.querySelectorAll('table tbody tr')) {
      if (tr.querySelector('.dataTables_empty')) continue;
      const r = P.parseCdrRow([...tr.children].map((td) => td.textContent));
      if (r) rows.push(r);
    }
    if (!rows.length) return;
    const merged = P.mergeCdr(rows);
    const { cdr = {} } = await chrome.storage.local.get('cdr');
    const next = { ...cdr };
    for (const [uid, v] of Object.entries(merged)) {
      next[uid] = { ...v, seenAt: Date.now() };
    }
    const keys = Object.keys(next);
    if (keys.length > 5000) keys.sort((a, b) => next[a].seenAt - next[b].seenAt).slice(0, keys.length - 5000).forEach((k) => delete next[k]);
    await chrome.storage.local.set({ cdr: next });
  }


  let autoDone = false;
  function autoRun() {
    if (autoDone || !state.s.autoAnalyze) return; autoDone = true;
    const uids = [...state.rows.values()].filter((r) => isSelectable(r))
      .slice(0, state.s.autoLimit).map((r) => r.uniqueId);
    if (!uids.length) return;
    const rows = payloadRows(uids);
    chrome.runtime.sendMessage({ type: 'ENQUEUE', rows, force: false });
    toast(`تحلیل خودکار: ${fmt(rows.length)} تماس به صف رفت.`);
  }

  let t = null;
  const debounced = () => { clearTimeout(t); t = setTimeout(() => { refresh(); syncStatuses(); }, 250); };

  (async () => {
    const s = await chrome.storage.local.get([...Object.keys(CS.DEFAULTS), 'jobs', 'cdr']);
    state.s = CS.normalize(s); state.minSeconds = state.s.minSeconds; state.extList = CS.parseExtList(state.s.onlyExtensions);
    state.jobs = s.jobs || {}; state.cdr = s.cdr || {};
    if (IS_CDR) {
      scrapeCdr();
      new MutationObserver(() => { clearTimeout(t); t = setTimeout(scrapeCdr, 400); }).observe(document.body, { childList: true, subtree: true });
      return;
    }
    refresh(); await syncStatuses(); autoRun();
    const target = findTable()?.table.parentElement || document.body;
    new MutationObserver((muts) => { if (muts.some((m) => !(m.target.closest && m.target.closest('.ca-host')))) debounced(); })
      .observe(target, { childList: true, subtree: true });
    chrome.storage.onChanged.addListener((ch) => { if (ch.jobs) { state.jobs = ch.jobs.newValue || {}; refresh(); } if (ch.cdr) { state.cdr = ch.cdr.newValue || {}; refresh(); }
      if (Object.keys(CS.DEFAULTS).some((k) => ch[k])) { chrome.storage.local.get(Object.keys(CS.DEFAULTS)).then((v) => { state.s = CS.normalize(v); state.minSeconds = state.s.minSeconds; state.extList = CS.parseExtList(state.s.onlyExtensions); refresh(); }); } });
  })();
})();
