"""NGINX 게이트웨이(deploy/nginx/nginx.conf) 실제 구동 테스트 —
진짜 nginx 를 띄우고 가짜 upstream(화면/API)을 붙여 검증한다.
포트만 시험용으로 바꾼 사본을 쓰며(80→18080, 443→18443, upstream→가짜 서버), 나머지 지시어는 원본 그대로다.
nginx·openssl 이 없으면 건너뛴다. 실행: python -m pytest deploy/tests -q"""

import http.client
import json
import os
import shutil
import socket
import ssl
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONF = ROOT / "deploy/nginx/nginx.conf"
GEN = ROOT / "deploy/nginx/gen-selfsigned.sh"
HTTPS_PORT, HTTP_PORT = 18443, 18080
IV, AP = "interview.example.internal", "apply.example.internal"

pytestmark = pytest.mark.skipif(not (shutil.which("nginx") and shutil.which("openssl")), reason="nginx/openssl 없음")


def _stub(marker: str):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _reply(self):
            length = int(self.headers.get("Content-Length") or 0)
            read = 0
            while read < length:
                read += len(self.rfile.read(min(65536, length - read)))
            if self.headers.get("Upgrade", "").lower() == "websocket":
                self.send_response(101, "Switching Protocols")
                self.send_header("Upgrade", "websocket")
                self.send_header("Connection", "Upgrade")
                self.end_headers()
                return
            body = json.dumps(
                {
                    "marker": marker,
                    "path": self.path,
                    "host": self.headers.get("Host"),
                    "xfp": self.headers.get("X-Forwarded-Proto"),
                    "received": read,
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = do_POST = _reply

        def log_message(self, *a):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture(scope="module")
def gateway(tmp_path_factory):
    work = tmp_path_factory.mktemp("nginx")
    web, apply_, api = _stub("web"), _stub("apply"), _stub("api")
    conf = CONF.read_text(encoding="utf-8")
    for old, new in (
        ("127.0.0.1:3001", f"127.0.0.1:{web.server_address[1]}"),
        ("127.0.0.1:3002", f"127.0.0.1:{apply_.server_address[1]}"),
        ("127.0.0.1:8001", f"127.0.0.1:{api.server_address[1]}"),
        ("listen 80;", f"listen {HTTP_PORT};"),
        ("listen 443 ssl;", f"listen {HTTPS_PORT} ssl;"),
    ):
        assert old in conf, old
        conf = conf.replace(old, new)
    # 비루트(예: GitHub Actions 러너) 사용자는 nginx 기본 임시 폴더(/var/lib/nginx/...)에 쓸 수 없어 큰 업로드(ng09)가
    # 500이 된다. 비루트로 실행될 때만 시험용 사본의 임시 폴더를 작업 폴더 안으로 돌린다(운영 nginx.conf 는 그대로).
    # 루트로 실행되면 워커가 다른 사용자(www-data 등)로 내려가 기본 경로가 오히려 맞으므로 건드리지 않는다.
    if os.geteuid() != 0:
        temp_dirs = "".join(
            f"    {directive} temp/{name};\n"
            for directive, name in (
                ("client_body_temp_path", "body"),
                ("proxy_temp_path", "proxy"),
                ("fastcgi_temp_path", "fastcgi"),
                ("uwsgi_temp_path", "uwsgi"),
                ("scgi_temp_path", "scgi"),
            )
        )
        assert "http {\n" in conf
        conf = conf.replace("http {\n", "http {\n" + temp_dirs, 1)
        (work / "temp").mkdir()
    (work / "nginx.conf").write_text(conf, encoding="utf-8")
    (work / "logs").mkdir()
    # 인증서는 실제 스크립트로 만든다(스크립트를 작업 폴더로 복사해 그 옆 certs/ 에 생성)
    script = work / "gen-selfsigned.sh"
    shutil.copy(GEN, script)
    subprocess.run(["bash", str(script)], check=True, capture_output=True)
    base = ["nginx", "-p", str(work), "-c", "nginx.conf", "-e", "logs/error.log"]
    check = subprocess.run(base + ["-t"], capture_output=True, text=True)
    assert check.returncode == 0, check.stderr
    subprocess.run(base, check=True, capture_output=True)
    try:
        yield work
    finally:
        subprocess.run(base + ["-s", "stop"], capture_output=True)
        for s in (web, apply_, api):
            s.shutdown()


def _conn(host, tls_version=None):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    if tls_version is not None:
        ctx.minimum_version = ctx.maximum_version = tls_version
    sock = ctx.wrap_socket(socket.create_connection(("127.0.0.1", HTTPS_PORT), timeout=10), server_hostname=host)
    conn = http.client.HTTPSConnection(host, HTTPS_PORT, context=ctx, timeout=30)
    conn.sock = sock
    return conn, sock


def get(host, path, method="GET", body=None, headers=None):
    conn, _ = _conn(host)
    conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp, data


def test_ng01_config_valid_and_started(gateway):
    assert (gateway / "nginx.pid").exists()


def test_ng02_tls13_handshake_negotiated(gateway):
    _, sock = _conn(IV, ssl.TLSVersion.TLSv1_3)
    assert sock.version() == "TLSv1.3"
    sock.close()


def test_ng03_tls12_client_is_rejected(gateway):
    with pytest.raises(ssl.SSLError):
        _conn(IV, ssl.TLSVersion.TLSv1_2)


def test_ng04_http_redirects_to_https(gateway):
    conn = http.client.HTTPConnection("127.0.0.1", HTTP_PORT, timeout=10)
    conn.request("GET", "/some/path?x=1", headers={"Host": IV})
    resp = conn.getresponse()
    assert resp.status == 301 and resp.getheader("Location") == f"https://{IV}/some/path?x=1"


def test_ng05_routes_web_and_api_with_forwarded_proto(gateway):
    r, body = get(IV, "/")
    assert json.loads(body)["marker"] == "web"
    r, body = get(IV, "/api/v1/auth/me")
    data = json.loads(body)
    assert data["marker"] == "api" and data["path"] == "/api/v1/auth/me" and data["xfp"] == "https"


def test_ng06_apply_host_routes_to_apply_web_and_api(gateway):
    assert json.loads(get(AP, "/")[1])["marker"] == "apply"
    assert json.loads(get(AP, "/api/v1/resumes")[1])["marker"] == "api"


@pytest.mark.parametrize("host", [IV, AP])
def test_ng07_metrics_is_blocked_at_gateway(gateway, host):
    assert get(host, "/metrics")[0].status == 404  # 가짜 API는 200을 돌려주므로 404면 게이트웨이가 막은 것


def test_ng08_security_headers_present_and_version_hidden(gateway):
    resp, _ = get(IV, "/")
    assert "max-age=31536000" in resp.getheader("Strict-Transport-Security")
    assert resp.getheader("X-Content-Type-Options") == "nosniff"
    assert resp.getheader("X-Frame-Options") == "SAMEORIGIN"
    assert resp.getheader("Referrer-Policy") == "no-referrer"
    assert resp.getheader("Server") == "nginx"  # 버전 숨김(server_tokens off)


def test_ng09_upload_limits_voice_26mb_and_resume_12mb(gateway):
    mb = 1024 * 1024
    assert get(IV, "/api/v1/interviews/x/turns", "POST", b"x" * (25 * mb))[0].status == 200  # 음성 상한 25MB 통과
    assert get(IV, "/api/v1/interviews/x/turns", "POST", b"x" * (27 * mb))[0].status == 413
    assert get(AP, "/api/v1/resumes", "POST", b"x" * (11 * mb))[0].status == 200  # 이력서 10MB 상한 + 여유
    assert get(AP, "/api/v1/resumes", "POST", b"x" * (13 * mb))[0].status == 413


def test_ng10_websocket_upgrade_passes_through(gateway):
    conn, sock = _conn(IV)
    request = (
        f"GET /ws/interviews/abc HTTP/1.1\r\nHost: {IV}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
        "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n\r\n"
    )
    sock.sendall(request.encode())
    assert sock.recv(4096).startswith(b"HTTP/1.1 101")
    sock.close()


def test_ng11_selfsigned_cert_has_both_domains_and_private_key_mode(gateway):
    crt, key = gateway / "certs/server.crt", gateway / "certs/server.key"
    text = subprocess.run(
        ["openssl", "x509", "-in", str(crt), "-noout", "-text"], capture_output=True, text=True
    ).stdout
    assert f"DNS:{IV}" in text and f"DNS:{AP}" in text
    assert oct(key.stat().st_mode & 0o777) == "0o600"


def test_ng12_unknown_path_on_unknown_host_not_exposed_via_plain_http(gateway):
    conn = http.client.HTTPConnection("127.0.0.1", HTTP_PORT, timeout=10)
    conn.request("GET", "/api/v1/auth/me", headers={"Host": "evil.example"})
    resp = conn.getresponse()
    assert resp.status == 301 and resp.getheader("Location").startswith("https://")  # 평문으로는 API 응답을 주지 않는다
