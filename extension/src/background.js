// Service Worker: صف دانلود/آپلود. حالت در chrome.storage.local می‌ماند چون MV3 هر لحظه می‌تواند بخوابد.
import './lib/queue.js';
const Q = self.CAQueue;
const DEFAULTS = { backendUrl: '', token: '', minSeconds: 20, concurrency: 2, pollSeconds: 3 };
const MAX_UPLOAD_MB = 25;
const controllers = new Map(); // uid ← AbortController (کارهای زنده‌ی همین نمونه‌ی service worker)
let running = false;

const getSettings = async () => ({ ...DEFAULTS, ...(await chrome.storage.local.get(Object.keys(DEFAULTS))) });
const getJobs = async () => (await chrome.storage.local.get('jobs')).jobs || {};

/* همه‌ی تغییرات صف پشت یک زنجیره‌ی سریالی انجام می‌شود تا دو دانلود هم‌زمان به‌روزرسانی هم را بازنویسی نکنند. */
let chain = Promise.resolve();
function mutateJobs(fn) {
  const p = chain.then(async () => {
    const jobs = await getJobs();
    const out = await fn(jobs);
    const next = out.jobs || jobs;
    await chrome.storage.local.set({ jobs: next });
    updateBadge(next);
    return out.result;
  });
  chain = p.catch(() => {});
  return p;
}
const patchJob = (uid, patch) => mutateJobs((jobs) => {
  if (!jobs[uid]) return { jobs };
  jobs[uid] = { ...jobs[uid], ...patch, updatedAt: Date.now() };
  return { jobs, result: jobs[uid] };
});
function updateBadge(jobs) {
  try { const b = Q.badge(jobs); chrome.action.setBadgeText({ text: b.text }); chrome.action.setBadgeBackgroundColor({ color: b.color }); } catch (_) {}
}

function userError(message, code) { const e = new Error(message); e.userMessage = message; e.code = code; return e; }

async function api(path, opts = {}) {
  const s = await getSettings();
  if (!s.backendUrl || !s.token) throw userError('اتصال تنظیم نشده است. آدرس سرور و توکن را در تنظیمات وارد کنید.', 'no_config');
  let res;
  try {
    res = await fetch(s.backendUrl.replace(/\/$/, '') + path, { ...opts, headers: { Authorization: 'Bearer ' + s.token, ...(opts.headers || {}) } });
  } catch (e) {
    if (e.name === 'AbortError') throw e;
    throw userError('اتصال به سرور تحلیل برقرار نشد.', 'network');
  }
  if (res.status === 401) throw userError('توکن نامعتبر است.', 'auth');
  if (res.status === 404) throw userError('مورد یافت نشد.', 'not_found');
  if (!res.ok) {
    let msg = 'خطای سرور';
    try { const j = await res.json(); if (typeof j.detail === 'string') msg = j.detail; } catch (_) {}
    throw userError(msg, res.status === 429 ? 'rate_limit' : res.status >= 500 ? 'server_5xx' : 'server_4xx');
  }
  return res.json();
}

async function downloadWav(url, signal) {
  let res;
  try { res = await fetch(url, { credentials: 'include', signal }); }
  catch (e) {
    if (e.name === 'AbortError') throw e;
    throw userError('دانلود از پنل ممکن نشد. یک‌بار پنل را باز کنید و گواهی را بپذیرید.', 'panel_network');
  }
  if (!res.ok) throw userError('پنل پاسخ نامعتبر داد (' + res.status + ').', 'panel_http');
  const len = Number(res.headers.get('content-length') || 0);
  if (len > MAX_UPLOAD_MB << 20) throw userError(`حجم فایل بیش از ${MAX_UPLOAD_MB} مگابایت است.`, 'too_large');
  const buf = await res.arrayBuffer();
  const head = new Uint8Array(buf.slice(0, 12));
  const riff = String.fromCharCode(...head.slice(0, 4)) === 'RIFF' && String.fromCharCode(...head.slice(8, 12)) === 'WAVE';
  if (!riff || buf.byteLength < 2000) throw userError('نشست پنل منقضی شده. یک‌بار وارد پنل شوید و دوباره تلاش کنید.', 'session_expired');
  if (buf.byteLength > MAX_UPLOAD_MB << 20) throw userError(`حجم فایل بیش از ${MAX_UPLOAD_MB} مگابایت است.`, 'too_large');
  return new Blob([buf], { type: 'audio/wav' });
}

