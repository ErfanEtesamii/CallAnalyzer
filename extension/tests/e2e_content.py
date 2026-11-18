"""آزمون e2e برای content script روی فیکسچرهای واقعی پنل (نیازمند playwright پایتون).
اجرا: python3 tests/e2e_content.py   — خروجی غیرصفر یعنی شکست."""
import json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

EXT = Path(__file__).resolve().parent.parent
TABLE = (EXT / "fixtures/calls-table.html").read_text(encoding="utf-8")
CDR = (EXT / "fixtures/cdr-tbody.html").read_text(encoding="utf-8")
OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/e2e-content.png"

MOCK = """
window.__sent = []; const L = [];
window.__store = { jobs: {}, cdr: {}, minSeconds: 20 };
const getv = (k) => { const ks = Array.isArray(k) ? k : [k]; const o = {}; ks.forEach((x) => { if (x in window.__store) o[x] = JSON.parse(JSON.stringify(window.__store[x])); }); return o; };
window.chrome = {
  storage: { local: { get: async (k) => getv(k), set: async (o) => { const ch = {}; for (const [k, v] of Object.entries(o)) { ch[k] = { newValue: v }; window.__store[k] = v; } L.forEach((f) => f(ch)); } }, onChanged: { addListener: (f) => L.push(f) } },
  runtime: { sendMessage: async (m) => { window.__sent.push(m);
    if (m.type === 'BATCH_STATUS') return { data: { '1794910108.189779': { status: 'done', overall_score: 72, grade: 'B' } } };
    if (m.type === 'ENQUEUE') return { ok: true, added: m.rows.length, skipped: 0 };
    return { ok: true }; } },
};
"""
SEED = """(cdrHtml) => {
  const doc = new DOMParser().parseFromString('<table>' + cdrHtml + '</table>', 'text/html');
  const rows = [...doc.querySelectorAll('tr')].map((tr) => CAParser.parseCdrRow([...tr.children].map((td) => td.textContent)));
  window.__store.cdr = CAParser.mergeCdr(rows);
  return Object.keys(window.__store.cdr).length;
}"""
fails = []
def check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), name, detail)
    if not cond: fails.append(name)

