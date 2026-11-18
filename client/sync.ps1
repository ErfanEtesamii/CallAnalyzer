<#
 همگام‌ساز اکستنشن CallAnalyzer (بدون نیاز به ادمین).
 هر چند دقیقه یک‌بار (Task Scheduler کاربر) اجرا می‌شود، فهرست فایل‌های اکستنشن را از بک‌اند می‌گیرد، فقط فایل‌های
 تغییرکرده را دانلود و در پوشه‌ی اکستنشن جایگزین می‌کند. manifest.json همیشه آخر از همه عوض می‌شود؛ خود اکستنشن تغییر نسخه‌ی
 manifest را می‌بیند و reload می‌شود (src/lib/updater.js). بدون حالت/state: هر بار با هش فایل‌ها مقایسه می‌کند، پس خودترمیم است.
 آدرس سرور و توکن از <Root>\ext\src\preset.json خوانده می‌شود و هرگز از سرور دریافت یا بازنویسی نمی‌شود.
#>
param(
  [string]$Root = (Join-Path $env:LOCALAPPDATA 'CallAnalyzer'),
  [switch]$Loop,
  [int]$LoopSeconds = 180
)
$ErrorActionPreference = 'Stop'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

$Ext      = Join-Path $Root 'ext'
$Stage    = Join-Path $Root 'stage'
$LogFile  = Join-Path $Root 'sync.log'
$LastFile = Join-Path $Root 'last-status.txt'

function Write-Log([string]$msg) {
  try {
    if (-not (Test-Path $Root)) { New-Item -ItemType Directory -Force -Path $Root | Out-Null }
    if ((Test-Path $LogFile) -and (Get-Item $LogFile).Length -gt 200KB) {
      $tail = Get-Content $LogFile -Tail 200; Set-Content -Path $LogFile -Value $tail -Encoding UTF8
    }
    Add-Content -Path $LogFile -Value ("{0:yyyy-MM-dd HH:mm:ss}  {1}" -f (Get-Date), $msg) -Encoding UTF8
  } catch { }
}
# پیام تکراری (مثلاً «سرور در دسترس نیست» هر ۳ دقیقه) فقط یک‌بار لاگ می‌شود
function Write-LogOnChange([string]$msg) {
  $prev = ''
  if (Test-Path $LastFile) { $prev = (Get-Content $LastFile -Raw -ErrorAction SilentlyContinue) }
  if ($prev -ne $msg) { Write-Log $msg; try { Set-Content -Path $LastFile -Value $msg -Encoding UTF8 -NoNewline } catch { } }
}

