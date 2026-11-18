const test = require('node:test');
const assert = require('node:assert');
const L = require('../src/lib/livechat.js');

const seg = (i, speaker, start, end = start + 2) => ({ i, speaker, start, end, text: 't' + i });

test('merge: تکراری اضافه نمی‌شود و مرتب می‌ماند', () => {
  const a = L.merge([], [seg(0, 'seller', 0), seg(1, 'customer', 3)]);
  assert.strictEqual(a.added, 2);
  const b = L.merge(a.list, [seg(1, 'customer', 3), seg(2, 'seller', 6)]);
  assert.strictEqual(b.added, 1);
  assert.deepStrictEqual(b.list.map((s) => s.i), [0, 1, 2]);
  assert.strictEqual(L.merge(b.list, []).added, 0);
  assert.strictEqual(L.merge(b.list, null).added, 0);
});

test('groupRuns: نوبت‌های پشت‌سرهم یک گوینده یک دسته می‌شوند و فاصله‌ی زیاد دسته را می‌شکند', () => {
  const r = L.groupRuns([seg(0, 'seller', 0), seg(1, 'seller', 3), seg(2, 'customer', 6), seg(3, 'seller', 9), seg(4, 'seller', 30)]);
  assert.deepStrictEqual(r.map((x) => [x.speaker, x.items.length]), [['seller', 2], ['customer', 1], ['seller', 1], ['seller', 1]]);
});

test('groupRuns: برچسب ناشناخته کارشناس حساب می‌شود (جلوگیری از حباب بی‌طرف)', () => {
  assert.strictEqual(L.groupRuns([{ i: 0, speaker: undefined, start: 0, end: 1, text: 'x' }])[0].speaker, 'seller');
});

test('stageIndex: وضعیت سرور بر وضعیت کار افزونه مقدم است', () => {
  assert.strictEqual(L.stageIndex('transcribing', 'processing'), 3);
  assert.strictEqual(L.stageIndex('analyzing', 'processing'), 4);
  assert.strictEqual(L.stageIndex(null, 'downloading'), 0);
  assert.strictEqual(L.stageIndex(null, 'uploading'), 1);
  assert.strictEqual(L.stageIndex(null, 'queued'), -1);
});

test('nextSide و revealMs', () => {
  assert.strictEqual(L.nextSide([]), 'seller');
  assert.strictEqual(L.nextSide([seg(0, 'seller', 0)]), 'customer');
  assert.strictEqual(L.nextSide([seg(0, 'customer', 0)]), 'seller');
  assert.strictEqual(L.revealMs(5), 250);
  assert.strictEqual(L.revealMs(10000), 1400);
});

test('joinsRun', () => {
  const run = { speaker: 'seller', start: 0, end: 3, items: [] };
  assert.ok(L.joinsRun(run, seg(1, 'seller', 5)));
  assert.ok(!L.joinsRun(run, seg(1, 'customer', 4)));
  assert.ok(!L.joinsRun(run, seg(1, 'seller', 20)));
  assert.ok(!L.joinsRun(null, seg(1, 'seller', 1)));
});
