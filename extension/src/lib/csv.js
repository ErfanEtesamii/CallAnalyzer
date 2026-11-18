/* خروجی CSV سازگار با Excel (BOM) و ایمن در برابر تزریق فرمول. */
(function (root) {
  function cell(v) {
    let s = v == null ? '' : String(v);
    if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
    return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }
  const toCsv = (header, rows) => '﻿' + [header, ...rows].map((r) => r.map(cell).join(',')).join('\r\n');
  const api = { cell, toCsv };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.CACsv = api;
})(typeof self !== 'undefined' ? self : globalThis);
