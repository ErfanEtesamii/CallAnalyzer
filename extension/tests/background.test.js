// اجرای واقعی service worker با chrome و fetch ساختگی
const test = require('node:test');
const assert = require('node:assert');

let skew = 0; const realNow = Date.now; Date.now = () => realNow() + skew;
const realST = setTimeout; globalThis.setTimeout = (fn, ms, ...a) => realST(fn, ms >= 2000 ? 10 : ms, ...a);
globalThis.self = globalThis;

const store = {}; const badges = []; let handler = null;
const clone = (o) => JSON.parse(JSON.stringify(o));
globalThis.chrome = {
  storage: { local: {
    get: async (keys) => { const ks = Array.isArray(keys) ? keys : [keys]; const o = {}; ks.forEach((k) => { if (k in store) o[k] = clone(store[k]); }); return o; },
    set: async (o) => { Object.assign(store, clone(o)); },
  } },
  action: { setBadgeText: ({ text }) => badges.push(text), setBadgeBackgroundColor() {} },
  alarms: { create() {}, onAlarm: { addListener() {} } },
  runtime: { onStartup: { addListener() {} }, onInstalled: { addListener() {} }, onMessage: { addListener: (fn) => { handler = fn; } } },
  sidePanel: { setPanelBehavior() {}, open: async () => {} },
};
const send = (msg) => new Promise((res) => handler(msg, { tab: { id: 1 } }, res));

// ---- شبکه‌ی ساختگی ----
const net = { panel: 'ok', uploadFail: 0, hang: new Set(), inDl: 0, maxDl: 0, uploads: [], nextId: 1, existing: new Set() };
const wav = () => { const b = new Uint8Array(4000); b.set([82, 73, 70, 70], 0); b.set([87, 65, 86, 69], 8); return b.buffer; };
globalThis.fetch = async (url, opts = {}) => {
  url = String(url);
  if (url.startsWith('https://panel/')) {
    net.inDl++; net.maxDl = Math.max(net.maxDl, net.inDl);
    try {
      const id = new URL(url).searchParams.get('id');
      if (net.hang.has(id)) await new Promise((_, rej) => opts.signal.addEventListener('abort', () => rej(Object.assign(new Error('aborted'), { name: 'AbortError' }))));
      await new Promise((r) => realST(r, 5));
      if (net.panel === 'expired') return new Response('<html>login</html>', { status: 200 });
      return new Response(wav(), { status: 200 });
    } finally { net.inDl--; }
  }
  const u = new URL(url), p = u.pathname;
  const json = (o, status = 200) => new Response(JSON.stringify(o), { status, headers: { 'Content-Type': 'application/json' } });
  if (p.startsWith('/api/v1/analyses/by-unique-id/')) return net.existing.has(decodeURIComponent(p.split('/').pop())) ? json({ id: 99, status: 'done', overall_score: 80, grade: 'B' }) : json({ detail: 'x' }, 404);
  if (p === '/api/v1/analyses/batch-status') { const ids = JSON.parse(opts.body).unique_ids; return json(Object.fromEntries(ids.map((i) => [i, { status: 'done', overall_score: 70, grade: 'B' }]))); }
  if (p === '/api/v1/analyses' && opts.method === 'POST') {
    if (net.uploadFail > 0) { net.uploadFail--; throw new TypeError('network down'); }
    const fd = opts.body; net.uploads.push(fd.get('unique_id') + '|' + fd.get('seller_ext') + '|' + fd.get('talk_seconds'));
    return json({ id: net.nextId++, status: 'queued' });
  }
  return json({}, 404);
};
const row = (u, extra = {}) => ({ uniqueId: u, downloadUrl: 'https://panel/dl?id=' + u, namefile: u + '.wav', date: 'd', time: 't', src: 's', dst: '0912', durationText: '00:01:00', durationSec: 60, extension: '14', direction: 'out', talkSec: 55, ...extra });
const waitFor = async (fn, ms = 6000) => { const t0 = realNow(); for (;;) { const v = await fn(); if (v) return v; if (realNow() - t0 > ms) throw new Error('timeout waiting'); await new Promise((r) => realST(r, 15)); } };
const jobs = () => store.jobs || {};
const settle = () => waitFor(() => Object.values(jobs()).every((j) => !['queued', 'downloading', 'uploading', 'processing'].includes(j.state)));

test('بارگذاری و تنظیمات', async () => {
  Object.assign(store, { backendUrl: 'https://api.local', token: 'tok', pollSeconds: 2, concurrency: 2, jobs: {} });
  await import('../src/background.js');
  assert.ok(handler);
});

