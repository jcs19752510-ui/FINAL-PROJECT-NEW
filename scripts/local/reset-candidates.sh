#!/usr/bin/env bash
# Delete all candidate accounts + interview data from the LOCAL dev DB (and their resume PDFs / TTS audio).
#   scripts/local/reset-candidates.sh            # DRY-RUN (default): shows counts, deletes nothing
#   scripts/local/reset-candidates.sh --apply    # real delete (asks you to type DELETE)
#   add --force to skip the prompt, --container NAME / --db NAME / --user NAME to override defaults
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../.." && pwd)"
CONTAINER="final-project-db"; DB="final_project"; DBUSER="final_app"; APPLY=0; FORCE=0
VAR_DIR="${VAR_DIR:-$ROOT/backend/var}"
PSQL_LOCAL="${PSQL_LOCAL:-}"   # for tests: full psql command instead of docker exec
while [ $# -gt 0 ]; do case "$1" in
  --apply) APPLY=1;; --force) FORCE=1;; --container) CONTAINER="$2"; shift;; --db) DB="$2"; shift;; --user) DBUSER="$2"; shift;;
  *) echo "unknown option $1"; exit 2;; esac; shift; done

psql_run(){ if [ -n "$PSQL_LOCAL" ]; then $PSQL_LOCAL "$@"; else docker exec -i "$CONTAINER" psql -U "$DBUSER" -d "$DB" "$@"; fi; }
if [ -z "$PSQL_LOCAL" ]; then
  docker ps --format '{{.Names}}' | grep -qx "$CONTAINER" || { echo "container '$CONTAINER' is not running (start servers first)"; exit 1; }
fi
echo "target: container=$CONTAINER db=$DB user=$DBUSER"
echo "=== DRY-RUN (counts) ==="
psql_run -v mode=dry < "$HERE/reset-candidates.sql"
[ "$APPLY" = 1 ] || { echo; echo "Nothing deleted. Re-run with --apply to delete."; exit 0; }

if [ "$FORCE" != 1 ]; then
  echo; echo "WARNING: this permanently deletes the data above (irreversible)."
  read -r -p "Type DELETE to continue: " ans; [ "$ans" = "DELETE" ] || { echo "aborted"; exit 1; }
fi

# collect resume file paths BEFORE deleting rows; delete files only after the DB commit succeeded
FILES="$(psql_run -At -c "SELECT file_path FROM resume_applications WHERE candidate_id IN (SELECT id FROM users WHERE role='candidate')")"
echo "=== APPLY ==="
psql_run -v mode=apply < "$HERE/reset-candidates.sql"

n=0
while IFS= read -r f; do [ -n "$f" ] && [ -f "$f" ] && rm -f -- "$f" && n=$((n+1)); done <<< "$FILES"
echo "resume PDFs removed: $n"
t=0
if [ -d "$VAR_DIR/media/tts" ]; then t=$(find "$VAR_DIR/media/tts" -type f | wc -l); find "$VAR_DIR/media/tts" -type f -delete; fi
echo "TTS audio files removed: $t"
echo "=== VERIFY ==="
psql_run -At -c "SELECT 'candidates='||count(*) FROM users WHERE role='candidate'" -c "SELECT 'recruiters='||count(*) FROM users WHERE role='recruiter'" -c "SELECT 'interviews='||count(*) FROM interviews"
echo "done. Sign up new candidate accounts at http://localhost:3001/register"
