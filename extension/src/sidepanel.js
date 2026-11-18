/* پنل کناری. همه‌ی متن پویا با textContent ساخته می‌شود (بدون innerHTML) تا XSS ممکن نباشد. */
'use strict';
const $ = (s) => document.querySelector(s);
const fa = new Intl.NumberFormat('fa-IR');
const fa1 = new Intl.NumberFormat('fa-IR', { maximumFractionDigits: 1 });
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
const el = (tag, cls, text, attrs) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  if (attrs) for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
};
const call = (type, extra = {}) => chrome.runtime.sendMessage({ type, ...extra });
const api = (path, init) => call('API', { path, init });

/* ---------- آیکون‌ها (مسیرهای ثابت) ---------- */
const ICONS = {
  music: ['M9 18V5l11-2v13', 'M9 18a3 3 0 1 1-3-3 3 3 0 0 1 3 3z', 'M20 16a3 3 0 1 1-3-3 3 3 0 0 1 3 3z'],
  analysis: ['M4 19V5', 'M4 19h16', 'M8 15l3-4 3 2 4-6'],
  queue: ['M9 6h11', 'M9 12h11', 'M9 18h11', 'M4.5 6h.01', 'M4.5 12h.01', 'M4.5 18h.01'],
  history: ['M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z', 'M12 7v5l3 2'],
  compare: ['M5 20V11', 'M12 20V4', 'M19 20v-6'],
  settings: ['M4 7h9', 'M17 7h3', 'M4 17h3', 'M11 17h9', 'M15 5v4', 'M9 15v4'],
  theme: ['M12 21a9 9 0 1 0 0-18z'],
  copy: ['M9 9h10v11H9z', 'M5 15V4h10'],
  play: ['M8 5.5v13l11-6.5z'],
  check: ['M5 12.5l4.5 4.5L19 7.5'],
  alert: ['M12 4l9 16H3z', 'M12 10v4', 'M12 17h.01'],
  bolt: ['M13 3L5 14h6l-1 7 8-11h-6z'],
  user: ['M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8z', 'M4 21a8 8 0 0 1 16 0'],
  headset: ['M4 14v-2a8 8 0 0 1 16 0v2', 'M4 14h3v5H4z', 'M17 14h3v5h-3z', 'M20 19a4 4 0 0 1-4 3h-2'],
  phone: ['M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z'],
  calendar: ['M5 6h14v14H5z', 'M5 10h14', 'M9 3v4', 'M15 3v4'],
  clock: ['M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z', 'M12 7v5l3 2'],
  flag: ['M5 21V4', 'M5 4h11l-2 4 2 4H5'],
  list: ['M6 4h12v16H6z', 'M9 9h6', 'M9 13h6', 'M9 17h3'],
  chat: ['M4 5h16v11H9l-5 4z'],
  download: ['M12 4v11', 'M7 11l5 5 5-5', 'M5 20h14'],
  refresh: ['M20 11a8 8 0 1 0-2 6', 'M20 5v6h-6'],
  swap: ['M7 7h13', 'M16 3l4 4-4 4', 'M17 17H4', 'M8 13l-4 4 4 4'],
  chevron: ['M6 9l6 6 6-6'],
  search: ['M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14z', 'M20 20l-4-4'],
  bulb: ['M9 18h6', 'M10 21h4', 'M12 3a6 6 0 0 0-4 10.5c.7.7 1 1.5 1 2.5h6c0-1 .3-1.8 1-2.5A6 6 0 0 0 12 3z'],
  inbox: ['M4 13l2-8h12l2 8', 'M4 13v6h16v-6', 'M4 13h5l1 2h4l1-2h5'],
  logo: ['M12 3l2.2 5 5.3-2.3-2.3 5.3 5 2.2-5 2.2 2.3 5.3-5.3-2.3L12 21l-2.2-5-5.3 2.3 2.3-5.3-5-2.2 5-2.2-2.3-5.3L9.8 8z'],
};
function icon(name, cls = '') {
  const NS = 'http://www.w3.org/2000/svg';
  const s = document.createElementNS(NS, 'svg');
  s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('class', 'i ' + cls); s.setAttribute('aria-hidden', 'true');
  for (const d of ICONS[name] || []) { const p = document.createElementNS(NS, 'path'); p.setAttribute('d', d); s.append(p); }
  return s;
}
const withIcon = (name, text, cls) => { const e = el('span', cls); e.append(icon(name), document.createTextNode(text)); return e; };

