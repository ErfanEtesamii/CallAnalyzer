const $ = (s) => document.querySelector(s);
const CS = CASettings, KEYS = Object.keys(CS.DEFAULTS);
const BOOL = ['includeInternal', 'autoAnalyze', 'showScoreInPill'];
const say = (el, text, bad) => { el.textContent = text; el.style.color = bad ? 'var(--danger)' : ''; };
$('#ver').textContent = chrome.runtime.getManifest().version;

function fill(s) {
  for (const k of KEYS) { const e = $('#' + k); if (!e) continue; if (BOOL.includes(k)) e.checked = !!s[k]; else e.value = s[k] ?? ''; }
}
function read() {
  const raw = {};
  for (const k of KEYS) { const e = $('#' + k); if (!e) continue; raw[k] = BOOL.includes(k) ? e.checked : e.value; }
  return CS.normalize(raw);
}
async function stats() {
  const { jobs = {}, cdr = {} } = await chrome.storage.local.get(['jobs', 'cdr']);
  $('#stats').textContent = `ریز مکالمات ذخیره‌شده: ${Object.keys(cdr).length.toLocaleString('fa-IR')} تماس · کارهای صف: ${Object.keys(jobs).length.toLocaleString('fa-IR')}`;
}
chrome.storage.local.get(KEYS).then((s) => { fill(CS.normalize(s)); stats(); });

async function permitBackend(url) {
  if (!url) return true;
  const u = new URL(url);
  if (u.protocol !== 'https:' && u.hostname !== 'localhost') throw new Error('برای امنیت فقط https مجاز است (به‌جز localhost).');
  return chrome.permissions.request({ origins: [u.origin + '/*'] });
}
async function ping(msgEl) {
  const r = await chrome.runtime.sendMessage({ type: 'API', path: '/api/v1/version' });
  if (r.data) { $('#bver').textContent = r.data.backend; $('#rver').textContent = r.data.rubric; say(msgEl, '✓ اتصال برقرار است'); return true; }
  say(msgEl, 'اتصال ناموفق: ' + (r.error || 'نامشخص'), true); return false;
}

const DEFAULT_ORIGIN = CS.DEFAULTS.panelOrigin;
/** اجازه‌ی دسترسی به سرور و پنل در یک درخواست (باید داخل همان کلیک کاربر باشد) و ثبت content script برای آدرس سفارشی پنل */
async function ensureAccess(s) {
  const origins = [];
  if (s.backendUrl) { const u = new URL(s.backendUrl); if (u.protocol !== 'https:' && u.hostname !== 'localhost') throw new Error('برای امنیت فقط https مجاز است (به‌جز localhost).'); origins.push(u.origin + '/*'); }
  const custom = s.panelOrigin !== DEFAULT_ORIGIN;
  if (custom) { const u = new URL(s.panelOrigin); if (u.protocol !== 'https:' && u.hostname !== 'localhost') throw new Error('آدرس پنل باید https باشد (یا localhost).'); origins.push(u.origin + '/*'); }
  if (origins.length && !(await chrome.permissions.request({ origins }))) throw new Error('دسترسی به آدرس داده نشد.');
  try { await chrome.scripting.unregisterContentScripts({ ids: ['ca-panel'] }); } catch { /* ثبت نبود */ }
  if (custom) await chrome.scripting.registerContentScripts([{ id: 'ca-panel', matches: [s.panelOrigin + '/index.php*'], js: ['src/lib/parser.js', 'src/lib/settings.js', 'src/lib/queue.js', 'src/content.js'], runAt: 'document_idle', persistAcrossSessions: true }]);
}

$('#f').addEventListener('submit', async (e) => {
  e.preventDefault(); const msg = $('#msg');
  const rawPanel = $('#panelOrigin').value.trim();
  if (rawPanel && !CS.normalizeOrigin(rawPanel)) { say(msg, 'آدرس پنل نامعتبر است.', true); return; }
  const s = read();
  try { await ensureAccess(s); } catch (err) { say(msg, err.message || 'آدرس نامعتبر است.', true); return; }
  await chrome.storage.local.set(s); fill(s);
  say(msg, '✓ ذخیره شد'); if (s.backendUrl && s.token) ping(msg);
});
$('#test').onclick = async () => {
  const s = read(); const out = $('#conn'); say(out, 'در حال آزمایش…');
  try { await permitBackend(s.backendUrl); } catch (err) { say(out, err.message || 'آدرس نامعتبر است.', true); return; }
  await chrome.storage.local.set({ backendUrl: s.backendUrl, token: s.token }); ping(out);
};
$('#showTok').onclick = (e) => { const i = $('#token'); const show = i.type === 'password'; i.type = show ? 'text' : 'password'; e.target.textContent = show ? 'پنهان' : 'نمایش'; e.target.setAttribute('aria-pressed', show); };

$('#export').onclick = () => {
  const { token, ...rest } = read();
  const url = URL.createObjectURL(new Blob([JSON.stringify(rest, null, 2)], { type: 'application/json' }));
  const a = document.createElement('a'); a.href = url; a.download = 'call-analyzer-settings.json'; a.click(); URL.revokeObjectURL(url);
};
$('#import').onclick = () => $('#file').click();
$('#file').onchange = async (e) => {
  const f = e.target.files[0]; if (!f) return;
  try {
    const j = JSON.parse(await f.text()); delete j.token;
    const cur = read(); const s = CS.normalize({ ...cur, ...Object.fromEntries(Object.entries(j).filter(([k]) => KEYS.includes(k))) });
    fill(s); say($('#msg'), 'وارد شد؛ برای اعمال «ذخیره» را بزنید.');
  } catch { say($('#msg'), 'فایل معتبر نیست.', true); }
  e.target.value = '';
};
$('#clearCdr').onclick = async () => { await chrome.storage.local.remove('cdr'); stats(); say($('#msg'), '✓ پاک شد'); };
$('#clearJobs').onclick = async () => { await chrome.storage.local.remove('jobs'); stats(); say($('#msg'), '✓ پاک شد'); };
$('#reset').onclick = async () => {
  if (!confirm('همه‌ی تنظیمات (از جمله توکن) به پیش‌فرض برگردد؟')) return;
  await chrome.storage.local.set(CS.normalize({})); fill(CS.normalize({})); say($('#msg'), '✓ بازنشانی شد');
};
