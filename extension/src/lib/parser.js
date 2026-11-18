/* منطق خالص (بدون DOM) برای تجزیه‌ی جدول مکالمات؛ هم در مرورگر و هم در Node قابل استفاده است. */
(function (root) {
  const FA = '۰۱۲۳۴۵۶۷۸۹', AR = '٠١٢٣٤٥٦٧٨٩';
  function normalizeDigits(s) {
    return String(s ?? '').replace(/[۰-۹٠-٩]/g, (c) => {
      const i = FA.indexOf(c); return String(i >= 0 ? i : AR.indexOf(c));
    });
  }
  function hmsToSeconds(s) {
    const parts = normalizeDigits(s).trim().split(':').map((p) => parseInt(p, 10)).filter((n) => !Number.isNaN(n));
    return parts.reduce((a, n) => a * 60 + n, 0);
  }
  const FILE_RE = /^(out|in)-([^-]+)-(\d+)-(\d{8})-(\d{6})-(\d+\.\d+)\.wav$/;
  function parseFilename(name) {
    if (!name || /[\\/]|\.\./.test(name)) return null;
    const m = FILE_RE.exec(name);
    if (!m) return null;
    return { direction: m[1], number: m[2], extension: m[3], date: m[4], time: m[5], uniqueId: m[6] };
  }
  // نگاشت ستون‌ها بر اساس عنوان (نه اندیس)
  const HEADERS = {
    uniqueId: ['uniqueid', 'unique id', 'شناسه'], date: ['تاریخ', 'date'], time: ['زمان', 'time'],
    src: ['مبدأ', 'مبدا', 'src', 'source'], dst: ['مقصد', 'dst', 'destination'],
    duration: ['مدت', 'duration'], type: ['نوع', 'type'], message: ['پیام', 'message'],
  };
  function mapColumns(headerTexts) {
    const map = {};
    headerTexts.forEach((h, i) => {
      const t = normalizeDigits(h).trim().toLowerCase();
      for (const [k, names] of Object.entries(HEADERS)) {
        if (!(k in map) && names.some((n) => t === n || t.includes(n))) map[k] = i;
      }
    });
    return map;
  }
  /** cells: متن سلول‌ها؛ links: href لینک‌های ستون پیام؛ baseUrl برای نسبی→مطلق */
  function parseRow(colMap, cells, links, baseUrl) {
    const get = (k) => (k in colMap ? (cells[colMap[k]] ?? '').trim() : '');
    const dl = (links || []).find((h) => /action=download/.test(h || ''));
    let downloadUrl = null;
    if (dl) { try { downloadUrl = new URL(dl, baseUrl).href; } catch (_) { downloadUrl = null; } }
    let namefile = null;
    if (downloadUrl) namefile = new URL(downloadUrl).searchParams.get('namefile');
    const f = parseFilename(namefile);
    const uniqueId = normalizeDigits(get('uniqueId')) || (f && f.uniqueId) ||
      (downloadUrl ? new URL(downloadUrl).searchParams.get('id') : null);
    if (!uniqueId) return null;
    const durText = get('duration');
    return {
      uniqueId, namefile, downloadUrl, date: normalizeDigits(get('date')), time: normalizeDigits(get('time')),
      src: normalizeDigits(get('src')), dst: normalizeDigits(get('dst')), durationText: durText,
      durationSec: hmsToSeconds(durText), type: get('type'), extension: f ? f.extension : null,
      direction: f ? f.direction : null,
    };
  }
  /** بازگشت دلیل غیرقابل‌تحلیل بودن یا null. cdr (اختیاری): خروجی mergeCdr برای همین uniqueId */
  function ineligibleReason(row, minSeconds, cdr) {
    if (!row.downloadUrl) return 'فایل ضبط‌شده ندارد';
    if (cdr && cdr.internal) return 'تماس داخلی (بین همکاران)';
    if (cdr && cdr.disposition && cdr.disposition !== 'answered') return 'پاسخ داده نشده / مشغول / قطع';
    const talk = cdr && cdr.talkSec != null ? cdr.talkSec : row.durationSec;
    if (talk < minSeconds) return `کمتر از ${minSeconds} ثانیه (بدون پاسخ/خیلی کوتاه)`;
    return null;
  }
  // ---------- صفحه‌ی «ریز مکالمات» (CDR) ----------
  /** «2m 17s» / «58s» / «6m 30s» → ثانیه */
  function cdrDurationToSeconds(s) {
    const t = normalizeDigits(s).trim();
    const m = /^(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*(?:(\d+)\s*s)?$/.exec(t);
    if (!m || !t) return null;
    return (+m[1] || 0) * 3600 + (+m[2] || 0) * 60 + (+m[3] || 0);
  }
  function dispositionOf(text) {
    const t = (text || '').trim();
    if (/پاسخ داده شده/.test(t)) return 'answered';
    if (/پاسخ داده نشده/.test(t)) return 'no_answer';
    if (/مشغول/.test(t)) return 'busy';
    if (/CONGESTION|FAILED/i.test(t)) return 'failed';
    return 'other';
  }
  /** ستون‌ها را بر اساس محتوا تشخیص می‌دهد (چون عنوان ستون‌های این صفحه در نمونه نبود). */
  function parseCdrRow(cells) {
    const c = cells.map((x) => (x ?? '').trim());
    const uid = c.find((x) => /^\d{6,}\.\d+$/.test(normalizeDigits(x)));
    if (!uid) return null;
    const channels = c.filter((x) => /^(PJSIP|SIP|IAX2|Local)\//.test(x));
    const dispIdx = c.findIndex((x) => /پاسخ داده|مشغول|CONGESTION|FAILED/i.test(x));
    const durIdx = c.findIndex((x, i) => i > dispIdx && dispIdx >= 0 && cdrDurationToSeconds(x) !== null && x !== '');
    const chExt = channels.map((x) => /^PJSIP\/(\d{1,5})-/.exec(x)).find(Boolean);
    const short = (x) => /^\d{1,5}$/.test(normalizeDigits(x));
    const src = c[1] || '', dst = c[3] || '';
    return {
      uniqueId: normalizeDigits(uid), dateText: c[0], src, dst,
      channel: channels[0] || null, dstChannel: channels[1] || null,
      disposition: dispIdx >= 0 ? dispositionOf(c[dispIdx]) : 'other',
      talkSec: durIdx >= 0 ? cdrDurationToSeconds(c[durIdx]) : null,
      extension: chExt ? chExt[1] : null,
      internal: short(src) && short(dst) && !!chExt === true && (channels[1] || '').startsWith('PJSIP/'),
    };
  }
  /** هر تماس چند پا دارد؛ ردیف بهتر (پاسخ‌داده‌شده با بیشترین مدت) و داخلی فروشنده را ادغام می‌کند. */
  function mergeCdr(rows) {
    const out = {};
    for (const r of rows) {
      if (!r) continue;
      const cur = out[r.uniqueId];
      if (!cur) { out[r.uniqueId] = { ...r }; continue; }
      const better = (r.disposition === 'answered' && cur.disposition !== 'answered') ||
        (r.disposition === cur.disposition && (r.talkSec || 0) > (cur.talkSec || 0));
      const ext = cur.extension || r.extension;
      out[r.uniqueId] = { ...(better ? r : cur), extension: ext, internal: cur.internal || r.internal };
    }
    return out;
  }
  /** برای هر UniqueID ردیفِ با بیشترین مدت را نگه می‌دارد (پنل ردیف ۰ ثانیه‌ای تکراری هم می‌سازد). */
  function dedupe(rows) {
    const best = new Map();
    for (const r of rows) {
      const k = r.uniqueId + '|' + (r.namefile || '');
      const cur = best.get(k);
      if (!cur || r.durationSec > cur.durationSec) best.set(k, r);
    }
    return [...best.values()];
  }
  /** آیا این ردیف همان ردیف اصلیِ قابل‌تحلیل برای uniqueId است؟ */
  function isPrimary(row, bestByUid) {
    const b = bestByUid.get(row.uniqueId);
    return !b || (b.durationSec === row.durationSec && b.time === row.time);
  }
  const api = { normalizeDigits, hmsToSeconds, parseFilename, mapColumns, parseRow, ineligibleReason, dedupe, isPrimary, cdrDurationToSeconds, parseCdrRow, mergeCdr };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.CAParser = api;
})(typeof self !== 'undefined' ? self : globalThis);
