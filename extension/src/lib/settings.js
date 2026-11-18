/* تنظیمات مشترک: مقادیر پیش‌فرض و توابع کمکی (بدون وابستگی به chrome.*) */
(function (root) {
  const DEFAULTS = {
    backendUrl: '', token: '',
    panelOrigin: 'https://192.168.139.15', // آدرس پنل تلفنی (Issabel)
    minSeconds: 20,            // حداقل مدت واقعی مکالمه
    concurrency: 2,            // تعداد هم‌زمان دانلود/آپلود
    pollSeconds: 3,            // فاصله‌ی بررسی وضعیت پردازش
    includeInternal: false,    // تماس‌های داخلی بین همکاران هم قابل‌تحلیل باشند
    onlyExtensions: '',        // فقط این داخلی‌ها (جداشده با ویرگول)؛ خالی = همه
    autoAnalyze: false,        // تحلیل خودکار تماس‌های واجد شرایط هنگام باز شدن جدول
    autoLimit: 10,             // سقف تحلیل خودکار در هر بار باز شدن صفحه
    confirmBulkOver: 10,       // پرسش تأیید برای انتخاب بیش از این تعداد
    showScoreInPill: true,     // نمایش عدد امتیاز کنار درجه در جدول
    theme: 'auto',             // auto | light | dark
    sellersText: '',           // «داخلی=نام» در هر خط
  };
  const LIMITS = { minSeconds: [0, 600], concurrency: [1, 5], pollSeconds: [2, 30], autoLimit: [1, 100], confirmBulkOver: [1, 500] };
  const clamp = (v, [lo, hi], d) => { const n = Number(v); return Number.isFinite(n) ? Math.min(hi, Math.max(lo, Math.round(n))) : d; };
  function normalize(raw) {
    const s = { ...DEFAULTS, ...(raw || {}) };
    for (const [k, r] of Object.entries(LIMITS)) s[k] = clamp(s[k], r, DEFAULTS[k]);
    for (const k of ['includeInternal', 'autoAnalyze', 'showScoreInPill']) s[k] = !!s[k];
    if (!['auto', 'light', 'dark'].includes(s.theme)) s.theme = 'auto';
    s.backendUrl = String(s.backendUrl || '').trim().replace(/\/$/, '');
    s.token = String(s.token || '').trim();
    s.panelOrigin = normalizeOrigin(s.panelOrigin) || DEFAULTS.panelOrigin;
    return s;
  }
  /** فقط origin معتبر http(s)؛ در غیر این‌صورت null */
  function normalizeOrigin(v) {
    try { const u = new URL(String(v || '').trim()); return (u.protocol === 'https:' || u.protocol === 'http:') && u.hostname ? u.origin : null; } catch { return null; }
  }
  const parseExtList = (t) => String(t || '').split(/[,،\s]+/).map((x) => x.trim()).filter(Boolean);
  function parseSellers(t) {
    const m = {};
    for (const line of String(t || '').split('\n')) {
      const i = line.indexOf('='); if (i < 1) continue;
      const k = line.slice(0, i).trim(), v = line.slice(i + 1).trim();
      if (k && v) m[k] = v;
    }
    return m;
  }
  const api = { DEFAULTS, normalize, normalizeOrigin, parseExtList, parseSellers };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.CASettings = api;
})(typeof self !== 'undefined' ? self : globalThis);