/* ---------- برچسب‌ها و قالب‌ها ---------- */
const STAGE = { hot_ready: 'آماده‌ی اقدام', warm_followup: 'علاقه‌مند', nurturing: 'پرورش بلندمدت', gatekeeper_blocked: 'مانع مسیر', not_now: 'فعلاً نه', lost_competitor: 'خرید از رقیب', not_target: 'مخاطب هدف نیست', no_conversation: 'مکالمه‌ی معنادار نشد' };
const STAGE_HEAT = { hot_ready: 5, warm_followup: 4, nurturing: 3, gatekeeper_blocked: 2, not_now: 2, lost_competitor: 1, not_target: 1, no_conversation: 0 };
const LEAD = { contact_name: 'نام مخاطب', contact_title: 'سمت', tenure_in_org: 'سابقه در سازمان', familiar_with_handicrafts: 'آشنایی با صنایع‌دستی', occasion: 'مناسبت', recipients: 'گیرندگان هدیه', decision_unit_or_person: 'تصمیم‌گیر', other_influencers: 'سایر اثرگذاران', budget_range: 'بودجه', volume: 'تعداد یا حجم', last_year_gifting: 'هدیه‌ی سال قبل', previous_supplier: 'تأمین‌کننده‌ی قبلی', main_challenges: 'چالش‌های اصلی', decision_criteria: 'معیارهای تصمیم', timeline: 'زمان‌بندی', preferred_channel: 'کانال ترجیحی', agreed_next_step: 'قدم بعدی توافق‌شده', followup_datetime: 'زمان پیگیری', gatekeeper_info: 'اطلاعات مانع یا منشی' };
const STEPS = ['دانلود', 'آپلود', 'آماده‌سازی', 'رونویسی', 'تحلیل'];
const toneOf = (s) => (s >= 8.5 ? 'a' : s >= 7 ? 'b' : s >= 5.5 ? 'c' : s >= 4 ? 'd' : 'f');
const mmss = (s) => { const t = Math.max(0, Math.floor(s)); return fa.format(Math.floor(t / 60)).padStart(1, '۰') + ':' + String(t % 60).replace(/\d/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[d]).padStart(2, '۰'); };
const toSec = (t) => String(t || '0').split(':').map(Number).reduce((a, n) => a * 60 + (n || 0), 0);
const dateFa = (iso) => { try { return new Intl.DateTimeFormat('fa-IR-u-ca-persian', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso)); } catch { return iso || ''; } };
const leadLabel = (k) => LEAD[k.replace(/\(.*?\)/g, '').trim()] || k;
let tab = 'analysis', timer = null, SELLERS = {}, viewKind = 'empty'; // viewKind: empty | live | report (برای دنبال‌کردن خودکار کار تازه)
const sellerName = (a) => a.seller_name || SELLERS[a.seller_ext] || (a.seller_ext ? 'داخلی ' + a.seller_ext : '—');
const applyTheme = (th) => { if (th === 'light' || th === 'dark') document.documentElement.dataset.theme = th; else delete document.documentElement.dataset.theme; };

function toast(msg) {
  document.querySelector('.toast')?.remove();
  const t = el('div', 'toast', msg, { role: 'status' }); document.body.append(t); setTimeout(() => t.remove(), 2200);
}
async function copy(text, done) {
  try { await navigator.clipboard.writeText(text); toast(done || 'کپی شد'); } catch { toast('کپی ممکن نشد'); }
}
function empty(iconName, title, text, action) {
  const d = el('div', 'empty'); const art = el('div', 'art'); art.append(icon(iconName));
  d.append(art, el('h3', null, title), el('p', null, text));
  if (action) { const b = el('button', 'btn primary', action.label); b.onclick = action.fn; d.append(b); }
  return d;
}
/** خطای API: اگر مشکل اتصال/توکن است به تنظیمات هدایت می‌کند، وگرنه تلاش دوباره */
function errState(title, r, retry) {
  if (r.code === 'no_config' || r.code === 'auth') return empty('settings', r.code === 'auth' ? 'توکن پذیرفته نشد' : 'اتصال هنوز تنظیم نشده', r.error, { label: 'باز کردن تنظیمات', fn: () => chrome.runtime.openOptionsPage() });
  return empty('alert', title, r.error, { label: 'تلاش دوباره', fn: retry });
}
function skeleton() {
  const f = document.createDocumentFragment();
  [250, 84, 140, 200].forEach((h) => { const s = el('div', 'skel'); s.style.height = h + 'px'; f.append(s); });
  return f;
}
function secHead(iconName, title, extra) {
  const h = el('h2', 'sec-h'); h.append(icon(iconName), document.createTextNode(title)); if (extra) { h.append(el('span', 'sp'), extra); } return h;
}

/* ---------- بلوک اصلی ---------- */
function callStrip(a, r, jump) {
  const segs = (a.transcript && a.transcript.segments) || [];
  const total = Math.max(a.real_duration || 0, ...segs.map((s) => s.end), 1);
  const seller = (r.participants || {}).seller_speaker;
  const wrap = el('div', 'strip-wrap');
  const h = el('div', 'strip-h'); h.append(el('span', null, 'نوار تماس'), el('span', null, 'روی هر نقطه بزنید'));
  const strip = el('div', 'strip', null, { role: 'group', 'aria-label': 'نوار زمانی تماس' });
  const track = el('div', 'track');
  segs.forEach((s) => {
    const d = el('div', 'seg ' + (CALive.isSpecial(s) ? 'n' : s.speaker === seller || !s.speaker ? 's' : 'c'));
    d.style.insetInlineStart = (s.start / total * 100) + '%'; d.style.width = Math.max(0.4, (s.end - s.start) / total * 100) + '%';
    track.append(d);
  });
  strip.append(track);
  const mark = (t, text, cls, label) => {
    const b = el('button', 'mk ' + cls, null, { 'aria-label': label + ' در ' + mmss(t), title: label + ' ' + mmss(t) + (text ? ': ' + text : '') });
    b.style.insetInlineStart = Math.min(97, Math.max(3, t / total * 100)) + '%';
    b.onclick = (e) => { e.stopPropagation(); jump(t); }; strip.append(b);
  };
  const cs = r.customer_status || {};
  (cs.buying_signals || []).forEach((b) => mark(toSec(b.timestamp), b.quote, 'sig', 'نشانه‌ی خرید'));
  (cs.objections || []).forEach((o) => mark(toSec(o.timestamp), o.quote, 'obj', 'اعتراض'));
  strip.onclick = (e) => { const rc = strip.getBoundingClientRect(); jump(Math.max(0, Math.min(1, (rc.right - e.clientX) / rc.width)) * total); };
  const times = el('div', 'times'); times.append(el('span', null, mmss(0)), el('span', null, mmss(total)));
  const lg = el('div', 'legend');
  [['lg-s', 'فروشنده'], ['lg-c', 'مشتری'], ['lg-sig', 'نشانه‌ی خرید'], ['lg-obj', 'اعتراض']].forEach(([c, t]) => { const s = el('span'); s.append(el('i', c), document.createTextNode(t)); lg.append(s); });
  wrap.append(h, strip, times, lg);
  return wrap;
}

