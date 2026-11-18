"""پیش‌نمایش پنل بدون اکستنشن: extension/dev/preview.html را از src/sidepanel.html می‌سازد.
باز کنید: dev/preview.html?theme=dark&tab=queue  (tab: analysis|queue|history|compare)  و ?empty=1 برای حالت خالی."""
from pathlib import Path

ext = Path(__file__).resolve().parent.parent / "extension"
html = (ext / "src/sidepanel.html").read_text(encoding="utf-8")
html = html.replace('href="sidepanel.css"', 'href="../src/sidepanel.css"')
html = html.replace('<script src="lib/settings.js">', '<script src="mock-chrome.js"></script>\n<script src="../src/lib/settings.js">')
html = html.replace('src="lib/csv.js"', 'src="../src/lib/csv.js"')
html = html.replace('<script src="sidepanel.js">', '<script>if(window.__tab)addEventListener("DOMContentLoaded",()=>{});</script>\n<script src="../src/sidepanel.js">')
html += '\n<script>if(window.__tab){setTimeout(()=>document.querySelector("#tab-"+window.__tab)?.click(),50)}</script>\n'
(ext / "dev/preview.html").write_text(html, encoding="utf-8")
print("dev/preview.html")
