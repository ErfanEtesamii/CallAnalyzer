/* انتقال فایل صوتی از content script (داخل صفحه‌ی پنل) به service worker.
   چرا: service worker گواهی self-signed پنل را نمی‌پذیرد (ERR_CERT_AUTHORITY_INVALID) و کوکی صفحه را ندارد؛
   content script روی خود صفحه اجرا می‌شود و هر دو را دارد. فایل تکه‌تکه (base64) از طریق پیام منتقل می‌شود.
   بدون وابستگی به chrome.* تا با Node قابل‌تست باشد. */
(function (root) {
  const CHUNK = 512 * 1024;
  const HOLD_MS = 120000; // اگر service worker نیامد، بافر آزاد می‌شود

  const toB64 = (u8) => {
    let s = '';
    for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
    return btoa(s);
  };
  const fromB64 = (b64) => {
    const s = atob(b64), u = new Uint8Array(s.length);
    for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i);
    return u;
  };
  const isWav = (u8) => u8.length >= 2000 && String.fromCharCode(...u8.subarray(0, 4)) === 'RIFF' && String.fromCharCode(...u8.subarray(8, 12)) === 'WAVE';
  const fail = (code, message) => ({ ok: false, code, message });
  const abortErr = () => Object.assign(new Error('aborted'), { name: 'AbortError' });
  const userErr = (message, code) => Object.assign(new Error(message), { userMessage: message, code });

  /** سمت صفحه: پاسخ به پیام‌های FETCH_WAV / WAV_CHUNK / WAV_RELEASE / WAV_ABORT */
  function createPanelFetcher({ fetchFn, baseHref }) {
    const bufs = new Map(), ctls = new Map(), timers = new Map();
    const release = (id) => { bufs.delete(id); ctls.delete(id); clearTimeout(timers.get(id)); timers.delete(id); };
    async function handle(msg) {
      const id = msg.id;
      switch (msg.type) {
        case 'FETCH_WAV': {
          const ctl = new AbortController(); ctls.set(id, ctl);
          const max = msg.maxBytes || 25 << 20;
          try {
            let res;
            try { res = await fetchFn(new URL(msg.url, baseHref).href, { credentials: 'include', signal: ctl.signal }); }
            catch (e) { return ctl.signal.aborted ? fail('aborted') : fail('panel_network', 'دانلود از پنل ممکن نشد. اتصال به پنل را بررسی کنید.'); }
            if (!res.ok) return fail('panel_http', 'پنل پاسخ نامعتبر داد (' + res.status + ').');
            if (Number(res.headers.get('content-length') || 0) > max) return fail('too_large', `حجم فایل بیش از ${max >> 20} مگابایت است.`);
            let u8;
            try { u8 = new Uint8Array(await res.arrayBuffer()); }
            catch (e) { return ctl.signal.aborted ? fail('aborted') : fail('panel_network', 'دانلود از پنل نیمه‌کاره ماند.'); }
            if (!isWav(u8)) return fail('session_expired', 'نشست پنل منقضی شده. یک‌بار وارد پنل شوید و دوباره تلاش کنید.');
            if (u8.length > max) return fail('too_large', `حجم فایل بیش از ${max >> 20} مگابایت است.`);
            bufs.set(id, u8); timers.set(id, setTimeout(() => release(id), HOLD_MS));
            return { ok: true, size: u8.length, chunks: Math.max(1, Math.ceil(u8.length / CHUNK)) };
          } finally { ctls.delete(id); }
        }
        case 'WAV_CHUNK': {
          const u8 = bufs.get(id);
          if (!u8) return { ok: false, code: 'gone' };
          return { ok: true, b64: toB64(u8.subarray(msg.index * CHUNK, (msg.index + 1) * CHUNK)) };
        }
        case 'WAV_ABORT': ctls.get(id)?.abort(); return { ok: true };
        case 'WAV_RELEASE': release(id); return { ok: true };
        default: return null;
      }
    }
    return { handle, _bufs: bufs };
  }

  /** سمت service worker: send(msg) پیام را به یک تب می‌فرستد. اگر تب پاسخ ندهد خطای خامِ chrome (بدون code) پرتاب می‌شود. */
  async function pullWav(send, { url, id, maxBytes, signal }) {
    const onAbort = () => { Promise.resolve(send({ type: 'WAV_ABORT', id })).catch(() => {}); };
    signal?.addEventListener('abort', onAbort);
    try {
      if (signal?.aborted) throw abortErr();
      const head = await send({ type: 'FETCH_WAV', id, url, maxBytes });
      if (signal?.aborted) throw abortErr();
      if (!head) throw new Error('no response from tab');
      if (!head.ok) { if (head.code === 'aborted') throw abortErr(); throw userErr(head.message || 'دانلود ناموفق بود.', head.code || 'panel_network'); }
      const out = new Uint8Array(head.size); let off = 0;
      for (let i = 0; i < head.chunks; i++) {
        if (signal?.aborted) throw abortErr();
        const r = await send({ type: 'WAV_CHUNK', id, index: i });
        if (!r || !r.ok) throw userErr('انتقال فایل از صفحه‌ی پنل قطع شد. دوباره تلاش کنید.', 'panel_network');
        const part = fromB64(r.b64); out.set(part, off); off += part.length;
      }
      if (off !== head.size) throw userErr('فایل صوتی ناقص منتقل شد.', 'panel_network');
      return out.buffer;
    } finally {
      signal?.removeEventListener('abort', onAbort);
      Promise.resolve(send({ type: 'WAV_RELEASE', id })).catch(() => {});
    }
  }

  const api = { CHUNK, toB64, fromB64, isWav, createPanelFetcher, pullWav };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.CATransfer = api;
})(typeof self !== 'undefined' ? self : globalThis);