function hero(a, r, jump) {
  const o = r.overall || {}; const s = el('section', 'hero');
  const top = el('div', 'hero-top');
  const sc = el('div', 'score'); const num = el('b', null, fa.format(0)); sc.append(num, el('span', null, 'از ۱۰۰ امتیاز'));
  const stamp = el('div', 'stamp s-' + (o.grade || 'C')); stamp.append(el('b', null, o.grade || '-'), el('small', null, o.rank_label || ''));
  stamp.setAttribute('role', 'img'); stamp.setAttribute('aria-label', `درجه ${o.grade}، ${o.rank_label || ''}`);
  top.append(sc, stamp); s.append(top);
  const target = Math.round(o.score ?? 0);
  if (reduceMotion) num.textContent = fa.format(target);
  else { const t0 = performance.now(); const tick = (t) => { const p = Math.min(1, (t - t0) / 700); num.textContent = fa.format(Math.round(target * (1 - Math.pow(1 - p, 3)))); if (p < 1) requestAnimationFrame(tick); }; requestAnimationFrame(tick); }
  s.append(el('p', 'headline', o.headline || r.summary || ''));
  const meta = el('div', 'meta');
  [['calendar', dateFa(a.call_datetime)], ['user', sellerName(a)], ['phone', a.dst_masked, 'ltr'], ['clock', a.real_duration ? mmss(a.real_duration) : '']].forEach(([i, t, c]) => { if (t) meta.append(withIcon(i, t, c)); });
  s.append(meta);
  if (a.transcript && a.transcript.segments.length) s.append(callStrip(a, r, jump));
  s.append(el('p', 'conf', 'اطمینان تحلیل: ' + fa.format(Math.round((o.confidence || 0) * 100)) + '٪'));
  return s;
}

