"""Prometheus 지표(app/core/metrics.py) 내부 테스트."""

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.metrics import METRICS_PATH, install_metrics


def make_app(enabled=True):
    app = FastAPI()
    registry = install_metrics(app, enabled=enabled)

    @app.get("/items/{item_id}")
    def item(item_id: int):
        return {"id": item_id}

    @app.get("/boom")
    def boom():
        raise HTTPException(status_code=503, detail="down")

    @app.get("/crash")
    def crash():
        raise RuntimeError("unhandled")

    return app, registry


def metrics_text(client):
    return client.get(METRICS_PATH).text


def test_mt01_disabled_by_default_exposes_nothing():
    app, registry = make_app(enabled=False)
    assert registry is None
    assert TestClient(app).get(METRICS_PATH).status_code == 404


def test_mt02_enabled_exposes_prometheus_format():
    app, _ = make_app()
    res = TestClient(app).get(METRICS_PATH)
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/plain")
    assert "# TYPE http_requests_total counter" in res.text


def test_mt03_counts_requests_with_route_template_not_raw_path():
    app, _ = make_app()
    client = TestClient(app)
    for i in (1, 2, 3):
        assert client.get(f"/items/{i}").status_code == 200
    text = metrics_text(client)
    assert 'http_requests_total{method="GET",path="/items/{item_id}",status="200"} 3.0' in text
    assert "/items/1" not in text  # 라벨 폭발 방지


def test_mt04_status_codes_recorded_including_errors():
    app, _ = make_app()
    client = TestClient(app, raise_server_exceptions=False)
    client.get("/boom")
    client.get("/crash")
    text = metrics_text(client)
    assert 'path="/boom",status="503"' in text
    assert 'path="/crash",status="500"' in text


def test_mt05_unmatched_paths_share_one_label():
    app, _ = make_app()
    client = TestClient(app)
    for p in ("/nope1", "/nope2", "/nope3"):
        assert client.get(p).status_code == 404
    text = metrics_text(client)
    assert 'path="unmatched",status="404"} 3.0' in text and "/nope1" not in text


def test_mt06_metrics_endpoint_itself_not_counted():
    app, _ = make_app()
    client = TestClient(app)
    metrics_text(client)
    metrics_text(client)
    assert 'path="/metrics"' not in metrics_text(client)


def test_mt07_duration_histogram_recorded():
    app, _ = make_app()
    client = TestClient(app)
    client.get("/items/1")
    text = metrics_text(client)
    assert 'http_request_duration_seconds_count{method="GET",path="/items/{item_id}"} 1.0' in text
    assert "http_request_duration_seconds_bucket" in text


def test_mt08_independent_registries_per_install():
    app1, _ = make_app()
    app2, _ = make_app()
    TestClient(app1).get("/items/1")
    assert "/items/{item_id}" not in metrics_text(TestClient(app2))  # app2 지표에는 app1 요청이 섞이지 않는다