test('جریان کامل + فرستادن داخلی و مدت واقعی + dedupe', async () => {
  let r = await send({ type: 'ENQUEUE', rows: [row('a'), row('b')] });
  assert.deepStrictEqual([r.added, r.skipped], [2, 0]);
  r = await send({ type: 'ENQUEUE', rows: [row('a')] }); // هنوز فعال است
  assert.strictEqual(r.skipped, 1);
  await settle();
  assert.deepStrictEqual([jobs().a.state, jobs().b.state], ['done', 'done']);
  assert.strictEqual(jobs().a.score, 70);
  assert.ok(net.uploads.includes('a|14|55'));
  assert.strictEqual(net.uploads.filter((x) => x.startsWith('a|')).length, 1);
  assert.strictEqual(badges.at(-1), '');
});

test('تحلیل‌شده‌ی قبلی دانلود نمی‌شود', async () => {
  net.existing.add('old'); const before = net.uploads.length;
  await send({ type: 'ENQUEUE', rows: [row('old')] }); await settle();
  assert.strictEqual(jobs().old.state, 'done'); assert.strictEqual(net.uploads.length, before);
});

test('شکست شبکه ← تلاش مجدد خودکار با backoff ← موفق', async () => {
  net.uploadFail = 1;
  await send({ type: 'ENQUEUE', rows: [row('n1')] });
  await waitFor(() => jobs().n1 && jobs().n1.attempts === 1 && jobs().n1.state === 'queued');
  assert.match(jobs().n1.error, /تلاش مجدد خودکار/);
  skew += 10000; // گذر زمانِ backoff
  await settle();
  assert.strictEqual(jobs().n1.state, 'done');
});

test('نشست منقضی ← خطای قطعی و بدون تکرار؛ بعد RETRY دستی', async () => {
  net.panel = 'expired';
  await send({ type: 'ENQUEUE', rows: [row('s1')] }); await settle();
  assert.deepStrictEqual([jobs().s1.state, jobs().s1.errorCode, jobs().s1.attempts], ['error', 'session_expired', 0]);
  assert.strictEqual(badges.at(-1), '!');
  net.panel = 'ok';
  await send({ type: 'RETRY', uniqueId: 's1' }); await settle();
  assert.strictEqual(jobs().s1.state, 'done');
});

test('لغو در میانه‌ی دانلود', async () => {
  net.hang.add('h1');
  await send({ type: 'ENQUEUE', rows: [row('h1')] });
  await waitFor(() => net.inDl === 1);
  await send({ type: 'CANCEL', uniqueId: 'h1' });
  await waitFor(() => net.inDl === 0);
  assert.strictEqual(jobs().h1.state, 'cancelled');
  await new Promise((r) => realST(r, 100));
  assert.strictEqual(jobs().h1.state, 'cancelled'); // دوباره اجرا نشد
  assert.ok(!net.uploads.some((x) => x.startsWith('h1|')));
});

test('کار یتیم بعد از خواب service worker بازیابی می‌شود', async () => {
  store.jobs = { ...store.jobs, orphan: { meta: row('orphan'), state: 'downloading', attempts: 0, createdAt: 1, updatedAt: 1 } };
  await send({ type: 'ENQUEUE', rows: [row('x1')] }); await settle();
  assert.strictEqual(jobs().orphan.state, 'done');
});

test('هم‌زمانی از سقف تنظیم‌شده بیشتر نمی‌شود', async () => {
  store.concurrency = 1; net.maxDl = 0;
  await send({ type: 'ENQUEUE', rows: ['c1', 'c2', 'c3', 'c4'].map((u) => row(u)) }); await settle();
  assert.strictEqual(net.maxDl, 1);
  assert.ok(['c1', 'c2', 'c3', 'c4'].every((u) => jobs()[u].state === 'done'));
});

test('تلاش مجدد همه‌ی خطاها', async () => {
  net.panel = 'expired';
  await send({ type: 'ENQUEUE', rows: [row('e1'), row('e2')] }); await settle();
  assert.deepStrictEqual([jobs().e1.state, jobs().e2.state], ['error', 'error']);
  net.panel = 'ok';
  const r = await send({ type: 'RETRY_ALL' });
  assert.strictEqual(r.retried, 2);
  await settle();
  assert.deepStrictEqual([jobs().e1.state, jobs().e2.state], ['done', 'done']);
});

test('پاک‌سازی تمام‌شده‌ها', async () => {
  const r = await send({ type: 'CLEAR_FINISHED' });
  assert.ok(r.cleared >= 5);
  assert.ok(!Object.values(jobs()).some((j) => j.state === 'done'));
});