/* ---------- نمای تحلیل ---------- */
function renderAnalysis(a, audio) {
  const v = $('#view'); v.replaceChildren();
  const r = a.result;
  if (!r) { v.append(a.status === 'failed'
    ? empty('alert', 'تحلیل انجام نشد', a.error_message || 'خطای نامشخص. دوباره تلاش کنید.', { label: 'تحلیل مجدد', fn: () => api(`/api/v1/analyses/${a.id}/reanalyze`, { method: 'POST' }).then(() => load(a.unique_id)) })
    : empty('clock', 'در حال پردازش', 'نتیجه همین‌جا ظاهر می‌شود؛ لازم نیست صفحه را باز نگه دارید.')); return; }
  if (!r.call_validity.is_analyzable) { v.append(empty('inbox', 'این تماس قابل‌تحلیل نیست', r.call_validity.reason || 'مکالمه‌ی معناداری ثبت نشده است.')); return; }

  /* ترنسکریپت (ساخته می‌شود تا نوار تماس بتواند به آن برود) */
  const tr = a.transcript, seller = (r.participants || {}).seller_speaker;
  const bubbles = []; let trBox = null, trOpen = null;
  const jump = (t) => {
    if (audio && audio.src) { audio.currentTime = t; audio.play().catch(() => {}); }
    if (!bubbles.length) return;
    trOpen(true);
    let best = bubbles[0]; for (const b of bubbles) if (b.t <= t) best = b;
    bubbles.forEach((b) => b.e.classList.remove('hit')); best.e.classList.add('hit');
    best.e.scrollIntoView({ block: 'center', behavior: reduceMotion ? 'auto' : 'smooth' });
  };

  v.append(hero(a, r, jump));
  (r.warnings || []).forEach((w) => { const al = el('div', 'alert'); al.append(icon('alert'), el('span', null, w)); v.append(al); });

  const cs = r.customer_status || {};
  const tiles = el('div', 'tiles');
  const t1 = el('div', 'tile'); t1.append(el('small', null, 'وضعیت مشتری'), el('b', null, STAGE[cs.stage] || cs.stage || '—'));
  const heat = el('div', 'heat'); for (let i = 1; i <= 5; i++) heat.append(el('i', i <= (STAGE_HEAT[cs.stage] ?? 0) ? 'on' : '')); t1.append(heat);
  const t2 = el('div', 'tile'); t2.append(el('small', null, 'علاقه‌مندی'), el('b', null, fa.format(cs.interest_level ?? 0) + ' از ۱۰'), el('span', 'sub', (cs.objections || []).length ? fa.format(cs.objections.length) + ' اعتراض' : 'بدون اعتراض'));
  const t3 = el('div', 'tile'); t3.append(el('small', null, 'نسبت به قبل'));
  if (a.percentile != null) t3.append(el('b', null, 'بهتر از ' + fa.format(Math.round(a.percentile)) + '٪'), el('span', 'sub', 'تماس‌های همین فروشنده')); else t3.append(el('b', null, '—'), el('span', 'sub', 'داده‌ی کافی نیست'));
  tiles.append(t1, t2, t3); v.append(tiles);

  /* قدم بعدی */
  const nb = r.next_best_action || {};
  if (nb.recommendation) {
    const n = el('section', 'next'); const t = el('div', 't'); const ic = el('div', 'ic'); ic.append(icon('bolt'));
    const tx = el('div'); tx.append(el('div', 'main', nb.recommendation)); if (nb.suggested_followup) tx.append(el('div', 'when', nb.suggested_followup)); t.append(ic, tx); n.append(t);
    if ((nb.talking_points || []).length) { const ul = el('ul'); nb.talking_points.forEach((p) => { const li = el('li'); li.append(icon('check'), el('span', null, p)); ul.append(li); }); n.append(ul); }
    const b = el('button', 'btn sm', null); b.append(icon('copy'), document.createTextNode('کپی برای CRM')); b.style.justifySelf = 'start';
    b.onclick = () => copy([nb.recommendation, nb.suggested_followup, ...(nb.talking_points || []).map((x) => '- ' + x)].filter(Boolean).join('\n'), 'برای CRM کپی شد'); n.append(b);
    v.append(secHead('bolt', 'قدم بعدی'), n);
  }

  /* معیارها */
  const crits = r.criteria || [], applicable = crits.filter((c) => c.applicable && c.score != null);
  const weak = applicable.filter((c) => c.score <= 6), strong = applicable.filter((c) => c.score >= 8);
  let filter = 'all'; const list = el('div', 'panel');
  const rows = new Map();
  const buildRow = (c) => {
    const d = el('div', 'crit' + (c.applicable ? '' : ' is-na')); const hb = el('button', null, null, { 'aria-expanded': 'false' });
    hb.append(el('span', 'nm', c.name || c.id));
    if (c.applicable) hb.append(el('span', 'sc t-' + toneOf(c.score ?? 0), fa1.format(c.score ?? 0))); else hb.append(el('span', 'na', 'قابل‌اعمال نیست'));
    hb.append(icon('chevron', 'chev'));
    if (c.applicable) { const m = el('div', 'meter'), bar = el('i', 't-' + toneOf(c.score ?? 0)); bar.style.background = 'var(--g-' + toneOf(c.score ?? 0) + ')'; m.append(bar); hb.append(m); requestAnimationFrame(() => requestAnimationFrame(() => { bar.style.width = (c.score ?? 0) * 10 + '%'; })); }
    const det = el('div', 'detail');
    if (c.reasoning) det.append(el('p', null, c.reasoning));
    (c.evidence || []).forEach((e) => { const q = el('button', 'q' + (e.verified === false ? ' unv' : '')); const tm = el('span', 'tm'); tm.append(icon('play', 'fill'), document.createTextNode(mmss(toSec(e.timestamp)))); q.append(tm, el('span', null, '«' + e.quote + '»')); if (e.verified === false) q.append(el('span', 'flag', 'تأییدنشده')); q.onclick = () => jump(toSec(e.timestamp)); det.append(q); });
    if (c.improvement) { const t = el('div', 'tip'); t.append(icon('bulb'), el('span', null, c.improvement)); det.append(t); }
    if (c.better_phrase_example) { const bt = el('div', 'better'); bt.append(el('small', null, 'نمونه‌ی جمله‌ی بهتر'), document.createTextNode('«' + c.better_phrase_example + '»')); det.append(bt); }
    hb.onclick = () => { const open = d.classList.toggle('open'); hb.setAttribute('aria-expanded', open); };
    d.append(hb, det); rows.set(c.id, { d, hb }); return d;
  };
  crits.forEach((c) => list.append(buildRow(c)));
  const applyFilter = () => { crits.forEach((c) => { const { d } = rows.get(c.id); d.hidden = filter === 'weak' ? !(c.applicable && c.score != null && c.score <= 6) : filter === 'strong' ? !(c.applicable && c.score != null && c.score >= 8) : false; }); };
  const ctl = el('div', 'seg-ctl', null, { role: 'group', 'aria-label': 'فیلتر معیارها' });
  [['all', 'همه (' + fa.format(crits.length) + ')'], ['weak', 'نیازمند بهبود (' + fa.format(weak.length) + ')'], ['strong', 'نقاط قوت (' + fa.format(strong.length) + ')']].forEach(([k, t]) => { const b = el('button', null, t, { 'aria-pressed': k === 'all' }); b.onclick = () => { filter = k; ctl.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', x === b)); applyFilter(); }; ctl.append(b); });
  const openRow = (c) => { filter = 'all'; ctl.querySelectorAll('button').forEach((x, i) => x.setAttribute('aria-pressed', i === 0)); applyFilter(); const { d, hb } = rows.get(c.id); d.classList.add('open'); hb.setAttribute('aria-expanded', 'true'); d.scrollIntoView({ block: 'center', behavior: reduceMotion ? 'auto' : 'smooth' }); };
  const hl = el('div', 'hl');
  if (applicable.length) {
    const lo = applicable.reduce((m, c) => (c.score < m.score ? c : m)), hi = applicable.reduce((m, c) => (c.score > m.score ? c : m));
    const mk = (label, c) => { const b = el('button'); b.append(document.createTextNode(label + ': ' + c.name + ' '), el('b', null, fa1.format(c.score))); b.onclick = () => openRow(c); return b; };
    hl.append(mk('ضعیف‌ترین', lo), mk('قوی‌ترین', hi));
  }
  v.append(secHead('analysis', 'ارزیابی معیارها'), hl, ctl, list);

  /* قوت و ضعف */
  const sp = r.seller_performance || {};
  if ((sp.strengths || []).length || (sp.weaknesses || []).length) {
    const two = el('div', 'two');
    const col = (title, items, cls, ic) => { const c = el('div'); c.append(el('div', 'sub-h', title)); const ul = el('ul', 'pts ' + cls); items.forEach((t) => { const li = el('li'); li.append(icon(ic), el('span', null, t)); ul.append(li); }); c.append(ul); return c; };
    if ((sp.strengths || []).length) two.append(col('نقاط قوت', sp.strengths, 'good', 'check'));
    if ((sp.weaknesses || []).length) two.append(col('نقاط قابل بهبود', sp.weaknesses, 'bad', 'flag'));
    v.append(secHead('user', 'عملکرد فروشنده'), two);
  }
  if ((sp.compliance_flags || []).length) {
    const l = el('div', 'panel'); sp.compliance_flags.forEach((f) => { const it = el('div', 'item'); const g = el('div', 'grow'); g.append(el('span', 'nm', f.type), el('span', 'sb', f.quote || '')); it.append(icon('alert'), g, el('span', 'chip warm', { high: 'مهم', medium: 'متوسط', low: 'جزئی' }[f.severity] || f.severity)); l.append(it); });
    v.append(secHead('alert', 'موارد انطباق'), l);
  }

  /* کوچینگ */
  const co = r.coaching || {};
  if ((co.top_3_improvements || []).length) {
    const ol = el('ol', 'coach panel'); co.top_3_improvements.forEach((t) => ol.append(el('li', null, t)));
    const cb = el('button', 'link', 'کپی برای ارسال به فروشنده'); cb.onclick = () => copy(co.top_3_improvements.map((t, i) => `${fa.format(i + 1)}. ${t}`).join('\n'), 'نکات کوچینگ کپی شد');
    v.append(secHead('flag', 'سه پیشنهاد اولویت‌دار', cb), ol);
  }

  /* اطلاعات لید */
  const li = Object.entries(r.lead_info || {}); const known = li.filter(([, x]) => !(x == null || x === '' || (Array.isArray(x) && !x.length))), unknown = li.filter(([k]) => !known.some(([kk]) => kk === k));
  if (li.length) {
    const dl = el('dl', 'dl panel'); let showUnk = false;
    const draw = () => { dl.replaceChildren(); [...known, ...(showUnk ? unknown : [])].forEach(([k, x]) => { const rw = el('div', known.some(([kk]) => kk === k) ? '' : 'unk'); rw.append(el('dt', null, leadLabel(k)), el('dd', null, x == null || x === '' || (Array.isArray(x) && !x.length) ? 'نامشخص' : Array.isArray(x) ? x.join('، ') : String(x))); dl.append(rw); }); if (!known.length && !showUnk) dl.append(el('div', 'note', 'هنوز چیزی درباره‌ی مشتری مشخص نشده است.', { style: 'padding:12px 16px' })); };
    draw();
    const tg = unknown.length ? el('button', 'link', 'نمایش ' + fa.format(unknown.length) + ' فیلد نامشخص') : null;
    if (tg) tg.onclick = () => { showUnk = !showUnk; tg.textContent = showUnk ? 'پنهان‌کردن فیلدهای نامشخص' : 'نمایش ' + fa.format(unknown.length) + ' فیلد نامشخص'; draw(); };
    v.append(secHead('list', 'اطلاعات مشتری', tg), dl);
  }

  /* ترنسکریپت */
  if (tr && tr.segments.length) {
    const box = el('div', 'panel tr-wrap'); box.hidden = true; trBox = box;
    if (audio) box.append(audio);
    const bw = el('div', 'bubbles');
    tr.segments.forEach((s) => { if (CALive.isSpecial(s)) { const n = LiveView.sysNote(s); if (s.speaker === 'ivr') n.body.append(el('p', 'ln', s.text)); bubbles.push({ t: s.start, e: n.row }); bw.append(n.row); return; } const b = el('button', 'b ' + (s.speaker === seller || !s.speaker ? 's' : 'c')); b.append(el('small', null, mmss(s.start) + (s.speaker === seller ? ' فروشنده' : s.speaker ? ' مشتری' : '')), document.createTextNode(s.text)); b.onclick = () => jump(s.start); bubbles.push({ t: s.start, e: b }); bw.append(b); });
    box.append(bw);
    const tg = el('button', 'link', 'نمایش ترنسکریپت'); trOpen = (open) => { box.hidden = !open; tg.textContent = open ? 'پنهان‌کردن' : 'نمایش ترنسکریپت'; };
    tg.onclick = () => trOpen(box.hidden);
    v.append(secHead('chat', 'ترنسکریپت (' + fa.format(tr.segments.length) + ' بخش)', tg), box);
  }

  /* ابزارها */
  const act = el('div', 'btns');
  const mkBtn = (ic, text, fn) => { const b = el('button', 'btn sm'); b.append(icon(ic), document.createTextNode(text)); b.onclick = fn; return b; };
  act.append(
    mkBtn('refresh', 'تحلیل مجدد', () => api(`/api/v1/analyses/${a.id}/reanalyze`, { method: 'POST' }).then(() => { toast('تحلیل مجدد شروع شد'); load(a.unique_id); })),
    mkBtn('swap', 'جابه‌جایی نقش‌ها', () => { const other = (a.transcript.segments.find((s) => s.speaker && s.speaker !== seller) || {}).speaker; api(`/api/v1/analyses/${a.id}/reanalyze`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ seller_speaker: other }) }).then(() => { toast('با نقش‌های جابه‌جاشده تحلیل می‌شود'); load(a.unique_id); }); }),
    mkBtn('download', 'دریافت JSON', () => { const u = URL.createObjectURL(new Blob([JSON.stringify(r, null, 2)], { type: 'application/json' })); const l = el('a'); l.href = u; l.download = `analysis-${a.id}.json`; l.click(); URL.revokeObjectURL(u); }));
  v.append(secHead('settings', 'ابزارها'), act, el('p', 'fine', 'این ارزیابی را هوش مصنوعی انجام داده است. آن را کمک‌ابزاری برای کوچینگ ببینید، نه مبنای تنها برای تصمیم‌های منابع انسانی. مدیر می‌تواند هر امتیاز را بازبینی کند.'));
}

