<#
 Delete ALL candidate accounts + their interview data from the LOCAL dev DB (and resume PDFs / TTS audio).
 Keeps recruiter/admin accounts, question bank, coding problems, rubric templates.
   .\scripts\local\reset-candidates.ps1            # DRY-RUN (default): shows counts, deletes nothing
   .\scripts\local\reset-candidates.ps1 -Apply     # real delete (asks you to type DELETE)
   -Force skips the prompt. -Container / -Db / -DbUser override defaults.
 ASCII-only on purpose (Windows PowerShell 5.1 misreads UTF-8 without BOM).
#>
param(
  [switch]$Apply,
  [switch]$Force,
  [string]$Container = "final-project-db",
  [string]$Db = "final_project",
  [string]$DbUser = "final_app"
)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Sql = Join-Path $PSScriptRoot "reset-candidates.sql"
$VarDir = Join-Path $Root "backend\var"

function RunSql([string]$mode) {
  Get-Content -Raw -Path $Sql | docker exec -i $Container psql -U $DbUser -d $Db -v "mode=$mode"
  if ($LASTEXITCODE -ne 0) { throw "psql failed (nothing was committed)" }
}

$running = docker ps --format "{{.Names}}"
if ($running -notcontains $Container) { throw "container '$Container' is not running (start the servers first)" }
Write-Host "target: container=$Container db=$Db user=$DbUser"

Write-Host "=== DRY-RUN (counts) ==="
RunSql "dry"
if (-not $Apply) {
  Write-Host ""
  Write-Host "Nothing deleted. Re-run with -Apply to delete."
  return
}

if (-not $Force) {
  Write-Host ""
  Write-Host "WARNING: this permanently deletes the data above (irreversible)." -ForegroundColor Yellow
  $ans = Read-Host "Type DELETE to continue"
  if ($ans -cne "DELETE") { Write-Host "aborted"; return }
}

# collect resume file paths BEFORE deleting rows; delete files only after the DB commit succeeded
$files = docker exec -i $Container psql -U $DbUser -d $Db -At -c "SELECT file_path FROM resume_applications WHERE candidate_id IN (SELECT id FROM users WHERE role='candidate')"
if ($LASTEXITCODE -ne 0) { throw "could not read resume paths" }

Write-Host "=== APPLY ==="
RunSql "apply"

$n = 0
foreach ($f in @($files)) {
  if ($f -and (Test-Path -LiteralPath $f -PathType Leaf)) { Remove-Item -LiteralPath $f -Force; $n++ }
}
Write-Host "resume PDFs removed: $n"
$t = 0
$tts = Join-Path $VarDir "media\tts"
if (Test-Path $tts) {
  $items = Get-ChildItem -Path $tts -File -Recurse
  $t = @($items).Count
  $items | Remove-Item -Force
}
Write-Host "TTS audio files removed: $t"

Write-Host "=== VERIFY ==="
docker exec -i $Container psql -U $DbUser -d $Db -At -c "SELECT 'candidates='||count(*) FROM users WHERE role='candidate'" -c "SELECT 'recruiters='||count(*) FROM users WHERE role='recruiter'" -c "SELECT 'interviews='||count(*) FROM interviews"
Write-Host "done. Sign up new candidate accounts at http://localhost:3001/register"
