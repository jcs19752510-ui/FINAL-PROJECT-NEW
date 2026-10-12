"""Locust 스크립트(loadtest/locustfile.py) 내부 테스트 — 가짜 API 서버(stub_server.py)에 실제 locust 를 돌려 검증한다.
실행: python -m pytest loadtest/tests -q"""

import csv
import importlib.util
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LOCUSTFILE = ROOT / "loadtest/locustfile.py"
STUB = ROOT / "loadtest/stub_server.py"

if importlib.util.find_spec("locust") is None:  # import 하면 gevent 몽키패치가 pytest 프로세스의 ssl 과 충돌한다
    pytest.skip("locust 미설치", allow_module_level=True)


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def stub():
    procs = []

    def start(*extra):
        port = _free_port()
        p = subprocess.Popen([sys.executable, str(STUB), str(port), *extra])
        procs.append(p)
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                return port
            except OSError:
                time.sleep(0.1)
        raise RuntimeError("stub 서버가 뜨지 않았습니다")

    yield start
    for p in procs:
        p.terminate()


def run_locust(tmp_path, port, **env):
    full_env = {**os.environ, "LOCUST_EMAIL": "a@example.com", "LOCUST_PASSWORD": "pw", **env}
    prefix = tmp_path / "out"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "locust",
            "-f",
            str(LOCUSTFILE),
            "--host",
            f"http://127.0.0.1:{port}",
            "--headless",
            "-u",
            "4",
            "-r",
            "4",
            "-t",
            "5s",
            "--csv",
            str(prefix),
            "--only-summary",
        ],
        capture_output=True,
        text=True,
        env=full_env,
        timeout=60,
    )
    rows = {}
    stats = Path(f"{prefix}_stats.csv")
    if stats.exists():
        with open(stats, encoding="utf-8") as fh:
            rows = {r["Name"]: r for r in csv.DictReader(fh)}
    return proc, rows


def test_lc01_candidate_scenario_runs_without_failures(stub, tmp_path):
    proc, rows = run_locust(tmp_path, stub())
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert int(rows["POST /auth/login"]["Request Count"]) >= 4
    assert int(rows["GET /auth/me"]["Request Count"]) > 0 and int(rows["GET /interviews"]["Request Count"]) > 0
    assert "GET /recruiter/reports" not in rows
    assert all(int(r["Failure Count"]) == 0 for r in rows.values())


def test_lc02_recruiter_scenario_uses_report_list_only(stub, tmp_path):
    proc, rows = run_locust(tmp_path, stub(), LOCUST_ROLE="recruiter")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert int(rows["GET /recruiter/reports"]["Request Count"]) > 0 and "GET /interviews" not in rows


def test_lc03_server_errors_are_reported_as_failures(stub, tmp_path):
    proc, rows = run_locust(tmp_path, stub("fail"))
    assert proc.returncode == 1  # locust 는 실패가 있으면 종료코드 1
    assert int(rows["Aggregated"]["Failure Count"]) > 0


def test_lc04_login_failure_is_marked_failed(stub, tmp_path):
    proc, rows = run_locust(tmp_path, stub(), LOCUST_PASSWORD="wrong")
    assert int(rows["POST /auth/login"]["Failure Count"]) >= 4
    assert proc.returncode == 1


def test_lc05_missing_credentials_gives_clear_message(stub, tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("LOCUST_")}
    port = stub()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "locust",
            "-f",
            str(LOCUSTFILE),
            "--host",
            f"http://127.0.0.1:{port}",
            "--headless",
            "-u",
            "1",
            "-r",
            "1",
            "-t",
            "3s",
            "--only-summary",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert "LOCUST_ACCOUNTS_CSV 또는 LOCUST_EMAIL/LOCUST_PASSWORD" in proc.stdout + proc.stderr


def _accounts_in_subprocess(**env):
    """locustfile 은 gevent 몽키패치를 하므로 별도 프로세스에서 _load_accounts() 결과만 받아 온다."""
    code = (
        "import importlib.util, json, sys\n"
        "spec = importlib.util.spec_from_file_location('lf', sys.argv[1])\n"
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        "print(json.dumps(m._load_accounts()))\n"
    )
    base = {k: v for k, v in os.environ.items() if not k.startswith("LOCUST_")}
    out = subprocess.run(
        [sys.executable, "-c", code, str(LOCUSTFILE)], capture_output=True, text=True, env={**base, **env}, timeout=60
    )
    assert out.returncode == 0, out.stderr
    import json

    return [tuple(x) for x in json.loads(out.stdout.strip().splitlines()[-1])]


def test_lc06_accounts_csv_loading(tmp_path):
    csv_file = tmp_path / "accounts.csv"
    csv_file.write_text("a@example.com,pw1\n\nb@example.com , pw2\nbroken\n", encoding="utf-8")
    assert _accounts_in_subprocess(LOCUST_ACCOUNTS_CSV=str(csv_file)) == [
        ("a@example.com", "pw1"),
        ("b@example.com", "pw2"),
    ]


def test_lc07_single_account_env_and_none():
    assert _accounts_in_subprocess(LOCUST_EMAIL="x@example.com", LOCUST_PASSWORD="p") == [("x@example.com", "p")]
    assert _accounts_in_subprocess() == []


def test_lc08_script_is_read_only_no_mutating_requests():
    src = LOCUSTFILE.read_text(encoding="utf-8")
    for verb in ("client.put", "client.delete", "client.patch"):
        assert verb not in src
    assert src.count("client.post(") == 1  # 로그인 한 곳뿐