async function load(uid) {
  if (LiveView.isShowing(uid)) return; // نمای زنده همین تماس در حال اجراست
  clearTimeout(timer); LiveView.stop();
  $('#view').replaceChildren(skeleton());
  const r = await api('/api/v1/analyses/by-unique-id/' + encodeURIComponent(uid));
  if (r.error) {
    if (r.code === 'not_found') { // هنوز روی سرور نیست؛ اگر کار فعالی در افزونه دارد، نمای زنده
      const { jobs } = await call('GET_JOBS'); const j = (jobs || {})[uid];
      if (j && ['queued', 'downloading', 'uploading', 'processing'].includes(j.state) && tab === 'analysis') { LiveView.show({ uid, number: j.meta && j.meta.dst, sub: jobSub(j.meta), jobState: j.state }); return; }
    }
    $('#view').replaceChildren(errState('دریافت نتیجه ممکن نشد', r, () => load(uid))); return;
  }
  let cur = r.data; const full = await api('/api/v1/analyses/' + cur.id); if (full.data) cur = full.data;
  if (tab !== 'analysis') return;
  if (!['done', 'failed'].includes(cur.status)) { LiveView.show({ uid, aid: cur.id, number: cur.dst_masked, sub: sellerName(cur) + (cur.call_datetime ? ' · ' + dateFa(cur.call_datetime) : ''), status: cur.status }); return; }
  let audio = null;
  if (cur.audio_path) {
    audio = el('audio', null, null, { controls: '' });
    const cfg = await chrome.storage.local.get(['backendUrl', 'token']);
    fetch(cfg.backendUrl.replace(/\/$/, '') + '/api/v1/analyses/' + cur.id + '/audio', { headers: { Authorization: 'Bearer ' + cfg.token } })
      .then((x) => (x.ok ? x.blob() : null)).then((b) => { if (b) audio.src = URL.createObjectURL(b); }).catch(() => {});
  }
  if (tab !== 'analysis') return;
  viewKind = 'report'; renderAnalysis(cur, audio);
}
const jobSub = (m) => (m ? ((m.extension && (SELLERS[m.extension] || 'داخلی ' + m.extension)) || '') + (m.date ? ' · ' + m.date + (m.time ? ' ' + m.time : '') : '') : '');

