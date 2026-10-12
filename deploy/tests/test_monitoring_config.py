"""모니터링 설정(deploy/monitoring) 교차 검증 — 문법, 파일 참조, 그리고 대시보드가 쓰는 지표 이름이
**실제 /metrics 출력**에 존재하는지 확인한다. (Prometheus/Grafana 컨테이너는 이 서버에서 실행하지 못했다.)"""

import json
import re
import sys
from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
MON = ROOT / "deploy/monitoring"
sys.path.insert(0, str(ROOT / "backend"))

from app.core.metrics import install_metrics  # noqa: E402


def load_yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_mn01_prometheus_scrapes_api_metrics_path_and_port():
    cfg = load_yaml(MON / "prometheus.yml")
    job = next(j for j in cfg["scrape_configs"] if j["job_name"] == "interview-api")
    assert job["metrics_path"] == "/metrics"
    assert job["static_configs"][0]["targets"] == ["host.docker.internal:8001"]  # 백엔드 API 포트


def test_mn02_compose_mounts_existing_files_and_binds_localhost_only():
    cfg = load_yaml(MON / "docker-compose.monitoring.yml")
    for name, svc in cfg["services"].items():
        for port in svc["ports"]:
            assert port.startswith("127.0.0.1:"), f"{name}: 외부 인터페이스에 노출됨 {port}"
        for vol in svc["volumes"]:
            src = vol.split(":")[0]
            if src.startswith("./"):
                assert (MON / src).exists(), f"{name}: 마운트 원본이 없음 {src}"
    assert cfg["services"]["grafana"]["depends_on"] == ["prometheus"]
    assert "host.docker.internal:host-gateway" in cfg["services"]["prometheus"]["extra_hosts"]


def test_mn03_grafana_provisioning_consistent():
    ds = load_yaml(MON / "grafana/provisioning/datasources/prometheus.yml")["datasources"][0]
    assert ds["type"] == "prometheus" and ds["url"] == "http://prometheus:9090" and ds["uid"] == "prometheus"
    provider = load_yaml(MON / "grafana/provisioning/dashboards/dashboards.yml")["providers"][0]
    assert provider["options"]["path"] == "/var/lib/grafana/dashboards"  # compose 의 마운트 위치와 일치
    compose = load_yaml(MON / "docker-compose.monitoring.yml")
    assert any(v.endswith(":/var/lib/grafana/dashboards:ro") for v in compose["services"]["grafana"]["volumes"])


def test_mn04_dashboard_json_valid_unique_ids_and_datasource():
    dash = json.loads((MON / "grafana/dashboards/interview-api.json").read_text(encoding="utf-8"))
    ids = [p["id"] for p in dash["panels"]]
    assert len(ids) == len(set(ids)) and dash["uid"] == "interview-api"
    for p in dash["panels"]:
        assert p["datasource"]["uid"] == "prometheus"
        for t in p["targets"]:
            expr = t["expr"]
            assert (
                expr.count("(") == expr.count(")")
                and expr.count("[") == expr.count("]")
                and expr.count("{") == expr.count("}")
            )


def test_mn05_dashboard_metric_names_exist_in_real_metrics_output():
    app = FastAPI()
    install_metrics(app, enabled=True)

    @app.get("/x/{i}")
    def x(i: int):
        return {}

    client = TestClient(app)
    client.get("/x/1")
    text = client.get("/metrics").text
    dash = json.loads((MON / "grafana/dashboards/interview-api.json").read_text(encoding="utf-8"))
    used = set()
    for p in dash["panels"]:
        for t in p["targets"]:
            used |= set(re.findall(r"\b(http_[a-z_]+|process_[a-z_]+)\b", t["expr"]))
    assert used, "대시보드가 지표를 쓰지 않음"
    for name in used:
        assert name in text, f"대시보드가 쓰는 지표 {name} 이(가) /metrics 에 없음"


def test_mn06_gateway_hides_metrics():
    assert "location = /metrics { return 404; }" in (ROOT / "deploy/nginx/nginx.conf").read_text(encoding="utf-8")
