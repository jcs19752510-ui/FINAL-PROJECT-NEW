#!/usr/bin/env bash
# 종료: scripts/local/stop-local.sh [--down]  (--down: DB/Redis 컨테이너도 내림, 볼륨 유지)
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; RUN="$ROOT/.local-run"
for f in "$RUN"/*.pid; do [ -f "$f" ] && kill "$(cat "$f")" 2>/dev/null && echo "종료 $(basename "$f" .pid)"; rm -f "$f"; done
[ "${1:-}" = "--down" ] && (cd "$ROOT/backend" && docker compose down)
exit 0
