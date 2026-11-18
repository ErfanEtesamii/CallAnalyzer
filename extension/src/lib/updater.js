/* به‌روزرسانی خودکار اکستنشن (unpacked): منطق خالص، بدون وابستگی به chrome.* (قابل‌تست با Node).

جریان کار: اسکریپت همگام‌ساز ویندوز (client/sync.ps1) فایل‌های جدید را از بک‌اند در پوشه‌ی اکستنشن می‌نویسد
و manifest.json را آخر از همه عوض می‌کند. این‌جا فقط نسخه‌ی manifest روی دیسک را با نسخه‌ی در حال اجرا مقایسه می‌کنیم
و اگر فرق داشت (و کار فعالی نبود) chrome.runtime.reload() می‌زنیم. */
(function (root) {
  const MIN_GAP_MS = 2 * 60 * 1000;     // حداقل فاصله‌ی دو reload پشت‌سرهم (محافظ حلقه)
  const MAX_WAIT_MS = 30 * 60 * 1000;   // اگر کار فعال تمام نمی‌شود، بعد از این مدت هم reload کن (کارها بازیابی می‌شوند)
  const STALE_MS = 20 * 60 * 1000;      // سرور نسخه‌ی جدیدتر دارد ولی دیسک عوض نشده ← همگام‌ساز کار نمی‌کند

  /** تصمیم خالص: none | wait | reload */
  function decide({ running, disk, busy, now, state }) {
    const st = state || {};
    if (!disk || disk === running) return { action: 'none', state: { ...st, pendingSince: null } };
    const pendingSince = st.pendingSince || now;
    if (st.lastReloadAt && now - st.lastReloadAt < MIN_GAP_MS) return { action: 'wait', state: { ...st, pendingSince } };
    if (busy && now - pendingSince < MAX_WAIT_MS) return { action: 'wait', state: { ...st, pendingSince } };
    return { action: 'reload', state: { ...st, pendingSince, lastReloadAt: now } };
  }

  /** آیا همگام‌ساز این کامپیوتر عقب مانده است؟ (سرور نسخه‌ی دیگری دارد ولی دیسک عوض نمی‌شود) */
  function staleness({ serverVersion, disk, now, state }) {
    const st = { ...(state || {}), serverVersion: serverVersion || null };
    if (!serverVersion || !disk || serverVersion === disk) return { ...st, behindSince: null, syncStale: false };
    const behindSince = st.behindSince || now;
    return { ...st, behindSince, syncStale: now - behindSince >= STALE_MS };
  }

  /** deps: { readDiskVersion, running, isBusy, reload, load, save, now, fetchServerVersion? } */
  async function check(deps) {
    const now = deps.now ? deps.now() : Date.now();
    let disk = null;
    try { disk = await deps.readDiskVersion(); } catch (_) { return { action: 'none', disk: null }; }
    let state = (await deps.load()) || {};
    if (deps.fetchServerVersion && (!state.serverCheckedAt || now - state.serverCheckedAt >= 5 * 60 * 1000)) {
      state = { ...state, serverCheckedAt: now };
      try { state = staleness({ serverVersion: await deps.fetchServerVersion(), disk, now, state }); } catch (_) { /* سرور در دسترس نیست */ }
    }
    const busy = disk !== deps.running ? await deps.isBusy() : false;
    const d = decide({ running: deps.running, disk, busy, now, state });
    await deps.save({ ...d.state, running: deps.running, disk });
    if (d.action === 'reload') await deps.reload();
    return { action: d.action, disk };
  }

  const api = { MIN_GAP_MS, MAX_WAIT_MS, STALE_MS, decide, staleness, check };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.CAUpdater = api;
})(typeof self !== 'undefined' ? self : globalThis);