/* ---------- صف ---------- */
async function renderQueue() {
  const v = $('#view'); v.replaceChildren(); const { jobs } = await call('GET_JOBS');
  const items = Object.entries(jobs || {}).sort((a, b) => b[1].updatedAt - a[1].updatedAt);
  const live = (j) => ['queued', 'downloading', 'uploading', 'processing'].includes(j.state);
  updateBadge(items.filter(([, j]) => live(j)).length);
  if (!items.length) { v.append(empty('queue', 'صف خالی است', 'در صفحه‌ی مکالمات پنل، چند تماس را انتخاب کنید و «تحلیل» را بزنید.')); return; }
  const errCount = items.filter(([, j]) => j.state === 'error').length, doneCount = items.filter(([, j]) => j.state === 'done' || j.state === 'cancelled').length;
  if (errCount || doneCount) {
    const bar = el('div', 'btns');
    if (errCount) { const b = el('button', 'btn sm'); b.append(icon('refresh'), document.createTextNode(`تلاش مجدد خطاها (${fa.format(errCount)})`)); b.onclick = () => call('RETRY_ALL').then(() => toast('خطاها دوباره به صف رفتند')); bar.append(b); }
    if (doneCount) { const b = el('button', 'btn sm', `پاک‌کردن تمام‌شده‌ها (${fa.format(doneCount)})`); b.onclick = () => call('CLEAR_FINISHED').then(() => renderQueue()); bar.append(b); }
    v.append(bar);
  }
  const group = (title, arr) => {
    if (!arr.length) return; v.append(secHead('queue', title)); const l = el('div', 'list');
    arr.forEach(([uid, j]) => {
      const it = el('div', 'item'); it.style.alignItems = 'flex-start'; const g = el('div', 'grow');
      const stateText = { queued: 'در صف انتظار', downloading: 'در حال دانلود از پنل', uploading: 'در حال ارسال به سرور', processing: 'در حال پردازش', done: 'انجام شد', error: j.error || 'خطا', cancelled: 'لغو شد' }[j.state] || j.state;
      const top = el('div', 'nm'); top.append(el('span', 'ltr', j.meta?.dst || uid)); g.append(top, el('span', 'sb' + (j.state === 'error' ? ' err' : ''), stateText));
      if (live(j)) { const idx = { queued: -1, downloading: 0, uploading: 1, processing: { preprocessing: 2, transcribing: 3, analyzing: 4 }[j.serverStatus] ?? 2 }[j.state]; const st = el('div', 'steps', null, { role: 'progressbar', 'aria-valuemin': 0, 'aria-valuemax': 5, 'aria-valuenow': Math.max(0, idx), 'aria-label': 'مرحله‌ی پردازش' }); STEPS.forEach((s, i) => { const d = el('div', i < idx ? 'on' : i === idx ? 'cur' : ''); d.append(el('i'), document.createTextNode(s)); st.append(d); }); g.append(st); }
      it.append(g);
      const mkb = (t, fn, cls) => { const b = el('button', 'btn sm ' + (cls || ''), t); b.onclick = fn; return b; };
      if (j.state === 'done') it.append(mkb('مشاهده', () => { chrome.storage.local.set({ focusUid: uid }); setTab('analysis'); }, 'primary'));
      else if (j.state === 'error') it.append(mkb('تلاش دوباره', () => call('RETRY', { uniqueId: uid })));
      else if (live(j)) { it.append(mkb('مشاهده‌ی زنده', () => { chrome.storage.local.set({ focusUid: uid }).then(() => setTab('analysis')); }, 'primary'), mkb('لغو', () => call('CANCEL', { uniqueId: uid }))); }
      l.append(it);
    }); v.append(l);
  };
  group('در حال انجام', items.filter(([, j]) => live(j)));
  group('تمام‌شده و خطادار', items.filter(([, j]) => !live(j)));
}
function updateBadge(n) { const b = document.querySelector('#tab-queue .badge'); if (b) { b.hidden = !n; b.textContent = fa.format(n); } }