def load(pg, url, body, seed_cdr):
    pg.goto(url)
    pg.set_content(f"<!doctype html><html lang=fa dir=rtl><body><div class='col-md-12'>{body}</div></body></html>")
    pg.add_script_tag(content=MOCK)
    pg.add_script_tag(path=str(EXT / "src/lib/parser.js"))
    if seed_cdr: print("cdr entries seeded:", pg.evaluate(SEED, CDR))
    for f in ("settings.js", "queue.js"): pg.add_script_tag(path=str(EXT / "src/lib" / f))
    pg.add_script_tag(path=str(EXT / "src/content.js"))
    pg.wait_for_timeout(900)

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 760})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("dialog", lambda d: d.accept())
    # صفحه‌ی خالی با query تا location.search درست باشد
    load(pg, "http://localhost:9/?menu=monitoring", TABLE, True) if False else None
    pg.route("**/*", lambda r: r.fulfill(body="<html></html>", content_type="text/html"))
    load(pg, "http://localhost:9/index.php?menu=monitoring", TABLE, True)

    check("بدون خطای JS", not errs, str(errs[:3]))
    n = pg.locator(".ca-host").count()
    check("برای هر ۱۰ ردیف UI ساخته شد", n == 10, f"n={n}")
    pills = [pg.locator(".ca-host").nth(i).locator(".pill").inner_text() for i in range(n)]
    print("pills:", pills)
    check("ردیف تمام‌شده امتیاز را نشان می‌دهد", "۷۲" in pills[4] and "B" in pills[4], pills[4])
    check("تماس busy در CDR غیرقابل‌تحلیل است", pills[0] == "غیرقابل‌تحلیل" and pills[2] == "غیرقابل‌تحلیل")
    check("۳ تماس واجد شرایط 'تحلیل‌نشده'", [pills[i] for i in (5, 8, 9)] == ["تحلیل‌نشده"] * 3, str([pills[i] for i in (5, 8, 9)]))
    check("ستون سرتیتر با چک‌باکس انتخاب همه", pg.locator("th.ca-th input").count() == 1)

    # انتخاب همه
    pg.locator("th.ca-th input").click(); pg.wait_for_timeout(200)
    bar = pg.locator(".bar").inner_text()
    check("انتخاب همه ← ۳ تماس", "۳ تماس انتخاب شد" in bar, bar.replace("\n", " "))
    pg.screenshot(path=OUT)
    pg.locator(".bar .btn.primary").click(); pg.wait_for_timeout(300)
    enq = [m for m in pg.evaluate("window.__sent") if m["type"] == "ENQUEUE"]
    check("ENQUEUE یک‌بار ارسال شد", len(enq) == 1)
    rows = enq[0]["rows"] if enq else []
    check("سه ردیف درست ارسال شد", sorted(r["uniqueId"] for r in rows) == ["1794909390.189574", "1794909577.189624", "1794909854.189718"], str([r["uniqueId"] for r in rows]))
    check("داخلی از CDR و مدت واقعی همراه است", all(r["extension"] == "14" for r in rows) and sorted(r["talkSec"] for r in rows) == [61, 89, 137], str([(r["extension"], r["talkSec"]) for r in rows]))
    check("نوار انتخاب پس از ارسال پاک شد", pg.locator(".bar").count() == 0)

    # انتخاب بازه‌ای با Shift (ردیف ۶ تا ۱۰)
    cbs = pg.locator(".ca-host .cb")
    cbs.nth(5).click(); cbs.nth(9).click(modifiers=["Shift"]); pg.wait_for_timeout(200)
    bar = pg.locator(".bar").inner_text() if pg.locator(".bar").count() else ""
    check("Shift-click بازه را انتخاب می‌کند (غیرقابل‌تحلیل‌ها رد می‌شوند)", "۳ تماس انتخاب شد" in bar, bar.replace("\n", " "))
    pg.locator(".bar .btn.ghost").nth(1).click(); pg.wait_for_timeout(150)
    check("پاک‌کردن انتخاب", pg.locator(".bar").count() == 0)
    check("چک‌باکس تماس غیرقابل‌تحلیل غیرفعال است", pg.locator(".ca-host .cb").nth(0).is_disabled())

    # تماس داخلی با گزینه‌ی فعال‌سازی
    pg.close()
    # صفحه‌ی CDR: ذخیره‌ی داده
    pg = b.new_page(viewport={"width": 1280, "height": 700})
    pg.route("**/*", lambda r: r.fulfill(body="<html></html>", content_type="text/html"))
    errs2 = []; pg.on("pageerror", lambda e: errs2.append(str(e)))
    pg.goto("http://localhost:9/index.php?menu=cdrreport")
    pg.set_content(f"<!doctype html><html><body><table><tbody>{CDR[CDR.index('<tr'):CDR.rindex('</tbody>')]}</tbody></table></body></html>")
    pg.add_script_tag(content=MOCK)
    for f in ("parser.js", "settings.js", "queue.js"): pg.add_script_tag(path=str(EXT / "src/lib" / f))
    pg.add_script_tag(path=str(EXT / "src/content.js")); pg.wait_for_timeout(900)
    cdr = pg.evaluate("window.__store.cdr")
    check("صفحه‌ی CDR بدون خطا", not errs2, str(errs2[:2]))
    check("CDR ذخیره شد", isinstance(cdr, dict) and len(cdr) > 40, f"n={len(cdr or {})}")
    e = (cdr or {}).get("1794910108.189779", {})
    check("مدت و داخلی از CDR", e.get("talkSec") == 58 and e.get("extension") == "14" and e.get("disposition") == "answered", str(e))
    b.close()
print("\nFAILED:" if fails else "\nALL PASSED", fails)
sys.exit(1 if fails else 0)
