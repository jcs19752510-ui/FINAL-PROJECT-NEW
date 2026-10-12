# 모니터링 (Prometheus + Grafana)

원본 계획서 7.2 "모니터링 대시보드 설정(Prometheus/Grafana)" 중 **API 프로세스 지표** 부분이다.

## 켜는 순서
1. 백엔드 `.env`(또는 환경변수)에 `METRICS_ENABLED=true` → API 재시작 → `GET http://127.0.0.1:8001/metrics` 확인
2. `docker compose -f deploy/monitoring/docker-compose.monitoring.yml up -d`
3. Grafana(`http://127.0.0.1:3000`) → 대시보드 "AI 모의면접 API" (요청 수, p95 응답 시간, 5xx 비율, 프로세스 메모리)

## 수집되는 지표
- `http_requests_total{method,path,status}` — `path`는 `/api/v1/interviews/{interview_id}/turns` 같은 **라우트 템플릿**(라벨 폭발 방지). 매칭 안 된 요청은 `unmatched`
- `http_request_duration_seconds` 히스토그램
- 프로세스 CPU/메모리(`process_*`, 리눅스 기준. Windows에서는 비어 있을 수 있음)

## 이번 범위에 없는 것 (정직하게)
- **AI 토큰 사용량·LLM 처리 시간 지표**: LLM 호출은 Celery 워커 프로세스에서 일어나 API의 `/metrics`에 포함되지 않는다. 워커 쪽 별도 노출(포트 하나 추가)이 필요해 이번 5분 범위를 넘는다.
- **알림 규칙(Alertmanager)**, **GPU 지표**(별도 exporter 필요)
- 이 서버에서 Prometheus/Grafana 컨테이너를 실제로 띄워 보지 못했다(도커 데몬 없음). 설정 파일 문법과 `/metrics` 출력 형식만 테스트로 검증했다.

## 보안
`/metrics`는 인증이 없다. 기본은 꺼져 있고(`METRICS_ENABLED=false`), 켤 때는 내부망에서만 접근하게 하고 NGINX 게이트웨이에서는 404로 막는다(`deploy/nginx/nginx.conf`).
