# Stop local dev servers. Add -Down to also stop the DB/Redis containers (data volumes are kept).
# ASCII-only on purpose (Windows PowerShell 5.1 misreads UTF-8 without BOM).
param([switch]$Down)
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
foreach ($port in @(8001, 3001, 3002)) {
  $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
  foreach ($c in $conns) {
    Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
    Write-Host "stopped port $port"
  }
}
$procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match "celery" }
foreach ($p in $procs) {
  Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
  Write-Host "stopped celery worker"
}
if ($Down) {
  Push-Location (Join-Path $Root "backend")
  docker compose down
  Pop-Location
}
