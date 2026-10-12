"""Prometheus 지표 노출 (원본 계획서 7.2 모니터링, 2026-10-12).

`METRICS_ENABLED=true`일 때만 활성화된다(기본 꺼짐 — 지표 노출은 운영자가 명시적으로 켠다). 켜면
- 모든 HTTP 요청의 건수(`http_requests_total`)와 처리 시간(`http_request_duration_seconds`)을
  메서드·**라우트 템플릿**·상태코드로 집계한다(`/interviews/{id}`처럼 템플릿을 써서 라벨 폭발을 막는다).
- `GET /metrics`로 Prometheus 형식을 내보낸다. 이 경로는 집계에서 제외된다.

주의:
- 지표는 **API 프로세스 기준**이다. Celery 워커(LLM·리포트 처리)는 별도 프로세스라 이 엔드포인트에 포함되지 않는다
  (AI 토큰 사용량 지표는 워커 쪽 별도 노출이 필요 — 이번 범위 아님).
- `/metrics`는 인증이 없다. 반드시 내부망에서만 접근시키고 외부 게이트웨이(NGINX)에서는 막는다(deploy/nginx).
"""

import time

from fastapi import FastAPI
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    ProcessCollector,
    generate_latest,
)
from starlette.requests import Request
from starlette.responses import Response

METRICS_PATH = "/metrics"
_UNMATCHED = "unmatched"  # 라우트에 매칭되지 않은 요청(404 등)은 한 라벨로 묶어 라벨 폭발을 막는다


class _MetricsMiddleware:
    def __init__(self, app, requests: Counter, durations: Histogram) -> None:
        self.app = app
        self._requests = requests
        self._durations = durations

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope["path"] == METRICS_PATH:
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status = {"code": 500}  # 응답 시작 전에 예외가 나면 500으로 기록

        async def send_wrapper(message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            route = scope.get("route")
            path = getattr(route, "path", None) or _UNMATCHED
            method = scope["method"]
            self._requests.labels(method=method, path=path, status=str(status["code"])).inc()
            self._durations.labels(method=method, path=path).observe(time.perf_counter() - started)


def install_metrics(app: FastAPI, *, enabled: bool) -> CollectorRegistry | None:
    """enabled가 False면 아무것도 하지 않는다. 호출마다 독립 레지스트리를 만들어 테스트·재호출에 안전하다."""
    if not enabled:
        return None
    registry = CollectorRegistry()
    requests = Counter("http_requests_total", "HTTP 요청 수", ["method", "path", "status"], registry=registry)
    durations = Histogram(
        "http_request_duration_seconds",
        "HTTP 요청 처리 시간(초)",
        ["method", "path"],
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
        registry=registry,
    )
    try:  # 프로세스 CPU/메모리 지표(/proc 기반이라 Windows에서는 값이 비어 있을 수 있음)
        ProcessCollector(registry=registry)
    except Exception:  # noqa: BLE001 — 부가 지표라 실패해도 서버 기동을 막지 않는다
        pass

    async def metrics_endpoint(_: Request) -> Response:
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    app.add_middleware(_MetricsMiddleware, requests=requests, durations=durations)
    app.add_route(METRICS_PATH, metrics_endpoint, include_in_schema=False)
    return registry
