#!/usr/bin/env bash
# 시험용 자체서명 인증서 생성 (2026-10-12). 운영에서는 사내 CA가 발급한 인증서를 certs/ 에 둔다.
# 사용법: bash deploy/nginx/gen-selfsigned.sh [도메인1 도메인2 ...]
#   기본 도메인: interview.example.internal apply.example.internal
# 결과: deploy/nginx/certs/server.crt, server.key (git에 올리지 않는다 — .gitignore)
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)/certs"
mkdir -p "$DIR"
DOMAINS=("${@:-interview.example.internal apply.example.internal}")
# 인자가 없을 때 위 기본값 문자열이 한 요소로 들어오므로 공백 기준으로 다시 나눈다
read -r -a DOMAINS <<< "${DOMAINS[*]}"

SAN=""
for d in "${DOMAINS[@]}"; do SAN="${SAN:+$SAN,}DNS:$d"; done

openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
  -keyout "$DIR/server.key" -out "$DIR/server.crt" \
  -subj "/CN=${DOMAINS[0]}" -addext "subjectAltName=$SAN"
chmod 600 "$DIR/server.key"
echo "생성 완료: $DIR/server.crt (SAN: $SAN)"
