<#
 Local dev server launcher (Windows PowerShell 5.1 / 7). Run from anywhere in the repo.
   .\scripts\local\start-local.ps1                 # DB/Redis -> migrate -> backend -> worker + beat -> frontend
   .\scripts\local\start-local.ps1 -SkipInstall    # skip dependency install (faster restart)
 Ports: backend 8001 / frontend 3001 / resume portal 3002 / DB 5544 / Redis 6389
 NOTE: this file is ASCII-only on purpose (Windows PowerShell 5.1 misreads UTF-8 without BOM).
#>
param([switch]$SkipInstall, [switch]$NoApply)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Be = Join-Path $Root "backend"
$Fe = Join-Path $Root "frontend"
$Ap = Join-Path $Root "frontend-apply"
$VenvPy = Join-Path $Be ".venv\Scripts\python.exe"

function Step([string]$m) { Write-Host ""; Write-Host "==> $m" -ForegroundColor Cyan }

Step "0. Pre-flight (docker / node / npm)"
foreach ($c in @("docker", "node", "npm")) {
  if (-not (Get-Command $c -ErrorAction SilentlyContinue)) { throw "$c is not installed." }
}
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker Desktop is not running." }

Step "1. Virtualenv and dependencies"
if (-not (Test-Path $VenvPy)) {
  Write-Host "creating venv"
  python -m venv (Join-Path $Be ".venv")
  if ($LASTEXITCODE -ne 0) { throw "python -m venv failed (is Python installed?)" }
}
if (-not $SkipInstall) {
  & $VenvPy -m pip install -q -r (Join-Path $Be "requirements.txt")
  if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
  foreach ($d in @($Fe, $Ap)) {
    if (Test-Path $d) {
      # always run: installs newly added packages (e.g. recharts) and is fast when already up to date
      Push-Location $d; npm install --no-audit --no-fund; Pop-Location
    }
  }
}
$beEnv = Join-Path $Be ".env"
if (-not (Test-Path $beEnv)) {
  Copy-Item (Join-Path $Be ".env.example") $beEnv
  Write-Host "created backend\.env from .env.example - change JWT_SECRET_KEY" -ForegroundColor Yellow
}
$feEnv = Join-Path $Fe ".env.local"
if (-not (Test-Path $feEnv)) {
  Set-Content -Path $feEnv -Value "NEXT_PUBLIC_API_BASE_URL=http://localhost:8001/api/v1" -Encoding Ascii
}

Step "2. DB (pgvector) and Redis containers"
Push-Location $Be
docker compose up -d
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "docker compose up failed" }
Pop-Location
for ($i = 0; $i -lt 30; $i++) {
  docker exec final-project-db pg_isready -U final_app *> $null
  if ($LASTEXITCODE -eq 0) { break }
  Start-Sleep -Seconds 1
}

Step "3. DB migration (alembic upgrade head)"
Push-Location $Be
$env:PYTHONIOENCODING = "utf-8"
& $VenvPy -m alembic upgrade head
$mig = $LASTEXITCODE
Pop-Location
if ($mig -ne 0) { throw "migration failed" }

Step "4. Start backend(8001), worker, beat (AI resume screening), frontend(3001), resume portal(3002) in separate windows"
function Launch([string]$title, [string]$dir, [string]$cmd) {
  $full = "`$host.UI.RawUI.WindowTitle = '$title'; `$env:PYTHONIOENCODING = 'utf-8'; Set-Location '$dir'; $cmd"
  $enc = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($full))
  Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoExit", "-NoProfile", "-EncodedCommand", $enc)
}
Launch "backend-8001" $Be "& '$VenvPy' -m uvicorn app.main:app --host 127.0.0.1 --port 8001"
Launch "worker" $Be "& '$VenvPy' -m celery -A app.services.celery_app worker --concurrency=1 --pool=solo -Q ai_pipeline"
New-Item -ItemType Directory -Force -Path (Join-Path $Be "var") | Out-Null
Launch "beat" $Be "& '$VenvPy' -m celery -A app.services.celery_app beat --loglevel=info -s var/celerybeat-schedule"
Launch "frontend-3001" $Fe "npm run dev -- --port 3001"
if ((-not $NoApply) -and (Test-Path $Ap)) {
  Launch "apply-3002" $Ap "npm run dev -- --port 3002"
}

Step "5. Health check (waiting for backend)"
$ok = $false
for ($i = 0; $i -lt 60; $i++) {
  try {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:8001/api/v1/health" -TimeoutSec 3
    if ($r.status -eq "ok") { $ok = $true; break }
  } catch { }
  Start-Sleep -Seconds 2
}
if ($ok) { Write-Host "backend OK" -ForegroundColor Green }
else { Write-Host "backend not responding - check the backend-8001 window log" -ForegroundColor Red }

Write-Host ""
Write-Host "Mock interview web app : http://localhost:3001  (sign up at /register)"
Write-Host "Resume portal          : http://localhost:3002"
Write-Host "API docs (Swagger)     : http://localhost:8001/docs"
Write-Host "Health check           : http://localhost:8001/api/v1/health"
Write-Host "Stop                   : .\scripts\local\stop-local.ps1"