/* ---------- تاریخچه ---------- */
async function renderHistory() {
  const v = $('#view'); v.replaceChildren(skeleton());
  const r = await api('/api/v1/analyses?limit=100&status=done'); v.replaceChildren();
  if (r.error) { v.append(errState('دریافت تاریخچه ممکن نشد', r, renderHistory)); return; }
  const all = r.data.items;
  if (!all.length) { v.append(empty('history', 'هنوز تحلیلی ندارید', 'بعد از تحلیل اولین تماس، اینجا فهرست می‌شود.')); return; }
  const tools = el('div', 'tools'); const fld = el('label', 'field'); const inp = el('input', null, null, { type: 'search', placeholder: 'شماره یا فروشنده', 'aria-label': 'جستجو' }); fld.append(icon('search'), inp);
  const sel = el('select', 'sel', null, { 'aria-label': 'مرتب‌سازی' }); [['new', 'تازه‌ترین'], ['hi', 'بالاترین امتیاز'], ['lo', 'پایین‌ترین امتیاز']].forEach(([k, t]) => sel.append(Object.assign(el('option', null, t), { value: k })));
  tools.append(fld, sel);
  const holder = el('div'); let shown = all;
  const exp = el('button', 'link', null); exp.append(icon('download'), document.createTextNode(' خروجی CSV')); exp.style.justifySelf = 'start';
  exp.onclick = () => {
    const rowsCsv = shown.map((a) => [a.call_datetime, sellerName(a), a.seller_ext || '', a.dst_masked || '', a.overall_score != null ? Math.round(a.overall_score) : '', a.grade || '', STAGE[a.customer_stage] || a.customer_stage || '', a.unique_id]);
    const csv = CACsv.toCsv(['تاریخ تماس', 'فروشنده', 'داخلی', 'شماره (ماسک‌شده)', 'امتیاز', 'درجه', 'وضعیت مشتری', 'شناسه'], rowsCsv);
    const u = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' })); const l = el('a'); l.href = u; l.download = 'call-analyses.csv'; l.click(); URL.revokeObjectURL(u); toast('فایل CSV ساخته شد');
  };
  v.append(tools, holder, exp);
  const draw = () => {
    const q = inp.value.trim(); let rows = all.filter((a) => !q || (a.dst_masked || '').includes(q) || sellerName(a).includes(q));
    rows = [...rows].sort((a, b) => sel.value === 'hi' ? (b.overall_score ?? -1) - (a.overall_score ?? -1) : sel.value === 'lo' ? (a.overall_score ?? 101) - (b.overall_score ?? 101) : 0);
    holder.replaceChildren(); shown = rows; exp.hidden = !rows.length;
    if (!rows.length) { holder.append(empty('search', 'موردی پیدا نشد', 'عبارت دیگری را جستجو کنید.')); return; }
    const l = el('div', 'list');
    rows.forEach((a) => {
      const b = el('button', 'item'); b.append(a.grade ? el('span', 'mini s-' + a.grade, a.grade) : el('span', 'mini none', '؟'));
      const g = el('div', 'grow'); g.append(el('span', 'nm', sellerName(a)));
      const sub = el('span', 'sb'); sub.append(el('span', 'ltr', a.dst_masked || ''), document.createTextNode('  ' + dateFa(a.call_datetime))); g.append(sub);
      if (a.customer_stage) g.append(el('span', 'chip brand', STAGE[a.customer_stage] || a.customer_stage));
      b.append(g, el('span', 'num', a.overall_score != null ? fa.format(Math.round(a.overall_score)) : '—'));
      b.onclick = () => { chrome.storage.local.set({ focusUid: a.unique_id }); setTab('analysis'); }; l.append(b);
    }); holder.append(l);
  };
  inp.oninput = draw; sel.onchange = draw; draw();
}

