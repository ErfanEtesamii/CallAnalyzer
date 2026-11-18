"""آزمون e2e نمای زنده‌ی پنل کناری با سرور ساختگی: حباب‌ها تدریجی می‌آیند، راست/چپ درست است، تحلیل و گذار به گزارش.
اجرا: python3 tests/e2e_live.py [پوشه‌ی خروجی اسکرین‌شات]  — خروجی غیرصفر یعنی شکست."""
import json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

EXT = Path(__file__).resolve().parent.parent
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/shots"); OUT.mkdir(parents=True, exist_ok=True)

SCRIPT = [  # (start, speaker, text)
    (0, "seller", "سلام وقت بخیر، جناب رضایی؟ از مجموعه‌ی فراز هنر تماس می‌گیرم"),
    (7, "customer", "سلام بله بفرمایید"),
    (9, "seller", "ما تولیدکننده‌ی تخصصی هدایای سازمانی با محوریت صنایع دستی هستیم"),
    (15, "seller", "خیلی مشتاقم در این زمینه با شرکت شما همکاری داشته باشیم. امیدوارم زمان مناسبی تماس گرفته باشم"),
    (24, "customer", "ممنون، ما معمولاً برای عید و پایان سال هدیه تهیه می‌کنیم"),
    (31, "seller", "عالیه! تصمیم‌گیری هدایا معمولاً با چه واحدی انجام میشه؟"),
    (37, "customer", "با واحد منابع انسانی هماهنگ می‌کنیم، ولی بودجه هنوز مشخص نیست"),
]
MOCK = """
window.__store = { backendUrl: 'https://x', token: 't', focusUid: 'U1', theme: '%THEME%', jobs: { U1: { state: 'queued', meta: { dst: '09120000000', extension: '14', date: '1405/08/28', time: '10:20' } } } };
window.__state = { status: 'transcribing', segs: [], aidKnown: false };
const L = [];
const getv = (k) => { const ks = Array.isArray(k) ? k : [k]; const o = {}; ks.forEach((x) => { if (x in window.__store) o[x] = JSON.parse(JSON.stringify(window.__store[x])); }); return o; };
window.chrome = {
  storage: { local: { get: async (k) => getv(k), set: async (o) => { const ch = {}; for (const [k, v] of Object.entries(o)) { ch[k] = { newValue: v }; window.__store[k] = v; } L.forEach((f) => f(ch)); } }, onChanged: { addListener: (f) => L.push(f) } },
  runtime: { openOptionsPage() {}, sendMessage: async (m) => {
    if (m.type === 'GET_JOBS') return { jobs: window.__store.jobs };
    if (m.type !== 'API') return { ok: true };
    const p = m.path;
    if (p === '/health') return { data: { ok: true } };
    if (p.startsWith('/api/v1/analyses/by-unique-id/')) {
      if (!window.__state.aidKnown) return { error: 'یافت نشد', code: 'not_found' };
      return { data: { id: 7, unique_id: 'U1', status: window.__state.status, dst_masked: '0353***7500', seller_ext: '14', seller_name: 'مریم احمدی', call_datetime: '2026-11-19T10:20:00' } };
    }
    if (/\\/analyses\\/7\\/live/.test(p)) { const after = +new URL('http://x' + p).searchParams.get('after');
      const segs = window.__state.segs.filter((s) => s.i >= after);
      return { data: { status: window.__state.status, next: segs.length ? segs[segs.length - 1].i + 1 : after, segments: segs } }; }
    if (p === '/api/v1/analyses/7') return { data: { id: 7, unique_id: 'U1', status: window.__state.status, dst_masked: '0353***7500', seller_name: 'مریم احمدی', seller_ext: '14', call_datetime: '2026-11-19T10:20:00', result: null } };
    return { error: 'unexpected ' + p, code: 'x' };
  } },
};
"""
fails = []
def check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), name, detail)
    if not cond: fails.append(name)

