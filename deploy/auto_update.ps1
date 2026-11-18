<#
 CallAnalyzer server auto-update (Windows). Run by a scheduled task every 2 minutes (see install_autoupdate.bat).

 What it does, in order:
   1. git: fetch origin/<Branch>; if the server checkout is clean and behind, fast-forward it (never overwrites local edits).
      Works without git too (-NoGit, or no .git folder): then it just reacts to files you edited on the server.
   2. Fingerprints (SHA-256) the files that matter and compares with what was last deployed:
        extension/**             -> nothing to do. The backend serves extension files straight from disk, and every
                                    user PC syncs them by itself (client\sync.ps1). No restart.
        rubric/**                -> POST /api/v1/rubric/reload (hot reload, no restart)
        backend/requirements.txt -> pip install -r
        backend/app/**, config/**, backend/.env, domain_vocab.txt -> pre-flight check, restart service, wait for /health
   3. If the pre-flight check or the health check fails after a pull, it rolls the checkout back to the previous commit,
      restarts the old code and remembers the bad commit (so it is not retried until a newer commit arrives).
 First run only records a baseline (it assumes the running service already matches the files on disk).
 State: <project>\logs\autoupdate-state.json    Log: <project>\logs\autoupdate.log
#>
param(
  [string]$Branch      = 'main',
  [string]$ServiceName = 'CallAnalyzer',
  [int]$Port           = 8000,
  [switch]$NoGit,
  [switch]$RunTests,                 # also run backend pytest as part of the pre-flight check
  [string]$PythonExe   = '',         # default: <project>\.venv\Scripts\python.exe
  [string]$NssmExe     = '',         # default: <project>\deploy\nssm.exe
  [string]$Git         = 'git'
)
$ErrorActionPreference = 'Stop'

$Project = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Backend = Join-Path $Project 'backend'
$LogDir  = Join-Path $Project 'logs'
$LogFile = Join-Path $LogDir 'autoupdate.log'
$StateFile = Join-Path $LogDir 'autoupdate-state.json'
if (-not $PythonExe) { $PythonExe = Join-Path $Project '.venv/Scripts/python.exe' }
if (-not $NssmExe)   { $NssmExe   = Join-Path $Project 'deploy/nssm.exe' }
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }

function Write-Log([string]$msg) {
  try {
    if ((Test-Path $LogFile) -and (Get-Item $LogFile).Length -gt 500KB) { Set-Content $LogFile (Get-Content $LogFile -Tail 500) -Encoding UTF8 }
    Add-Content $LogFile ("{0:yyyy-MM-dd HH:mm:ss}  {1}" -f (Get-Date), $msg) -Encoding UTF8
  } catch { }
}

function Invoke-Git([string[]]$gitArgs) {
  # safe.directory=*: the task runs as SYSTEM but the folder may belong to another user
  $out = & $Git -c safe.directory=* -C $Project @gitArgs 2>&1
  if ($LASTEXITCODE -ne 0) { throw ("git {0} failed: {1}" -f ($gitArgs -join ' '), ($out -join ' ')) }
  return ($out -join "`n").Trim()
}

function Get-Fingerprint([string[]]$files) {
  $sb = New-Object Text.StringBuilder
  foreach ($f in ($files | Sort-Object)) {
    [void]$sb.Append($f.Substring($Project.Length)).Append(':').Append((Get-FileHash -Algorithm SHA256 -LiteralPath $f).Hash).Append("`n")
  }
  $sha = [Security.Cryptography.SHA256]::Create()
  return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($sb.ToString()))) -replace '-', '')
}
function Get-Files([string]$dir, [string[]]$exclude) {
  if (-not (Test-Path $dir)) { return @() }
  return @(Get-ChildItem -LiteralPath $dir -Recurse -File | Where-Object {
    $p = $_.FullName; -not ($exclude | Where-Object { $p -like "*$_*" })
  } | ForEach-Object { $_.FullName })
}
function Get-State {
  if (Test-Path $StateFile) { try { return Get-Content $StateFile -Raw | ConvertFrom-Json } catch { } }
  return [pscustomobject]@{ backend = ''; rubric = ''; req = ''; badCommit = '' }
}
function Save-State($s) { $s | ConvertTo-Json | Set-Content $StateFile -Encoding UTF8 }

function Get-Current {
  $codeFiles = @()
  $codeFiles += Get-Files (Join-Path $Backend 'app') @('__pycache__', '.pyc')
  $codeFiles += Get-Files (Join-Path $Project 'config') @()
  foreach ($x in @((Join-Path $Backend '.env'), (Join-Path $Backend 'domain_vocab.txt'), (Join-Path $Backend 'requirements.txt'))) { if (Test-Path $x) { $codeFiles += $x } }
  $req = Join-Path $Backend 'requirements.txt'
  return [pscustomobject]@{
    backend = Get-Fingerprint $codeFiles
    rubric  = Get-Fingerprint (Get-Files (Join-Path $Project 'rubric') @())
    req     = $(if (Test-Path $req) { (Get-FileHash -Algorithm SHA256 -LiteralPath $req).Hash } else { '' })
  }
}

function Wait-Healthy([int]$seconds = 60) {
  $until = (Get-Date).AddSeconds($seconds)
  while ((Get-Date) -lt $until) {
    try { $r = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 3; if ($r.ok) { return $true } } catch { }
    Start-Sleep -Seconds 2
  }
  return $false
}
function Restart-Backend {
  Write-Log "restarting service $ServiceName"
  & $NssmExe restart $ServiceName 2>&1 | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "nssm restart failed (exit $LASTEXITCODE)" }
  return (Wait-Healthy 60)
}
function Test-Preflight {
  & $PythonExe -m compileall -q (Join-Path $Backend 'app') 2>&1 | Out-Null
  if ($LASTEXITCODE -ne 0) { Write-Log 'pre-flight FAILED: python syntax error in backend/app'; return $false }
  if ($RunTests) {
    Push-Location $Backend
    try { & $PythonExe -m pytest -q -x 2>&1 | Out-Null; $code = $LASTEXITCODE } finally { Pop-Location }
    if ($code -ne 0) { Write-Log 'pre-flight FAILED: backend tests'; return $false }
  }
  return $true
}
function Invoke-RubricReload {
  $envFile = Join-Path $Backend '.env'
  $tok = ''
  if (Test-Path $envFile) { foreach ($l in Get-Content $envFile) { if ($l -match '^\s*API_TOKEN\s*=\s*(.+?)\s*$') { $tok = $Matches[1].Trim('"').Trim("'") } } }
  if (-not $tok) { return $false }
  try { $null = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$Port/api/v1/rubric/reload" -Headers @{ Authorization = "Bearer $tok" } -TimeoutSec 20; return $true } catch { return $false }
}

# ---- single instance ----
$created = $false
$mutex = New-Object System.Threading.Mutex($true, 'Global\CallAnalyzerAutoUpdate', [ref]$created)
if (-not $created) { exit 0 }
try {
  $state = Get-State
  $useGit = (-not $NoGit) -and (Test-Path (Join-Path $Project '.git'))
  $before = ''; $pulledFrom = ''

  # first run: the running service is assumed to match the files on disk RIGHT NOW (before any pull)
  if (-not $state.backend) {
    $base = Get-Current
    $state = [pscustomobject]@{ backend = $base.backend; rubric = $base.rubric; req = $base.req; badCommit = '' }
    Save-State $state; Write-Log 'baseline recorded (first run)'
  }

  # 1) git
  if ($useGit) {
    try {
      $dirty = Invoke-Git @('status', '--porcelain', '--untracked-files=no')
      Invoke-Git @('fetch', '--quiet', 'origin', $Branch) | Out-Null
      $before = Invoke-Git @('rev-parse', 'HEAD')
      $remote = Invoke-Git @('rev-parse', "origin/$Branch")
      if ($before -ne $remote) {
        if ($state.badCommit -eq $remote) { }  # known-bad commit: wait for a newer one
        elseif ($dirty) { Write-Log 'checkout has local modifications: not pulling (commit or discard them on the server)' }
        else {
          & $Git -c safe.directory=* -C $Project merge-base --is-ancestor $before $remote 2>&1 | Out-Null
          if ($LASTEXITCODE -ne 0) { Write-Log 'server checkout has diverged from origin: not pulling' }
          else {
            Invoke-Git @('merge', '--ff-only', "origin/$Branch") | Out-Null
            $pulledFrom = $before
            Write-Log ("pulled {0} -> {1}" -f $before.Substring(0, 8), $remote.Substring(0, 8))
          }
        }
      }
    } catch { Write-Log ("git step skipped: " + $_.Exception.Message) }
  }

  # 2) what changed?
  $cur = Get-Current
  $backendChanged = $cur.backend -ne $state.backend
  $rubricChanged  = $cur.rubric  -ne $state.rubric
  $reqChanged     = $cur.req     -ne $state.req
  if ($pulledFrom -and -not ($backendChanged -or $rubricChanged)) { Write-Log 'only the extension (or docs) changed: clients will sync it; no restart needed' }
  if (-not ($backendChanged -or $rubricChanged -or $reqChanged)) { exit 0 }

  $ok = $true; $restarted = $false
  try {
    if ($reqChanged) {
      Write-Log 'requirements.txt changed: pip install'
      & $PythonExe -m pip install -q -r (Join-Path $Backend 'requirements.txt') 2>&1 | Out-Null
      if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }
    }
    if ($backendChanged -or $reqChanged) {
      if (-not (Test-Preflight)) { throw 'pre-flight check failed' }
      $restarted = $true
      if (-not (Restart-Backend)) { throw 'service did not become healthy after restart' }
      Write-Log 'backend restarted and healthy'
    } elseif ($rubricChanged) {
      if (Invoke-RubricReload) { Write-Log 'rubric hot-reloaded' }
      else { Write-Log 'rubric reload via API failed: restarting service'; $restarted = $true; if (-not (Restart-Backend)) { throw 'service did not become healthy after restart' } }
    }
  } catch {
    $ok = $false
    Write-Log ("DEPLOY FAILED: " + $_.Exception.Message)
  }

  if ($ok) {
    $state = [pscustomobject]@{ backend = $cur.backend; rubric = $cur.rubric; req = $cur.req; badCommit = '' }
    Save-State $state
  } elseif ($pulledFrom) {
    # roll back to the previous commit and bring the old code back up
    try {
      $bad = Invoke-Git @('rev-parse', 'HEAD')
      Invoke-Git @('reset', '--hard', $pulledFrom) | Out-Null
      if ($reqChanged) { & $PythonExe -m pip install -q -r (Join-Path $Backend 'requirements.txt') 2>&1 | Out-Null }
      if ($restarted) { $null = Restart-Backend }
      $state.badCommit = $bad
      Save-State $state
      Write-Log ("rolled back to {0}; commit {1} is marked bad until a newer commit arrives" -f $pulledFrom.Substring(0, 8), $bad.Substring(0, 8))
    } catch { Write-Log ("ROLLBACK FAILED, manual action needed: " + $_.Exception.Message) }
  } else {
    Write-Log 'no git history to roll back to (files were edited in place): fix the files and the next run retries'
  }
} catch {
  Write-Log ("unexpected error: " + $_.Exception.Message)
} finally { $mutex.ReleaseMutex(); $mutex.Dispose() }
