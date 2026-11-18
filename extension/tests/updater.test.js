const test = require('node:test');
const assert = require('node:assert');
const U = require('../src/lib/updater.js');

const T0 = 1_000_000_000;
const mk = (over = {}) => {
  const log = { reloads: 0, saved: null };
  let store = over.state;
  const deps = {
    running: '1.0.1.1', now: () => over.now ?? T0,
    readDiskVersion: async () => { if (over.diskErr) throw new Error('x'); return over.disk ?? '1.0.1.1'; },
    isBusy: async () => !!over.busy,
    reload: async () => { log.reloads++; },
    load: async () => store, save: async (s) => { store = s; log.saved = s; },
    ...(over.server !== undefined ? { fetchServerVersion: async () => { if (over.server instanceof Error) throw over.server; return over.server; } } : {}),
  };
  return { deps, log, get store() { return store; } };
};

test('نسخه‌ی دیسک با نسخه‌ی در حال اجرا یکی است: کاری نمی‌کند', async () => {
  const m = mk(); const r = await U.check(m.deps);
  assert.strictEqual(r.action, 'none'); assert.strictEqual(m.log.reloads, 0);
});
test('نسخه‌ی دیسک عوض شده و کاری فعال نیست: reload', async () => {
  const m = mk({ disk: '1.0.2.2' }); const r = await U.check(m.deps);
  assert.strictEqual(r.action, 'reload'); assert.strictEqual(m.log.reloads, 1);
  assert.strictEqual(m.store.lastReloadAt, T0);
});
test('وسط دانلود/آپلود صبر می‌کند و بعد از MAX_WAIT به هر حال reload می‌کند', async () => {
  let m = mk({ disk: '1.0.2.2', busy: true });
  assert.strictEqual((await U.check(m.deps)).action, 'wait'); assert.strictEqual(m.log.reloads, 0);
  const pending = m.store.pendingSince;
  m = mk({ disk: '1.0.2.2', busy: true, state: { pendingSince: pending }, now: T0 + U.MAX_WAIT_MS + 1 });
  assert.strictEqual((await U.check(m.deps)).action, 'reload');
});
test('محافظ حلقه: دو reload در فاصله‌ی کمتر از MIN_GAP انجام نمی‌شود', async () => {
  const m = mk({ disk: '1.0.2.2', state: { lastReloadAt: T0 - 1000 } });
  assert.strictEqual((await U.check(m.deps)).action, 'wait'); assert.strictEqual(m.log.reloads, 0);
  const m2 = mk({ disk: '1.0.2.2', state: { lastReloadAt: T0 - U.MIN_GAP_MS - 1 } });
  assert.strictEqual((await U.check(m2.deps)).action, 'reload');
});
test('خواندن manifest شکست بخورد: هیچ کاری نمی‌کند (reload بی‌دلیل نه)', async () => {
  const m = mk({ diskErr: true }); const r = await U.check(m.deps);
  assert.strictEqual(r.action, 'none'); assert.strictEqual(m.log.reloads, 0);
});
test('همگام‌ساز عقب‌مانده: سرور نسخه‌ی جدید دارد ولی دیسک عوض نمی‌شود', async () => {
  let m = mk({ server: '1.0.9.9' });
  await U.check(m.deps); assert.strictEqual(m.store.syncStale, false); assert.ok(m.store.behindSince);
  m = mk({ server: '1.0.9.9', state: { behindSince: T0 - U.STALE_MS - 1 }, now: T0 });
  await U.check(m.deps); assert.strictEqual(m.store.syncStale, true);
  m = mk({ server: '1.0.1.1', state: { behindSince: T0 - U.STALE_MS - 1, syncStale: true } });
  await U.check(m.deps); assert.strictEqual(m.store.syncStale, false);
});
test('خطای دسترسی به سرور، بررسی به‌روزرسانی را خراب نمی‌کند', async () => {
  const m = mk({ disk: '1.0.2.2', server: new Error('offline') });
  assert.strictEqual((await U.check(m.deps)).action, 'reload');
});
test('بررسی سرور حداکثر هر ۵ دقیقه', async () => {
  let calls = 0;
  const m = mk({ server: '1.0.1.1' }); const orig = m.deps.fetchServerVersion;
  m.deps.fetchServerVersion = async () => { calls++; return orig(); };
  await U.check(m.deps); await U.check(m.deps); assert.strictEqual(calls, 1);
});
