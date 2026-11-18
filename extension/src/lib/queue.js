/* منطق خالص صف (بدون chrome.*): قابل‌تست با Node و قابل‌استفاده در service worker. */
(function (root) {
  const ACTIVE = ['queued', 'downloading', 'uploading', 'processing'];
  const RUNNING = ['downloading', 'uploading'];
  // خطاهایی که تکرار خودکار فایده ندارد
  const NON_RETRY = new Set(['auth', 'no_config', 'session_expired', 'panel_http', 'server_4xx', 'too_large', 'not_found']);
  const isActive = (j) => ACTIVE.includes(j.state);

  /** افزودن ردیف‌ها؛ ردیفی که همین حالا فعال است دوباره اضافه نمی‌شود. */
  function addJobs(jobs, rows, { force = false, now = Date.now() } = {}) {
    const next = { ...jobs }; let added = 0, skipped = 0;
    for (const row of rows) {
      const cur = next[row.uniqueId];
      if (cur && isActive(cur)) { skipped++; continue; }
      next[row.uniqueId] = { meta: row, state: 'queued', force: !!force, attempts: 0, cancelled: false, error: null, errorCode: null, createdAt: now, updatedAt: now, nextAttemptAt: 0 };
      added++;
    }
    return { jobs: next, added, skipped };
  }
  /** کارهای downloading/uploading که هیچ اجرای زنده‌ای ندارند (مثلاً بعد از خواب service worker). */
  function recoverOrphans(jobs, isLive) {
    const patches = {};
    for (const [uid, j] of Object.entries(jobs)) if (RUNNING.includes(j.state) && !isLive(uid)) patches[uid] = { state: 'queued', nextAttemptAt: 0 };
    return patches;
  }
  function pickRunnable(jobs, now, free) {
    return Object.entries(jobs)
      .filter(([, j]) => j.state === 'queued' && !j.cancelled && (j.nextAttemptAt || 0) <= now)
      .sort((a, b) => (a[1].createdAt || 0) - (b[1].createdAt || 0))
      .slice(0, Math.max(0, free)).map(([u]) => u);
  }
  const backoffMs = (attempts) => Math.min(60000, 5000 * 2 ** attempts);
  /** نتیجه‌ی شکست: تلاش مجدد خودکار (تا maxAttempts) یا خطای نهایی. */
  function onFailure(job, err, now, maxAttempts = 3) {
    const code = err.code || 'unknown', n = job.attempts || 0, msg = err.userMessage || err.message || 'خطای ناشناخته';
    if (!NON_RETRY.has(code) && n + 1 < maxAttempts) {
      return { state: 'queued', attempts: n + 1, nextAttemptAt: now + backoffMs(n), error: msg + ' (تلاش مجدد خودکار)', errorCode: code };
    }
    return { state: 'error', error: msg, errorCode: code, nextAttemptAt: 0 };
  }
  const processingTimedOut = (job, now, limitMs = 15 * 60 * 1000) => job.state === 'processing' && now - (job.processingSince ?? job.updatedAt ?? now) > limitMs;
  function badge(jobs) {
    const list = Object.values(jobs), active = list.filter(isActive).length, errs = list.filter((j) => j.state === 'error').length;
    if (active) return { text: String(active), color: '#14919B' };
    if (errs) return { text: '!', color: '#CC3E39' };
    return { text: '', color: '#14919B' };
  }
  /** حذف قدیمی‌های تمام‌شده؛ فعال‌ها و خطاها می‌مانند. سقف تعداد هم دارد. */
  function prune(jobs, now, { maxAgeMs = 7 * 864e5, maxCount = 500 } = {}) {
    const keep = Object.entries(jobs).filter(([, j]) => isActive(j) || j.state === 'error' || now - (j.updatedAt || 0) < maxAgeMs);
    keep.sort((a, b) => (b[1].updatedAt || 0) - (a[1].updatedAt || 0));
    return Object.fromEntries(keep.slice(0, maxCount));
  }
  const totalMinutes = (rows) => Math.round(rows.reduce((s, r) => s + (r.talkSec ?? r.durationSec ?? 0), 0) / 60);
  const api = { ACTIVE, RUNNING, NON_RETRY, isActive, addJobs, recoverOrphans, pickRunnable, backoffMs, onFailure, processingTimedOut, badge, prune, totalMinutes };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.CAQueue = api;
})(typeof self !== 'undefined' ? self : globalThis);
