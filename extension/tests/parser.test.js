const test = require('node:test');
const assert = require('node:assert');
const P = require('../src/lib/parser.js');

test('ارقام فارسی', () => {
  assert.strictEqual(P.normalizeDigits('۰۰:۰۱:۰۹'), '00:01:09');
  assert.strictEqual(P.hmsToSeconds('۰۰:۰۱:۰۹'), 69);
  assert.strictEqual(P.hmsToSeconds('00:00:00'), 0);
});
test('نام فایل', () => {
  const f = P.parseFilename('out-09198255664-14-20261117-134241-1794910361.189853.wav');
  assert.deepStrictEqual([f.extension, f.uniqueId, f.direction], ['14', '1794910361.189853', 'out']);
  assert.strictEqual(P.parseFilename('../x.wav'), null);
});
test('نگاشت ستون و ردیف', () => {
  const map = P.mapColumns(['UniqueID', 'تاریخ', 'زمان', 'مبدأ', 'مقصد', 'مدت', 'نوع', 'پیام']);
  assert.strictEqual(map.duration, 5);
  const row = P.parseRow(map, ['1794910361.189853', '۱۴۰۵/۰۸/۲۶', '۱۳:۴۲:۴۱', '14', '09198255664', '۰۰:۰۱:۰۹', 'خروجی', ''],
    ['javascript:playaudio(...)', '?menu=monitoring&action=download&id=1794910361.189853&namefile=out-09198255664-14-20261117-134241-1794910361.189853.wav&rawmode=yes'],
    'https://192.168.139.15/index.php?menu=monitoring');
  assert.strictEqual(row.durationSec, 69);
  assert.strictEqual(row.extension, '14');
  assert.ok(row.downloadUrl.startsWith('https://192.168.139.15/index.php?menu=monitoring&action=download'));
  assert.strictEqual(P.ineligibleReason(row, 20), null);
  assert.match(P.ineligibleReason({ ...row, durationSec: 0 }, 20), /کمتر از 20/);
});
test('ترتیب ستون‌ها متفاوت', () => {
  const map = P.mapColumns(['پیام', 'نوع', 'مدت', 'مقصد', 'مبدأ', 'زمان', 'تاریخ', 'UniqueID']);
  assert.strictEqual(map.uniqueId, 7);
});
test('deduplicate', () => {
  const a = { uniqueId: '1.1', namefile: 'a' };
  assert.strictEqual(P.dedupe([a, { ...a }, { uniqueId: '1.2', namefile: 'a' }]).length, 2);
});

// --- فیکسچر واقعی پنل ---
const fs = require('node:fs');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../fixtures/calls-table.html'), 'utf8');
const strip = (s) => s.replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ').trim();
function readFixture() {
  const heads = [...html.matchAll(/<th[^>]*>([^<]*)<\/th>/g)].map((m) => strip(m[1]));
  const body = html.slice(html.indexOf('<tbody>'));
  const rows = [...body.matchAll(/<tr[^>]*>(.*?)<\/tr>/gs)].map((m) => {
    const cells = [...m[1].matchAll(/<td[^>]*>(.*?)<\/td>/gs)].map((c) => strip(c[1]));
    const links = [...m[1].matchAll(/href="([^"]*)"/g)].map((l) => l[1].replace(/&amp;/g, '&'));
    return { cells, links };
  });
  return { heads, rows };
}
test('فیکسچر واقعی: ستون‌ها و ردیف‌ها', () => {
  const { heads, rows } = readFixture();
  const map = P.mapColumns(heads);
  assert.deepStrictEqual(map, { uniqueId: 0, date: 1, time: 2, src: 3, dst: 4, duration: 5, type: 6, message: 7 });
  assert.strictEqual(rows.length, 10);
  const parsed = rows.map((r) => P.parseRow(map, r.cells, r.links, 'https://192.168.139.15/index.php?menu=monitoring'));
  assert.ok(parsed.every(Boolean));
  assert.ok(parsed.every((r) => r.extension === '14' && r.direction === 'out'));
  assert.ok(parsed.every((r) => r.downloadUrl.includes('action=download')));
  assert.deepStrictEqual(parsed.map((r) => r.durationSec), [23, 0, 49, 0, 69, 149, 9, 48, 76, 114]);
  assert.strictEqual(parsed[0].dst, '09198255664');
  // ردیف تکراری ۰ ثانیه‌ای نباید ردیف ۲۳ ثانیه‌ای را بپوشاند
  const best = P.dedupe(parsed);
  assert.strictEqual(best.length, 8);
  assert.strictEqual(best.find((r) => r.uniqueId === '1794910361.189853').durationSec, 23);
  // با آستانه‌ی ۲۰ ثانیه: قابل‌تحلیل = ۲۳،۴۹،۶۹،۱۴۹،۴۸،۷۶،۱۱۴
  assert.strictEqual(best.filter((r) => !P.ineligibleReason(r, 20)).length, 7);
});

