"""Google 로그인 테스트 공용 픽스처. 외부 Google은 모킹하고, DB(마이그레이션 적용됨)·Redis는 실제로 쓴다.

사전 조건: DATABASE_URL/REDIS_URL/JWT_SECRET_KEY 환경변수, `alembic upgrade head`(user_identities 포함) 적용.
서버 기동은 필요 없다 — FastAPI TestClient로 신규 라우터와 기존 auth 라우터만 담은 미니 앱을 직접 호출한다.
"""

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt

from app.api.v1.auth import router as auth_router
from app.api.v1.auth_google import router as google_router
from app.core.config import settings
from app.core.errors import AppError, app_error_handler
from app.services import google_oidc
from app.services.prompt_safety import _get_redis
from tests.support.accounts import is_marker_email, new_marker_email
from tests.support.cleanup import cleanup_test_data

CLIENT_ID = "test-client-id.apps.googleusercontent.com"
CLIENT_SECRET = "TEST-SECRET-must-never-appear-in-logs"
REDIRECT_URI = "http://localhost:8001/api/v1/auth/google/callback"
FRONT = "http://localhost:3002"
KID = "test-key-1"


class _Resp:
    def __init__(self, data: bytes):
        self.status = 200
        self.data = data
        self.headers = {}


class FakeCertRequest:
    """google-auth 전송 계층 대역: Google 인증서 조회 요청에 우리가 만든 인증서를 돌려준다."""

    def __init__(self, certs: dict[str, str]):
        self.certs = certs

    def __call__(self, url, method="GET", body=None, headers=None, timeout=None, **kwargs):
        import json

        return _Resp(json.dumps(self.certs).encode())


def _make_key_and_cert():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-google")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    priv_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    return priv_pem, cert.public_bytes(serialization.Encoding.PEM).decode()


@pytest.fixture(scope="session")
def signing():
    priv, cert = _make_key_and_cert()
    other_priv, _ = _make_key_and_cert()
    return {"priv": priv, "cert": cert, "other_priv": other_priv}


@pytest.fixture
def google_settings(monkeypatch, signing):
    monkeypatch.setattr(settings, "google_login_enabled", True)
    monkeypatch.setattr(settings, "google_client_id", CLIENT_ID)
    monkeypatch.setattr(settings, "google_client_secret", CLIENT_SECRET)
    monkeypatch.setattr(settings, "google_redirect_uri", REDIRECT_URI)
    monkeypatch.setattr(settings, "google_allowed_return_origins", f"{FRONT},http://localhost:3000")
    monkeypatch.setattr(settings, "cookie_secure", False)
    fake = FakeCertRequest({KID: signing["cert"]})
    monkeypatch.setattr(google_oidc, "_default_http_request", lambda: fake)
    redis = _get_redis()
    for key in redis.scan_iter("rate_limit:google_*"):
        redis.delete(key)
    return settings


@pytest.fixture
def app(google_settings):
    app = FastAPI()
    app.add_exception_handler(AppError, app_error_handler)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(google_router, prefix="/api/v1")
    return app


@pytest.fixture
def client(app):
    return TestClient(app, follow_redirects=False, raise_server_exceptions=False)


@pytest.fixture
def created_emails():
    emails: list[str] = []
    yield emails
    if emails:
        cleanup_test_data(set(emails))


class Flow:
    def __init__(self, client: TestClient, return_to: str | None = None):
        params = {"return_to": return_to} if return_to else {}
        self.start = client.get("/api/v1/auth/google/start", params=params)
        assert self.start.status_code == 302, self.start.text
        from urllib.parse import parse_qs, urlparse

        self.query = {k: v[0] for k, v in parse_qs(urlparse(self.start.headers["location"]).query).items()}
        self.state = self.query["state"]
        self.nonce = self.query["nonce"]
        cookie = next(
            c for c in self.start.headers.get_list("set-cookie") if c.startswith(f"{google_oidc.FLOW_COOKIE_NAME}=")
        )
        self.cookie_value = cookie.split(";", 1)[0].split("=", 1)[1]

    def headers(self, cookie_value: str | None = None) -> dict:
        return {"Cookie": f"{google_oidc.FLOW_COOKIE_NAME}={cookie_value or self.cookie_value}"}


@pytest.fixture
def new_flow(client):
    return lambda return_to=None: Flow(client, return_to)


@pytest.fixture
def make_token(signing):
    def _make(
        nonce: str,
        *,
        sub=None,
        email=None,
        email_verified=True,
        aud=CLIENT_ID,
        iss="https://accounts.google.com",
        exp_delta=3600,
        name="구글 테스터",
        key="priv",
        extra=None,
    ):
        now = int(time.time())
        claims = {
            "iss": iss,
            "aud": aud,
            "sub": sub or str(uuid.uuid4().int),
            "email": email or new_marker_email(),
            "email_verified": email_verified,
            "name": name,
            "nonce": nonce,
            "iat": now,
            "exp": now + exp_delta,
        }
        claims.update(extra or {})
        return jwt.encode(claims, signing[key], algorithm="RS256", headers={"kid": KID})

    return _make


@pytest.fixture
def complete(client, monkeypatch, make_token, created_emails):
    """Flow 하나를 만들고 id_token을 주입해 콜백까지 호출한다. (flow, token, response) 반환."""

    def _complete(flow: Flow, *, state=None, code="auth-code-123", token_kwargs=None, token=None, cookie_value=None):
        kwargs = dict(token_kwargs or {})
        tok = token or make_token(flow.nonce, **kwargs)
        claim_email = jwt.get_unverified_claims(tok).get("email", "")
        if is_marker_email(claim_email):
            created_emails.append(claim_email)
        monkeypatch.setattr(google_oidc, "exchange_code", lambda c, v: tok)
        return client.get(
            "/api/v1/auth/google/callback",
            params={"code": code, "state": state or flow.state},
            headers=flow.headers(cookie_value),
        )

    return _complete