function Get-Sha256([string]$path) { (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant() }

function Test-SafeRel([string]$rel) {
  # فقط manifest.json و فایل‌های زیر src/ و assets/ ؛ بدون .. و مسیر مطلق
  return ($rel -cmatch '^(manifest\.json|(src|assets)/[^\\:*?"<>|]+)$') -and ($rel -notmatch '\.\.') -and ($rel -ne 'src/preset.json')
}

function Move-WithRetry([string]$from, [string]$to) {
  $dir = Split-Path -Parent $to
  if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
  for ($i = 1; $i -le 5; $i++) {
    try { Move-Item -LiteralPath $from -Destination $to -Force; return } catch { if ($i -eq 5) { throw }; Start-Sleep -Milliseconds 400 }
  }
}

function Invoke-Sync {
  $presetPath = Join-Path $Ext 'src/preset.json'
  if (-not (Test-Path $presetPath)) { Write-LogOnChange 'preset.json پیدا نشد؛ install-client.bat را دوباره اجرا کنید.'; return 'nopreset' }
  $p = Get-Content $presetPath -Raw -Encoding UTF8 | ConvertFrom-Json
  if (-not $p.backendUrl -or -not $p.token) { Write-LogOnChange 'preset.json ناقص است (backendUrl/token).'; return 'nopreset' }
  $base = ([string]$p.backendUrl).TrimEnd('/')
  $hdr  = @{ Authorization = "Bearer $($p.token)" }

  try { $idx = Invoke-RestMethod -Uri "$base/api/v1/ext/manifest" -Headers $hdr -TimeoutSec 20 }
  catch {
    $code = $null; try { $code = [int]$_.Exception.Response.StatusCode } catch { }
    if ($code -eq 401) { Write-LogOnChange 'توکن نامعتبر است (401). توکن در preset.json با API_TOKEN سرور یکی نیست.'; return 'auth' }
    Write-LogOnChange ("سرور در دسترس نیست: " + $_.Exception.Message); return 'offline'
  }

  $wanted = @{}
  foreach ($f in $idx.files) { if (Test-SafeRel $f.path) { $wanted[$f.path] = $f } else { Write-Log ("مسیر نامعتبر نادیده گرفته شد: " + $f.path) } }
  if (-not $wanted.ContainsKey('manifest.json')) { Write-LogOnChange 'فهرست سرور manifest.json ندارد؛ همگام‌سازی انجام نشد.'; return 'badindex' }

  $need = @()
  foreach ($rel in $wanted.Keys) {
    $local = Join-Path $Ext $rel
    if (-not (Test-Path -LiteralPath $local) -or (Get-Sha256 $local) -ne $wanted[$rel].sha256) { $need += $rel }
  }
  $extra = @()
  foreach ($sub in 'src', 'assets') {
    $d = Join-Path $Ext $sub
    if (Test-Path $d) {
      Get-ChildItem -LiteralPath $d -Recurse -File | ForEach-Object {
        $rel = ($_.FullName.Substring($Ext.Length + 1) -replace '\\', '/')
        if ($rel -ne 'src/preset.json' -and -not $wanted.ContainsKey($rel)) { $extra += $_.FullName }
      }
    }
  }
  if ($need.Count -eq 0 -and $extra.Count -eq 0) { Write-LogOnChange ("به‌روز است: " + $idx.version); return 'current' }

  # ۱) همه‌ی فایل‌های لازم در پوشه‌ی موقت دانلود و راستی‌آزمایی می‌شوند؛ اگر یکی خراب بود هیچ فایلی عوض نمی‌شود.
  if (Test-Path $Stage) { Remove-Item -LiteralPath $Stage -Recurse -Force }
  New-Item -ItemType Directory -Force -Path $Stage | Out-Null
  foreach ($rel in $need) {
    $tmp = Join-Path $Stage $rel
    $dir = Split-Path -Parent $tmp
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    Invoke-WebRequest -Uri ("$base/api/v1/ext/file/" + $rel) -Headers $hdr -OutFile $tmp -UseBasicParsing -TimeoutSec 60 | Out-Null
    if ((Get-Sha256 $tmp) -ne $wanted[$rel].sha256) { throw "هش فایل $rel با فهرست سرور نمی‌خواند (وسط انتشار؟). بعداً دوباره تلاش می‌شود." }
  }
  # ۲) جایگزینی: manifest.json آخر از همه تا اکستنشن وسط کار reload نشود
  foreach ($rel in ($need | Where-Object { $_ -ne 'manifest.json' })) { Move-WithRetry (Join-Path $Stage $rel) (Join-Path $Ext $rel) }
  foreach ($x in $extra) { try { Remove-Item -LiteralPath $x -Force } catch { Write-Log ("حذف نشد: $x") } }
  if ($need -contains 'manifest.json') { Move-WithRetry (Join-Path $Stage 'manifest.json') (Join-Path $Ext 'manifest.json') }
  Remove-Item -LiteralPath $Stage -Recurse -Force -ErrorAction SilentlyContinue
  Write-LogOnChange ("به‌روزرسانی شد → " + $idx.version + "  (فایل تغییرکرده: " + $need.Count + "، حذف‌شده: " + $extra.Count + ")")
  return 'updated'
}

# فقط یک نمونه هم‌زمان
$created = $false
$mutex = New-Object System.Threading.Mutex($true, 'Local\CallAnalyzerExtSync', [ref]$created)
if (-not $created) { exit 0 }
try {
  do {
    try { $null = Invoke-Sync } catch { Write-Log ("خطا: " + $_.Exception.Message) }
    if ($Loop) { Start-Sleep -Seconds $LoopSeconds }
  } while ($Loop)
} finally { $mutex.ReleaseMutex(); $mutex.Dispose() }
