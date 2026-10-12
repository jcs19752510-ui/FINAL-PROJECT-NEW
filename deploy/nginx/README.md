# NGINX 게이트웨이 (TLS 1.3 종단) — 시험용 구성

원본 계획서 4.1 "API Gateway: NGINX/Traefik(로드밸런싱, SSL 종단)" 항목. 같은 PC에서 NGINX가 `443`(HTTPS)을 받아 화면(3001/3002)과 API(8001)로 프록시한다.

## 구성 요약
| 경로 | 대상 | 비고 |
|---|---|---|
| `https://interview.example.internal/` | 면접·채용담당자 화면(3001) | |
| `https://interview.example.internal/api/` | API(8001) | 읽기 대기 120초(LLM 지연 여유) |
| `https://interview.example.internal/ws/` | API WebSocket | 세션 동안 유지(3600초) |
| `https://apply.example.internal/` | 채용 지원 화면(3002) + `/api/` | 업로드 상한 12MB(이력서 10MB) |
| `/metrics` | **404 반환** | Prometheus는 외부 경유 없이 API 포트로 직접 수집 |
| `http://...:80` | 301 → HTTPS | |

TLS는 **1.3만** 허용한다(1.2 이하 클라이언트는 접속 불가). HTTP/2는 NGINX 버전에 따라 지시어가 달라 호환성을 위해 켜지 않았다(HTTP/1.1).

## 실행 (시험)
```bash
bash deploy/nginx/gen-selfsigned.sh                 # 시험용 자체서명 인증서 → deploy/nginx/certs/
nginx -p deploy/nginx -c nginx.conf -t              # 설정 검사
nginx -p deploy/nginx -c nginx.conf                 # 실행
```
Windows는 NGINX Windows 빌드로 같은 명령을 `nginx.exe -p deploy\nginx -c nginx.conf` 로 실행한다(openssl로 인증서를 만들어 `certs\`에 둔다).

## 착수 전 결정이 필요한 것 (임의로 정하지 않았다)
1. **도메인 이름**: `interview.example.internal`, `apply.example.internal`은 자리표시자다. 실제 사내 도메인으로 바꿔야 한다.
2. **인증서**: 자체서명은 시험용이다. 운영은 사내 CA가 발급한 인증서를 `certs/server.crt`, `certs/server.key`로 둔다.
3. **프런트·API 설정 변경**(HTTPS 전환 시 필수):
   - 프런트 빌드 환경변수 `NEXT_PUBLIC_API_BASE_URL=https://interview.example.internal/api/v1` (빌드 시점에 박힘)
   - 백엔드 `CORS_ORIGINS`에 두 HTTPS 주소 추가, `COOKIE_SECURE=true`
4. **로그인 시도 제한(rate limit)**: 이 설정에는 넣지 않았다(기획서 OPEN-11 미결정).

## 확인하지 못한 것
- 실제 Windows NGINX 빌드와 실제 브라우저(HSTS·쿠키) 동작은 검증하지 않았다(Linux NGINX + curl/openssl로 검증).
- 운영 인증서 체인, 사내 DNS 등록, 방화벽 규칙은 이 설정의 범위가 아니다.
