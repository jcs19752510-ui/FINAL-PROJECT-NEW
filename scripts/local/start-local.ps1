<#
 로컬 개발 서버 일괄 기동 (Windows PowerShell). 저장소 어디서 실행해도 됩니다.
   .\scripts\local\start-local.ps1            # 전체 기동 (DB/Redis → 마이그레이션 → 백엔드 → 워커 → 프런트)
   .\scripts\local\start-local.ps1 -SkipInstall   # 의존성 설치 단계 생략(재기동 시 빠름)
 포트: 백엔드 8001 / 프런트 3001 / 이력서 포털 3002 / DB 5544 / Redis 6389 (서버띄우기접속방법.md 와 동일)
 각 서버는 별도 PowerShell 창으로 뜨며, 종료는 해당 창에서 Ctrl+C 또는 stop-local.ps1.
#>
param([switch]$SkipInstall, [switch]$NoApply)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path "$PSScriptRoot\..\..").Path
$Be = Join-Path $Root "backend"; $Fe = Join-Path $Root "frontend"; $Ap = Join-Path $Root "frontend-apply"
$Py = Join-Path $Be ".venv\Scripts\python.exe"
function Step($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }

Step "0. 사전 점검 (docker / python / node)"
foreach ($c in "docker", "node", "npm") { if (-not (Get-Command $c -ErrorAction SilentlyContinue)) { throw "$c 가 설치되어 있지 않습니다." } }
docker info *> $null; if ($LASTEXITCODE -ne 0) { throw "Docker Desktop 이 실행 중이 아닙니다." }

Step "1. 가상환경 / 의존성"
if (-not (Test-Path $Py)) { Write-Host "venv 생성"; python -m venv (Join-Path $Be ".venv") }
if (-not $SkipInstall) {
  & $Py -m pip install -q -r (Join-Path $Be "requirements.txt")          # pypdf 포함 (이력서 맞춤 면접)
  foreach ($d in $Fe, $Ap) { if ((Test-Path $d) -and -not (Test-Path (Join-Path $d "node_modules"))) { Push-Location $d; npm install; Pop-Location } }
}
if (-not (Test-Path (Join-Path $Be ".env"))) { Copy-Item (Join-Path $Be ".env.example") (Join-Path $Be ".env"); Write-Host "backend\.env 를 .env.example 에서 생성했습니다. JWT_SECRET_KEY 를 바꾸세요." -ForegroundColor Yellow }
$envLocal = Join-Path $Fe ".env.local"
if (-not (Test-Path $envLocal)) { "NEXT_PUBLIC_API_BASE_URL=http://localhost:8001/api/v1" | Set-Content $envLocal -Encoding ascii }

Step "2. DB(pgvector) · Redis 컨테이너"
Push-Location $Be; docker compose up -d; Pop-Location
for ($i = 0; $i -lt 30; $i++) { docker exec final-project-db pg_isready -U final_app *> $null; if ($LASTEXITCODE -eq 0) { break }; Start-Sleep 1 }

Step "3. DB 마이그레이션 (alembic upgrade head)"
Push-Location $Be; $env:PYTHONIOENCODING = "utf-8"; & $Py -m alembic upgrade head; if ($LASTEXITCODE -ne 0) { throw "마이그레이션 실패" }; Pop-Location

Step "4. 백엔드(8001) / 워커 / 프런트(3001) / 이력서 포털(3002) 별도 창 기동"
function Launch($title, $dir, $cmd) {
  Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$host.UI.RawUI.WindowTitle='$title'; `$env:PYTHONIOENCODING='utf-8'; Set-Location '$dir'; $cmd"
}
Launch "backend-8001"  $Be "& '$Py' -m uvicorn app.main:app --host 127.0.0.1 --port 8001"
Launch "worker"        $Be "& '$Py' -m celery -A app.services.celery_app worker --concurrency=1 --pool=solo -Q ai_pipeline"
Launch "frontend-3001" $Fe "npm run dev -- --port 3001"
if (-not $NoApply -and (Test-Path $Ap)) { Launch "apply-3002" $Ap "npm run dev -- --port 3002" }

Step "5. 헬스체크 (백엔드 기동 대기)"
$ok = $false
for ($i = 0; $i -lt 60; $i++) { try { if ((Invoke-RestMethod http://127.0.0.1:8001/api/v1/health).status -eq "ok") { $ok = $true; break } } catch {}; Start-Sleep 2 }
if ($ok) { Write-Host "백엔드 정상" -ForegroundColor Green } else { Write-Host "백엔드 응답 없음 - backend-8001 창의 로그를 확인하세요." -ForegroundColor Red }
Write-Host @"

접속 주소
  모의면접 웹앱      http://localhost:3001      (회원가입: /register)
  이력서 제출 포털   http://localhost:3002
  API 문서(Swagger)  http://localhost:8001/docs
  헬스체크           http://localhost:8001/api/v1/health
※ 이력서 맞춤 면접: 지원자는 먼저 PDF(스캔본 아님) 이력서를 제출해야 면접을 시작할 수 있습니다.
"@