// --- CDR (ریز مکالمات) ---
function readCdr() {
  const h = fs.readFileSync(path.join(__dirname, '../fixtures/cdr-tbody.html'), 'utf8');
  return [...h.matchAll(/<tr[^>]*>(.*?)<\/tr>/gs)].map((m) => P.parseCdrRow([...m[1].matchAll(/<td[^>]*>(.*?)<\/td>/gs)].map((c) => strip(c[1]))));
}
test('CDR: مدت‌ها', () => {
  assert.strictEqual(P.cdrDurationToSeconds('2m 17s'), 137);
  assert.strictEqual(P.cdrDurationToSeconds('58s'), 58);
  assert.strictEqual(P.cdrDurationToSeconds('6m 30s'), 390);
  assert.strictEqual(P.cdrDurationToSeconds('0s'), 0);
  assert.strictEqual(P.cdrDurationToSeconds('abc'), null);
});
test('CDR: ردیف‌ها و ادغام پاها', () => {
  const rows = readCdr();
  assert.ok(rows.length > 80 && rows.every(Boolean));
  const m = P.mergeCdr(rows);
  // تماس ۶۹ ثانیه‌ای صفحه‌ی ضبط ← ۵۸ ثانیه در CDR، داخلی ۱۴
  assert.deepStrictEqual([m['1794910108.189779'].talkSec, m['1794910108.189779'].extension, m['1794910108.189779'].disposition], [58, '14', 'answered']);
  assert.strictEqual(m['1794909390.189574'].talkSec, 89);
  assert.strictEqual(m['1794910361.189853'].disposition, 'busy');
  // تماس‌های داخلی ۳۳↔۴۴
  assert.strictEqual(m['1794916786.191139'].internal, true);
  assert.strictEqual(m['1794916325.191045'].internal, false);
  // داخلی ۳۳ هم فروشنده است
  assert.strictEqual(m['1794916325.191045'].extension, '33');
  // دو پا: یکی ۲ ثانیه پاسخ داده‌شده، دیگری پاسخ داده نشده ← پاسخ‌داده‌شده برنده است
  assert.strictEqual(m['1794907364.188877'].disposition, 'answered');
});
test('CDR: غیرقابل‌تحلیل بر اساس مدت واقعی و وضعیت', () => {
  const m = P.mergeCdr(readCdr());
  const rec = { downloadUrl: 'x', durationSec: 69 };
  assert.strictEqual(P.ineligibleReason(rec, 20, m['1794910108.189779']), null);
  assert.match(P.ineligibleReason(rec, 20, m['1794910361.189853']), /پاسخ داده نشده/);
  assert.match(P.ineligibleReason(rec, 20, m['1794916786.191139']), /داخلی/);
  // مدت پنل ۲۴ ولی مدت واقعی ۱۴ ثانیه
  assert.match(P.ineligibleReason({ downloadUrl: 'x', durationSec: 24 }, 20, { disposition: 'answered', talkSec: 14 }), /کمتر از 20/);
});