def run(theme, tag):
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 420, "height": 860})
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script(MOCK.replace("%THEME%", theme))
        pg.goto((EXT / "src/sidepanel.html").as_uri())
        pg.wait_for_selector(".live", timeout=5000)
        check(f"{tag}: نمای زنده قبل از ساخته‌شدن روی سرور (مرحله‌ی دانلود)", pg.locator(".live .steps").count() == 1)
        pg.evaluate("window.__store.jobs = { U1: { state: 'downloading', meta: { dst: '09120000000', extension: '14', date: '1405/08/28', time: '10:20' } } }")
        pg.wait_for_timeout(1500)
        pg.screenshot(path=str(OUT / f"{tag}-1-download.png"))
        pg.evaluate("window.__state.aidKnown = true; window.__state.status = 'transcribing'")
        pg.wait_for_timeout(1700)
        check(f"{tag}: «در حال شنیدن» (نقطه‌های تایپ) قبل از اولین حباب", pg.locator(".msg.typing .dots").count() == 1)
        # حباب‌ها یکی‌یکی
        for i, (st, sp, tx) in enumerate(SCRIPT[:4]):
            pg.evaluate("(s) => window.__state.segs.push(s)", {"i": i, "start": st, "end": st + 6, "text": tx, "speaker": sp})
            pg.wait_for_timeout(1500)
        pg.screenshot(path=str(OUT / f"{tag}-2-chat.png"))
        n_s = pg.locator(".lv-chat .msg.s:not(.typing)").count(); n_c = pg.locator(".lv-chat .msg.c:not(.typing)").count()
        check(f"{tag}: کارشناس (چسبیده‌ی پشت‌سرهم) یک حباب با چند خط", n_s == 2 and n_c == 1, f"s={n_s} c={n_c}")
        check(f"{tag}: خط‌های حباب سوم و چهارم یک دسته‌اند", pg.locator(".lv-chat .msg.s .ln").count() == 3)
        # مختصات: کارشناس راست، مشتری چپ
        xs = pg.evaluate("document.querySelector('.msg.s:not(.typing) .bub').getBoundingClientRect().right")
        xc = pg.evaluate("document.querySelector('.msg.c:not(.typing) .bub').getBoundingClientRect().left")
        check(f"{tag}: کارشناس سمت راست و مشتری سمت چپ", xs > 300 and xc < 120, f"seller.right={xs:.0f} customer.left={xc:.0f}")
        txt = pg.inner_text(".lv-chat")
        check(f"{tag}: متن‌ها کامل تایپ شد", "فراز هنر" in txt and "همکاری" in txt and "بله بفرمایید" in txt)
        for i, (st, sp, tx) in enumerate(SCRIPT[4:], start=4):
            pg.evaluate("(s) => window.__state.segs.push(s)", {"i": i, "start": st, "end": st + 6, "text": tx, "speaker": sp})
        pg.wait_for_timeout(1800)
        check(f"{tag}: تکرار polling حباب تکراری نمی‌سازد", pg.locator(".lv-chat .ln").count() == len(SCRIPT))
        pg.evaluate("window.__state.status = 'analyzing'")
        pg.wait_for_timeout(1700)
        check(f"{tag}: حالت تحلیل نمایش داده می‌شود و تایپ‌نشانگر برداشته می‌شود", pg.locator(".lv-think").is_visible() and pg.locator(".msg.typing").count() == 0)
        pg.screenshot(path=str(OUT / f"{tag}-3-analyzing.png"), full_page=True)
        pg.evaluate("window.__state.status = 'done'")
        pg.wait_for_timeout(2600)
        check(f"{tag}: پس از done نمای زنده بسته می‌شود (گذار به گزارش)", pg.locator(".live").count() == 0)
        check(f"{tag}: بدون خطای JS", not errs, "; ".join(errs[:2]))
        b.close()

run("light", "light"); run("dark", "dark")
print("FAILED:", fails) if fails else print("ALL PASS"); sys.exit(1 if fails else 0)