/** پس از claim شدن توسط pump، state برابر downloading است. */
async function runJob(uid) {
  const ctl = new AbortController(); controllers.set(uid, ctl);
  const alive = async () => { const j = (await getJobs())[uid]; return j && !j.cancelled ? j : null; };
  try {
    let job = await alive(); if (!job) return;
    const m = job.meta;
    if (!job.force) {
      try {
        const ex = await api('/api/v1/analyses/by-unique-id/' + encodeURIComponent(uid), { signal: ctl.signal });
        if (ex && ex.status === 'done') { await patchJob(uid, { state: 'done', analysisId: ex.id, score: ex.overall_score, grade: ex.grade }); return; }
      } catch (e) { if (e.code !== 'not_found') throw e; }
    }
    const blob = await downloadWav(m.downloadUrl, ctl.signal);
    job = await alive(); if (!job) return;
    await patchJob(uid, { state: 'uploading' });
    const fd = new FormData();
    fd.append('file', blob, m.namefile || uid + '.wav');
    Object.entries({ unique_id: uid, namefile: m.namefile || '', call_date: m.date, call_time: m.time, src: m.src, dst: m.dst,
      panel_duration: m.durationText, talk_seconds: m.talkSec ?? '', seller_ext: m.extension || '', direction: m.direction || 'out', force: job.force ? 'true' : 'false' })
      .forEach(([k, v]) => fd.append(k, v ?? ''));
    const r = await api('/api/v1/analyses', { method: 'POST', body: fd, signal: ctl.signal });
    await patchJob(uid, { state: 'processing', analysisId: r.id, serverStatus: r.status, processingSince: Date.now(), error: null });
  } catch (e) {
    if (e.name === 'AbortError') return; // لغو شده؛ state را CANCEL تنظیم کرده است
    const job = (await getJobs())[uid];
    if (job && !job.cancelled) await patchJob(uid, Q.onFailure(job, e, Date.now()));
  } finally { controllers.delete(uid); }
}

/** وضعیت همه‌ی کارهای در حال پردازش با یک درخواست */
async function pollProcessing() {
  const jobs = await getJobs();
  const pend = Object.entries(jobs).filter(([, j]) => j.state === 'processing');
  if (!pend.length) return 0;
  const now = Date.now();
  const live = [];
  for (const [uid, j] of pend) {
    if (Q.processingTimedOut(j, now)) await patchJob(uid, { state: 'error', error: 'پردازش بیش از ۱۵ دقیقه طول کشید.', errorCode: 'timeout' });
    else live.push(uid);
  }
  if (!live.length) return 0;
  try {
    const st = await api('/api/v1/analyses/batch-status', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ unique_ids: live }) });
    for (const uid of live) {
      const a = st[uid];
      if (!a) await patchJob(uid, { state: 'error', error: 'این تحلیل روی سرور پیدا نشد.', errorCode: 'not_found' });
      else if (a.status === 'done') await patchJob(uid, { state: 'done', score: a.overall_score, grade: a.grade, serverStatus: 'done' });
      else if (a.status === 'failed') await patchJob(uid, { state: 'error', error: a.error_message || 'تحلیل ناموفق بود', errorCode: 'analysis_failed' });
      else await patchJob(uid, { serverStatus: a.status });
    }
  } catch (e) {
    if (e.code === 'auth' || e.code === 'no_config') for (const uid of live) await patchJob(uid, { state: 'error', error: e.userMessage, errorCode: e.code });
  }
  return live.length;
}

