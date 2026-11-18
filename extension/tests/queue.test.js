const test = require('node:test');
const assert = require('node:assert');
const Q = require('../src/lib/queue.js');
const C = require('../src/lib/csv.js');
const S = require('../src/lib/settings.js');
const row = (u, extra = {}) => ({ uniqueId: u, durationSec: 60, ...extra });

test('addJobs: تکراریِ فعال اضافه نمی‌شود ولی خطادار/تمام‌شده دوباره می‌شود', () => {
  let r = Q.addJobs({}, [row('a'), row('b')], { now: 1 });
  assert.deepStrictEqual([r.added, r.skipped], [2, 0]);
  r = Q.addJobs({ ...r.jobs, a: { ...r.jobs.a, state: 'processing' }, b: { ...r.jobs.b, state: 'error' } }, [row('a'), row('b'), row('c')], { now: 2 });
  assert.deepStrictEqual([r.added, r.skipped], [2, 1]);
  assert.strictEqual(r.jobs.b.state, 'queued');
  assert.strictEqual(r.jobs.b.attempts, 0);
});
test('recoverOrphans', () => {
  const jobs = { a: { state: 'downloading' }, b: { state: 'uploading' }, c: { state: 'processing' }, d: { state: 'queued' } };
  assert.deepStrictEqual(Object.keys(Q.recoverOrphans(jobs, (u) => u === 'b')), ['a']);
});
test('pickRunnable: ترتیب، backoff، لغو و سقف', () => {
  const jobs = { a: { state: 'queued', createdAt: 3 }, b: { state: 'queued', createdAt: 1 }, c: { state: 'queued', createdAt: 2, nextAttemptAt: 999 }, d: { state: 'queued', createdAt: 0, cancelled: true }, e: { state: 'done' } };
  assert.deepStrictEqual(Q.pickRunnable(jobs, 100, 5), ['b', 'a']);
  assert.deepStrictEqual(Q.pickRunnable(jobs, 100, 1), ['b']);
  assert.deepStrictEqual(Q.pickRunnable(jobs, 100, 0), []);
  assert.deepStrictEqual(Q.pickRunnable(jobs, 1000, 5), ['b', 'c', 'a']);
});
test('onFailure: تلاش مجدد برای شبکه، قطعی برای auth و session', () => {
  const net = { code: 'network', userMessage: 'قطع شد' };
  let p = Q.onFailure({ attempts: 0 }, net, 1000);
  assert.deepStrictEqual([p.state, p.attempts, p.nextAttemptAt], ['queued', 1, 6000]);
  p = Q.onFailure({ attempts: 1 }, net, 1000); assert.strictEqual(p.nextAttemptAt, 11000);
  p = Q.onFailure({ attempts: 2 }, net, 1000); assert.strictEqual(p.state, 'error');
  for (const code of ['auth', 'session_expired', 'server_4xx', 'too_large']) assert.strictEqual(Q.onFailure({ attempts: 0 }, { code }, 0).state, 'error', code);
  assert.strictEqual(Q.backoffMs(10), 60000);
});
test('badge و timeout پردازش', () => {
  assert.deepStrictEqual(Q.badge({ a: { state: 'queued' }, b: { state: 'processing' }, c: { state: 'error' } }).text, '2');
  assert.strictEqual(Q.badge({ c: { state: 'error' } }).text, '!');
  assert.strictEqual(Q.badge({ c: { state: 'done' } }).text, '');
  assert.ok(Q.processingTimedOut({ state: 'processing', processingSince: 0 }, 16 * 60000));
  assert.ok(!Q.processingTimedOut({ state: 'processing', processingSince: 0 }, 60000));
});
test('prune: قدیمی‌های تمام‌شده حذف، خطا و فعال می‌ماند، سقف تعداد', () => {
  const day = 864e5, now = 10 * day;
  const jobs = { old: { state: 'done', updatedAt: 0 }, newer: { state: 'done', updatedAt: now - day }, err: { state: 'error', updatedAt: 0 }, act: { state: 'queued', updatedAt: 0 } };
  assert.deepStrictEqual(Object.keys(Q.prune(jobs, now)).sort(), ['act', 'err', 'newer']);
  assert.strictEqual(Object.keys(Q.prune(jobs, now, { maxCount: 1 })).length, 1);
});
test('تخمین دقیقه', () => { assert.strictEqual(Q.totalMinutes([row('a', { talkSec: 90 }), row('b', { durationSec: 150 })]), 4); });

test('CSV: BOM، نقل‌قول، ایمنی فرمول', () => {
  const s = C.toCsv(['الف', 'ب'], [['=1+1', 'a,"b"'], [null, 'x\ny']]);
  assert.ok(s.startsWith('﻿'));
  assert.ok(s.includes("'=1+1"));
  assert.ok(s.includes('"a,""b"""'));
  assert.ok(s.includes('"x\ny"'));
});
test('origin پنل', () => {
  assert.strictEqual(S.normalizeOrigin('https://10.0.0.5/index.php?x=1'), 'https://10.0.0.5');
  assert.strictEqual(S.normalizeOrigin('ftp://x'), null);
  assert.strictEqual(S.normalizeOrigin('خراب'), null);
  assert.strictEqual(S.normalize({ panelOrigin: 'bad' }).panelOrigin, 'https://192.168.139.15');
});
