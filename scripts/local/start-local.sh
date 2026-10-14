#!/usr/bin/env bash
# 로컬 개발 서버 일괄 기동 (macOS/Linux/Git Bash/WSL). 사용: scripts/local/start-local.sh [--skip-install]
# 포트: 백엔드 8001 / 프런트 3001 / 이력서 포털 3002. 로그: .local-run/*.log, PID: .local-run/*.pid
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; BE="$ROOT/backend"; FE="$ROOT/frontend"; AP="$ROOT/frontend-apply"
RUN="$ROOT/.local-run"; mkdir -p "$RUN"
if [ -x "$BE/.venv/Scripts/python.exe" ]; then PY="$BE/.venv/Scripts/python.exe"; else PY="$BE/.venv/bin/python"; fi
step(){ printf '\n==> %s\n' "$1"; }
for c in docker python3 node npm; do command -v "$c" >/dev/null || { echo "$c 필요"; exit 1; }; done
docker info >/dev/null 2>&1 || { echo "Docker 데몬이 실행 중이 아닙니다"; exit 1; }

step "1. 가상환경/의존성"
[ -e "$PY" ] || python3 -m venv "$BE/.venv"
[ -x "$BE/.venv/Scripts/python.exe" ] && PY="$BE/.venv/Scripts/python.exe" || PY="$BE/.venv/bin/python"
if [ "${1:-}" != "--skip-install" ]; then
  "$PY" -m pip install -q -r "$BE/requirements.txt"   # pypdf 포함
  for d in "$FE" "$AP"; do [ -d "$d" ] && [ ! -d "$d/node_modules" ] && (cd "$d" && npm install); done
fi
[ -f "$BE/.env" ] || { cp "$BE/.env.example" "$BE/.env"; echo "backend/.env 생성(JWT_SECRET_KEY 변경 권장)"; }
[ -f "$FE/.env.local" ] || echo "NEXT_PUBLIC_API_BASE_URL=http://localhost:8001/api/v1" > "$FE/.env.local"

step "2. DB/Redis"; (cd "$BE" && docker compose up -d)
for i in $(seq 30); do docker exec final-project-db pg_isready -U final_app >/dev/null 2>&1 && break; sleep 1; done

step "3. 마이그레이션"; (cd "$BE" && PYTHONIOENCODING=utf-8 "$PY" -m alembic upgrade head)

step "4. 서버 기동"
launch(){ name="$1"; dir="$2"; shift 2; (cd "$dir" && PYTHONIOENCODING=utf-8 nohup "$@" >"$RUN/$name.log" 2>&1 & echo $! >"$RUN/$name.pid"); echo "  $name pid=$(cat "$RUN/$name.pid")"; }
launch backend "$BE" "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8001
launch worker  "$BE" "$PY" -m celery -A app.services.celery_app worker --concurrency=1 --pool=solo -Q ai_pipeline
launch frontend "$FE" npm run dev -- --port 3001
[ -d "$AP" ] && launch apply "$AP" npm run dev -- --port 3002

step "5. 헬스체크"
for i in $(seq 60); do curl -fs http://127.0.0.1:8001/api/v1/health >/dev/null 2>&1 && { echo "백엔드 정상"; break; }; sleep 2; done
cat <<TXT

  모의면접 웹앱     http://localhost:3001   (회원가입 /register)
  이력서 제출 포털  http://localhost:3002
  API 문서          http://localhost:8001/docs
  종료: scripts/local/stop-local.sh   로그: $RUN/*.log
TXT