async function pump() {
  if (running) return; running = true;
  try {
    // کارهای یتیم (مثلاً service worker وسط دانلود خوابیده) به صف برمی‌گردند؛ قدیمی‌ها پاک می‌شوند
    await mutateJobs((jobs) => {
      const patches = Q.recoverOrphans(jobs, (u) => controllers.has(u));
      for (const [u, p] of Object.entries(patches)) jobs[u] = { ...jobs[u], ...p };
      return { jobs: Q.prune(jobs, Date.now()) };
    });
    for (;;) {
      const s = await getSettings();
      const claimed = await mutateJobs((jobs) => {
        const active = Object.values(jobs).filter((j) => Q.RUNNING.includes(j.state)).length;
        const uids = Q.pickRunnable(jobs, Date.now(), s.concurrency - active);
        uids.forEach((u) => { jobs[u] = { ...jobs[u], state: 'downloading', updatedAt: Date.now() }; });
        return { jobs, result: uids };
      });
      claimed.forEach((u) => { runJob(u); });
      const processing = await pollProcessing();
      const jobs = await getJobs();
      const busy = Object.values(jobs).some((j) => Q.RUNNING.includes(j.state) || (j.state === 'queued' && !j.cancelled));
      if (!busy && !processing) break;
      await new Promise((r) => setTimeout(r, Math.max(2, s.pollSeconds) * 1000));
    }
  } finally { running = false; }
}

chrome.alarms.create('pump', { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener((a) => { if (a.name === 'pump') pump(); });
chrome.runtime.onStartup.addListener(() => pump());
chrome.runtime.onInstalled.addListener(() => pump());

chrome.runtime.onMessage.addListener((msg, sender, send) => {
  (async () => {
    switch (msg.type) {
      case 'ENQUEUE': {
        const r = await mutateJobs((jobs) => { const o = Q.addJobs(jobs, msg.rows, { force: !!msg.force }); return { jobs: o.jobs, result: { added: o.added, skipped: o.skipped } }; });
        pump(); return { ok: true, ...r };
      }
      case 'CANCEL': {
        controllers.get(msg.uniqueId)?.abort();
        await patchJob(msg.uniqueId, { cancelled: true, state: 'cancelled' }); return { ok: true };
      }
      case 'RETRY': await patchJob(msg.uniqueId, { state: 'queued', error: null, errorCode: null, cancelled: false, attempts: 0, nextAttemptAt: 0 }); pump(); return { ok: true };
      case 'RETRY_ALL': {
        const n = await mutateJobs((jobs) => { let c = 0; for (const [u, j] of Object.entries(jobs)) if (j.state === 'error') { jobs[u] = { ...j, state: 'queued', error: null, errorCode: null, attempts: 0, nextAttemptAt: 0, updatedAt: Date.now() }; c++; } return { jobs, result: c }; });
        pump(); return { ok: true, retried: n };
      }
      case 'CLEAR_FINISHED': {
        const n = await mutateJobs((jobs) => { let c = 0; for (const [u, j] of Object.entries(jobs)) if (j.state === 'done' || j.state === 'cancelled') { delete jobs[u]; c++; } return { jobs, result: c }; });
        return { ok: true, cleared: n };
      }
      case 'GET_JOBS': return { jobs: await getJobs() };
      case 'BATCH_STATUS': {
        try { return { data: await api('/api/v1/analyses/batch-status', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ unique_ids: msg.uniqueIds }) }) }; }
        catch (e) { return { error: e.userMessage, code: e.code }; }
      }
      case 'API': try { return { data: await api(msg.path, msg.init) }; } catch (e) { return { error: e.userMessage, code: e.code }; }
      case 'OPEN_PANEL': await chrome.sidePanel.open({ tabId: sender.tab.id }); return { ok: true };
      default: return { error: 'unknown' };
    }
  })().then(send);
  return true;
});
chrome.sidePanel.setPanelBehavior?.({ openPanelOnActionClick: true });
getJobs().then(updateBadge);
