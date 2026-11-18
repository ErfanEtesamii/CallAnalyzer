# Windows server setup (no Docker).  Double-click setup-windows.bat (or run as Administrator).
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$ExtId = 'pafdcnobmnjinfeefhnleopoildeipch'
$Port = 8000
$envf = Join-Path $PSScriptRoot 'backend\.env'
$venvPy = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$bin = Join-Path $PSScriptRoot 'bin'
$env:PYTHONUTF8 = '1'

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { throw 'Please run as Administrator (use setup-windows.bat).' }

function Get-Kv($k) {
  if (-not (Test-Path $envf)) { return '' }
  $l = Get-Content $envf -Encoding UTF8 | Where-Object { $_ -match "^$k=" } | Select-Object -First 1
  if ($l) { return $l.Substring($k.Length + 1) } else { return '' }
}
function Set-Kv($k, $v) {
  $lines = @()
  if (Test-Path $envf) { $lines = @(Get-Content $envf -Encoding UTF8 | Where-Object { $_ -notmatch "^$k=" }) }
  $lines += "$k=$v"
  [IO.File]::WriteAllLines($envf, [string[]]$lines, (New-Object Text.UTF8Encoding($false)))
}
function Read-Secret($prompt) {
  $s = Read-Host $prompt -AsSecureString
  return [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
}

# ---- 1) Python (3.10 - 3.13) ----
function Find-Python {
  foreach ($c in @(@('py','-3.12'), @('py','-3.13'), @('py','-3.11'), @('py','-3.10'), @('python'))) {
    $exe = Get-Command $c[0] -ErrorAction SilentlyContinue
    if (-not $exe) { continue }
    $extra = @(); if ($c.Count -gt 1) { $extra = @($c[1]) }
    try {
      $v = & $exe.Source @extra -c "import sys;print(sys.version_info[0]*100+sys.version_info[1])" 2>$null
      if ([int]$v -ge 310 -and [int]$v -le 313) { return @{ Exe = $exe.Source; Args = $extra } }
    } catch { }
  }
  foreach ($p in @('C:\Program Files\Python312\python.exe','C:\Program Files\Python313\python.exe')) {
    if (Test-Path $p) { return @{ Exe = $p; Args = @() } }
  }
  return $null
}
$py = Find-Python
if (-not $py) {
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    Write-Host '> Installing Python 3.12 with winget...'
    winget install -e --id Python.Python.3.12 --scope machine --silent --accept-package-agreements --accept-source-agreements | Out-Null
    $py = Find-Python
  }
}
if (-not $py) { throw 'Python 3.12 not found. Install it from https://www.python.org/downloads/ (tick "Add to PATH"), then run this again.' }

