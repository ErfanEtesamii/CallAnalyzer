const test = require('node:test');
const assert = require('node:assert');
const S = require('../src/lib/settings.js');

test('نرمال‌سازی و محدوده‌ها', () => {
  const s = S.normalize({ minSeconds: 9999, concurrency: 0, pollSeconds: 'x', theme: 'neon', backendUrl: ' https://a.b/ ', autoAnalyze: 1 });
  assert.deepStrictEqual([s.minSeconds, s.concurrency, s.pollSeconds, s.theme, s.backendUrl, s.autoAnalyze], [600, 1, 3, 'auto', 'https://a.b', true]);
  assert.strictEqual(S.normalize().includeInternal, false);
});
test('فهرست داخلی و نگاشت فروشنده', () => {
  assert.deepStrictEqual(S.parseExtList('14، 33, 15  16'), ['14', '33', '15', '16']);
  assert.deepStrictEqual(S.parseSellers('14=علی\n33 = سارا\nخراب\n=x'), { 14: 'علی', 33: 'سارا' });
});
