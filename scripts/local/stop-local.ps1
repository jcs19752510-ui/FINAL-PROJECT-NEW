<# 로컬 서버 종료. -Down 을 주면 DB/Redis 컨테이너도 내립니다(데이터 볼륨은 유지). #>
param([switch]$Down)
foreach ($port in 8001, 3001, 3002) {
  Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue; Write-Host "포트 $port 종료" }
}
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match "celery" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host "celery 워커 종료" }
if ($Down) { Push-Location (Join-Path (Resolve-Path "$PSScriptRoot\..\..").Path "backend"); docker compose down; Pop-Location }