# ---- 2) ffmpeg -> bin\ffmpeg.exe ----
if (-not (Test-Path (Join-Path $bin 'ffmpeg.exe'))) {
  $ff = Get-Command ffmpeg -ErrorAction SilentlyContinue
  if (-not $ff -and (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Host '> Installing ffmpeg with winget...'
    winget install -e --id Gyan.FFmpeg --silent --accept-package-agreements --accept-source-agreements | Out-Null
    $found = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages","$env:ProgramFiles\WinGet\Packages" -Recurse -Filter ffmpeg.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { $ff = $found }
  }
  if ($ff) {
    New-Item -ItemType Directory -Force $bin | Out-Null
    Copy-Item ($(if ($ff.Source) { $ff.Source } else { $ff.FullName })) (Join-Path $bin 'ffmpeg.exe') -Force
  }
}
if (-not (Test-Path (Join-Path $bin 'ffmpeg.exe'))) {
  throw 'ffmpeg not found. Download ffmpeg-release-essentials.zip from https://www.gyan.dev/ffmpeg/builds/ , copy bin\ffmpeg.exe into the "bin" folder next to this script, then run this again.'
}

# ---- 3) settings (.env) ----
if (-not (Test-Path $envf)) { Copy-Item "$envf.example" $envf }
$defIp = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -match '^(192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)' } | Select-Object -First 1).IPAddress
$addr = Read-Host "Server IP that the PCs will use [$defIp]"; if (-not $addr) { $addr = $defIp }
$token = Get-Kv 'API_TOKEN'
if ($token.Length -lt 16) {
  $b = New-Object byte[] 24; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
  $token = ($b | ForEach-Object { $_.ToString('x2') }) -join ''
}
$key = Get-Kv 'ANTHROPIC_API_KEY'; if (-not $key) { $key = Read-Secret 'ANTHROPIC_API_KEY' }
Write-Host 'Speech-to-text:  1) OpenAI (needs key)   2) Local faster-whisper (audio stays on the server)'
$ch = Read-Host 'Choice [2]'; if (-not $ch) { $ch = '2' }
if ($ch -eq '1') {
  $oai = Get-Kv 'OPENAI_API_KEY'; if (-not $oai) { $oai = Read-Secret 'OPENAI_API_KEY' }
  Set-Kv 'OPENAI_API_KEY' $oai; Set-Kv 'STT_PROVIDER' 'openai'; $whisper = $false
} else { Set-Kv 'STT_PROVIDER' 'faster_whisper'; $whisper = $true }
Set-Kv 'API_TOKEN' $token
Set-Kv 'ANTHROPIC_API_KEY' $key
Set-Kv 'ALLOWED_ORIGINS' "chrome-extension://$ExtId"

# ---- 4) virtualenv + packages ----
Write-Host '> Installing packages (first time takes a few minutes)...'
if (-not (Test-Path $venvPy)) { & $py.Exe @($py.Args) -m venv (Join-Path $PSScriptRoot '.venv') }
& $venvPy -m pip install --quiet --upgrade pip
& $venvPy -m pip install --quiet -r (Join-Path $PSScriptRoot 'backend\requirements.txt')
if ($whisper) { & $venvPy -m pip install --quiet faster-whisper }

# ---- 5) auto-start at boot (Scheduled Task) + firewall ----
$run = Join-Path $PSScriptRoot 'run-server.cmd'
@"
@echo off
set PATH=$bin;%PATH%
cd /d "$PSScriptRoot\backend"
"$venvPy" -m uvicorn app.main:app --host 0.0.0.0 --port $Port >> "$PSScriptRoot\server.log" 2>&1
"@ | Set-Content -Encoding ASCII $run

Stop-ScheduledTask -TaskName CallAnalyzer -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName CallAnalyzer -Confirm:$false -ErrorAction SilentlyContinue
$action = New-ScheduledTaskAction -Execute ('"' + $run + '"')
$trigger = New-ScheduledTaskTrigger -AtStartup
$set = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable
Register-ScheduledTask -TaskName CallAnalyzer -Action $action -Trigger $trigger -Settings $set -User SYSTEM -RunLevel Highest | Out-Null

Remove-NetFirewallRule -DisplayName 'CallAnalyzer' -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName 'CallAnalyzer' -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow -RemoteAddress LocalSubnet | Out-Null
Start-ScheduledTask -TaskName CallAnalyzer

# ---- 6) health check + client package ----
$ok = $false
for ($i = 0; $i -lt 30 -and -not $ok; $i++) {
  Start-Sleep 2
  try { $ok = (Invoke-WebRequest "http://localhost:$Port/health" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200 } catch { }
}
if ($ok) { Write-Host 'OK: server is running.' } else { Write-Host "WARNING: no response. See server.log" }

Push-Location (Join-Path $PSScriptRoot 'backend'); & $venvPy scripts\doctor.py; Pop-Location
& $venvPy (Join-Path $PSScriptRoot 'scripts\make_client.py') --url "http://${addr}:$Port" --token $token
Write-Host ''
Write-Host 'DONE. Give dist\CallAnalyzer-Client.zip to every PC and run install.bat inside it.'
