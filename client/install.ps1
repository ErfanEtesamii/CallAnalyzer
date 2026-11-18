<#
 نصب کلاینت CallAnalyzer روی کامپیوتر کاربر — بدون ادمین.
  ۱) اکستنشن را در %LOCALAPPDATA%\CallAnalyzer\ext می‌سازد (آدرس سرور و توکن از preset.json کنار این فایل)
  ۲) یک‌بار همگام‌سازی می‌کند
  ۳) همگام‌ساز خودکار را (هر ۳ دقیقه) در Task Scheduler کاربر ثبت می‌کند؛ اگر نشد، در Run کاربر (HKCU)
 بعد از آن فقط یک‌بار در Chrome «Load unpacked» لازم است. دفعه‌های بعد هر تغییری با commit روی سرور خودکار می‌رسد.
 حذف: install.ps1 -Uninstall
#>
param([switch]$Uninstall, [string]$BackendUrl = '', [string]$Token = '')
$ErrorActionPreference = 'Stop'
$Here  = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root  = Join-Path $env:LOCALAPPDATA 'CallAnalyzer'
$Ext   = Join-Path $Root 'ext'
$Task  = 'CallAnalyzerExtSync'
$RunKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'

function Remove-Autostart {
  & schtasks.exe /Delete /F /TN $Task 2>&1 | Out-Null
  Remove-ItemProperty -Path $RunKey -Name $Task -ErrorAction SilentlyContinue
}
if ($Uninstall) {
  Remove-Autostart
  Write-Host "همگام‌ساز حذف شد. پوشه‌ی $Root را می‌توانید دستی پاک کنید و اکستنشن را از chrome://extensions بردارید."
  exit 0
}

if (-not $BackendUrl -or -not $Token) {
  $pj = Join-Path $Here 'preset.json'
  if (-not (Test-Path $pj)) { Write-Host 'preset.json کنار install.ps1 نیست (یا -BackendUrl و -Token را بدهید).' -ForegroundColor Red; exit 1 }
  $p = Get-Content $pj -Raw -Encoding UTF8 | ConvertFrom-Json
  $BackendUrl = [string]$p.backendUrl; $Token = [string]$p.token
}
if ($BackendUrl -notmatch '^https?://[^/\s]+') { Write-Host 'آدرس سرور نامعتبر است.' -ForegroundColor Red; exit 1 }

if (Test-Path (Join-Path $Here 'caddy-root.crt')) {
  Write-Host 'اعتماد به گواهی سرور (اگر پنجره‌ی ویندوز آمد، Yes بزنید)…'
  & certutil.exe -user -addstore Root (Join-Path $Here 'caddy-root.crt') | Out-Null
}

New-Item -ItemType Directory -Force -Path (Join-Path $Ext 'src') | Out-Null
Copy-Item -Force (Join-Path $Here 'sync.ps1') (Join-Path $Root 'sync.ps1')
Copy-Item -Force (Join-Path $Here 'sync.vbs') (Join-Path $Root 'sync.vbs')
$preset = @{ backendUrl = $BackendUrl.TrimEnd('/'); token = $Token } | ConvertTo-Json
[IO.File]::WriteAllText((Join-Path $Ext 'src/preset.json'), $preset, (New-Object Text.UTF8Encoding($false)))

Write-Host 'دانلود اکستنشن از سرور…'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root 'sync.ps1') -Root $Root
if (-not (Test-Path (Join-Path $Ext 'manifest.json'))) {
  Write-Host "دانلود انجام نشد. آدرس/توکن و دسترسی شبکه به $BackendUrl را بررسی کنید. لاگ: $Root\sync.log" -ForegroundColor Red
  exit 1
}

# همگام‌ساز خودکار
Remove-Autostart
$vbs = Join-Path $Root 'sync.vbs'
$tr  = "wscript.exe //B //Nologo `"$vbs`""
& schtasks.exe /Create /F /SC MINUTE /MO 3 /TN $Task /TR $tr 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) { Write-Host 'همگام‌ساز خودکار ثبت شد (Task Scheduler، هر ۳ دقیقه).' }
else {
  Set-ItemProperty -Path $RunKey -Name $Task -Value "wscript.exe //B //Nologo `"$vbs`" -Loop"
  Start-Process wscript.exe -ArgumentList "//B //Nologo `"$vbs`" -Loop"
  Write-Host 'Task Scheduler مجاز نبود؛ همگام‌ساز در Run کاربر ثبت شد (با هر ورود به ویندوز).'
}

try { Set-Clipboard -Value $Ext } catch { }
Write-Host ''
Write-Host '================================================================' -ForegroundColor Green
Write-Host ' آماده است. فقط یک‌بار در Chrome:' -ForegroundColor Green
Write-Host '  ۱) chrome://extensions  ←  روشن کردن Developer mode (بالا-راست)'
Write-Host '  ۲) Load unpacked  ←  Ctrl+V (مسیر کپی شده) ←  Select Folder'
Write-Host "     مسیر: $Ext"
Write-Host ' از این به بعد هر تغییری که روی سرور می‌دهید خودکار (حداکثر چند دقیقه) می‌رسد.'
Write-Host '================================================================' -ForegroundColor Green
try { Start-Process 'chrome.exe' 'chrome://extensions' } catch { }