/* ---------- مقایسه ---------- */
async function renderCompare() {
  const v = $('#view'); v.replaceChildren(skeleton());
  const r = await api('/api/v1/sellers/stats'); v.replaceChildren();
  if (r.error) { v.append(errState('دریافت آمار ممکن نشد', r, renderCompare)); return; }
  if (!r.data.length) { v.append(empty('compare', 'هنوز داده‌ی کافی نیست', 'بعد از تحلیل چند تماس، رتبه‌بندی فروشنده‌ها اینجا می‌آید.')); return; }
  v.append(secHead('compare', 'میانگین امتیاز فروشنده‌ها')); const l = el('div', 'list');
  r.data.forEach((s, i) => {
    const row = el('div', 'bar-row'); row.append(el('span', 'rk', ['🥇', '🥈', '🥉'][i] || fa.format(i + 1)));
    const g = el('div'); g.append(el('div', 'nm', sellerName(s)), el('div', 'sb', fa.format(s.calls) + ' تماس تحلیل‌شده', { style: 'font-size:12.5px;color:var(--text-2)' }));
    const bt = el('div', 'bt'), f = el('i'); bt.append(f); g.append(bt); requestAnimationFrame(() => requestAnimationFrame(() => { f.style.width = Math.round(s.avg_score) + '%'; }));
    row.append(g, el('span', 'num', fa.format(Math.round(s.avg_score)))); l.append(row);
  });
  v.append(l, el('p', 'fine', 'میانگین امتیازِ همه‌ی تماس‌های تحلیل‌شده‌ی هر فروشنده. برای نتیجه‌ی قابل‌اتکا، دست‌کم چند تماس لازم است.'));
}

/* ---------- ناوبری ---------- */
const TABS = [['analysis', 'تحلیل', 'analysis'], ['queue', 'صف', 'queue'], ['history', 'تاریخچه', 'history'], ['compare', 'مقایسه', 'compare']];
function buildNav() {
  const nav = $('nav.tabs');
  TABS.forEach(([k, t, ic]) => { const b = el('button', null, null, { role: 'tab', id: 'tab-' + k, 'data-tab': k, 'aria-selected': k === 'analysis' }); const p = el('span', 'pill'); p.append(icon(ic)); b.append(p, el('span', null, t)); if (k === 'queue') { const bd = el('span', 'badge'); bd.hidden = true; b.append(bd); } b.onclick = () => setTab(k); nav.append(b); });
}
function setTab(t) {
  tab = t; clearTimeout(timer); LiveView.stop(); window.scrollTo(0, 0);
  document.querySelectorAll('nav.tabs [role=tab]').forEach((b) => b.setAttribute('aria-selected', b.dataset.tab === t));
  ({ analysis: async () => { const { focusUid, backendUrl, token } = await chrome.storage.local.get(['focusUid', 'backendUrl', 'token']); if (!backendUrl || !token) { $('#view').replaceChildren(empty('settings', 'اول اتصال را تنظیم کنید', 'آدرس سرور تحلیل و توکن دسترسی را در تنظیمات وارد کنید. بعد از آن، تماس‌ها را در صفحه‌ی پنل انتخاب و تحلیل کنید.', { label: 'باز کردن تنظیمات', fn: () => chrome.runtime.openOptionsPage() })); return; } focusUid ? load(focusUid) : (viewKind = 'empty', $('#view').replaceChildren(empty('analysis', 'هنوز تماسی انتخاب نشده', 'در صفحه‌ی پنل روی امتیاز یک تماس بزنید، یا از تاریخچه یکی را باز کنید.', { label: 'رفتن به تاریخچه', fn: () => setTab('history') }))); }, queue: renderQueue, history: renderHistory, compare: renderCompare }[t])();
}

/** اگر پنل «خالی» است و کاری وارد پردازش شد، خودکار نمای زنده‌اش را باز کن (بدون ربودن گزارشی که کاربر می‌خواند). */
function followNewJob(jobs) {
  if (tab !== 'analysis' || viewKind !== 'empty') return;
  const j = Object.entries(jobs).filter(([, x]) => ['downloading', 'uploading', 'processing'].includes(x.state)).sort((a, b) => b[1].updatedAt - a[1].updatedAt)[0];
  if (j) chrome.storage.local.set({ focusUid: j[0] });
}

/* ---------- راه‌اندازی ---------- */
$('#logo').append(icon('logo', 'fill'));
$('#settings').append(icon('settings')); $('#theme').append(icon('theme'));
$('#settings').onclick = () => chrome.runtime.openOptionsPage();
const THEME_FA = { auto: 'خودکار', light: 'روشن', dark: 'تیره' };
$('#theme').onclick = async () => { const { theme = 'auto' } = await chrome.storage.local.get('theme'); const n = { auto: 'light', light: 'dark', dark: 'auto' }[theme] || 'auto'; applyTheme(n); await chrome.storage.local.set({ theme: n }); toast('تم: ' + THEME_FA[n]); };
chrome.storage.local.get(['theme', 'sellersText']).then((s) => { applyTheme(s.theme || 'auto'); SELLERS = CASettings.parseSellers(s.sellersText); });
chrome.storage.onChanged.addListener((ch) => {
  if (ch.theme) applyTheme(ch.theme.newValue); if (ch.sellersText) SELLERS = CASettings.parseSellers(ch.sellersText.newValue);
  if (ch.focusUid && tab === 'analysis') load(ch.focusUid.newValue); if (ch.jobs) { followNewJob(ch.jobs.newValue || {}); if (tab === 'queue') renderQueue(); else updateBadge(Object.values(ch.jobs.newValue || {}).filter((j) => ['queued', 'downloading', 'uploading', 'processing'].includes(j.state)).length); }
});
(async () => {
  const r = await api('/health'); const c = $('#conn');
  if (r.error) { c.className = 'conn bad'; c.lastChild.textContent = r.code === 'no_config' ? 'تنظیم نشده' : r.code === 'auth' ? 'توکن نادرست' : 'قطع'; c.title = r.error + ' (برای باز کردن تنظیمات بزنید)'; c.style.cursor = 'pointer'; c.onclick = () => chrome.runtime.openOptionsPage(); }
  else { c.className = 'conn ok'; c.lastChild.textContent = 'متصل'; }
})();
buildNav(); setTab('analysis');
