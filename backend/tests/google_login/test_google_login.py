import logging
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import psycopg
import pytest
from fastapi import FastAPI

from app.api.v1 import google_wiring
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.services import google_oidc
from app.services.google_oidc import GoogleOidcError
from tests.google_login.conftest import CLIENT_ID, CLIENT_SECRET, FRONT, Flow
from tests.support.accounts import _database_url, new_marker_email

OK_URL = f"{FRONT}/login/google?status=ok"


def _q(resp):
    return parse_qs(urlparse(resp.headers["location"]).query)


def _refresh_cookie(resp):
    return [c for c in resp.headers.get_list("set-cookie") if c.startswith("refresh_token=")]


def _db(sql, args=()):
    with psycopg.connect(_database_url(), connect_timeout=5) as conn, conn.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall() if cur.description else None


def _error(resp) -> str:
    assert resp.status_code == 302
    assert not _refresh_cookie(resp), "실패 응답에 refresh 쿠키가 발급되면 안 됩니다"
    return _q(resp)["error"][0]


# ---------- /start ----------
def test_start_redirects_with_oidc_params_and_flow_cookie(client):
    resp = client.get("/api/v1/auth/google/start")
    assert resp.status_code == 302
    url = urlparse(resp.headers["location"])
    assert f"{url.scheme}://{url.netloc}{url.path}" == "https://accounts.google.com/o/oauth2/v2/auth"
    q = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert q["client_id"] == CLIENT_ID and q["response_type"] == "code"
    assert q["scope"] == "openid email profile" and q["code_challenge_method"] == "S256"
    assert len(q["state"]) >= 32 and len(q["nonce"]) >= 32 and q["code_challenge"]
    assert "client_secret" not in url.query
    cookie = next(c for c in resp.headers.get_list("set-cookie") if c.startswith("g_oauth="))
    low = cookie.lower()
    assert "httponly" in low and "samesite=lax" in low and "path=/api/v1/auth/google" in low and "max-age=600" in low
    assert not cookie.startswith("refresh_token=")


def test_start_return_to_allowlist(client):
    assert client.get("/api/v1/auth/google/start", params={"return_to": FRONT + "/"}).status_code == 302
    for bad in ["http://evil.example", f"{FRONT}.evil.example", "javascript:alert(1)", "//evil.example"]:
        r = client.get("/api/v1/auth/google/start", params={"return_to": bad})
        assert r.status_code == 400, bad


def test_start_state_is_unique(client):
    a, b = Flow(client), Flow(client)
    assert a.state != b.state and a.nonce != b.nonce and a.cookie_value != b.cookie_value


# ---------- 정상/재로그인/중복 ----------
def test_new_user_created_as_candidate_and_session_works(client, new_flow, complete):
    email = new_marker_email()
    flow = new_flow()
    resp = complete(flow, token_kwargs={"email": email, "sub": "sub-new-1", "name": "홍길동"})
    assert resp.status_code == 302 and resp.headers["location"] == OK_URL
    cookies = _refresh_cookie(resp)
    assert len(cookies) == 1
    low = cookies[0].lower()
    assert (
        "httponly" in low and "samesite=lax" in low and "path=/api/v1/auth" in low and f"max-age={7 * 24 * 3600}" in low
    )

    rows = _db("SELECT email, role, name FROM users WHERE email=%s", (email,))
    assert rows == [(email, "candidate", "홍길동")]
    ident = _db("SELECT provider, provider_sub, email_verified FROM user_identities WHERE email=%s", (email,))
    assert ident == [("google", "sub-new-1", True)]

    # 발급된 쿠키로 기존 /auth/refresh → /auth/me 가 그대로 동작한다.
    refresh_value = cookies[0].split(";", 1)[0].split("=", 1)[1]
    r = client.post("/api/v1/auth/refresh", headers={"Cookie": f"refresh_token={refresh_value}"})
    assert r.status_code == 200
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me.status_code == 200 and me.json()["email"] == email and me.json()["role"] == "candidate"


def test_relogin_same_sub_reuses_user(client, new_flow, complete):
    email = new_marker_email()
    first = complete(new_flow(), token_kwargs={"email": email, "sub": "sub-relogin"})
    second = complete(new_flow(), token_kwargs={"email": email, "sub": "sub-relogin"})
    assert first.headers["location"] == second.headers["location"] == OK_URL
    assert _db("SELECT count(*) FROM users WHERE email=%s", (email,)) == [(1,)]
    assert _db("SELECT count(*) FROM user_identities WHERE provider_sub='sub-relogin'") == [(1,)]


def test_concurrent_callbacks_same_google_account_create_one_user(app, created_emails, make_token, monkeypatch):
    from fastapi.testclient import TestClient

    email = new_marker_email()
    created_emails.append(email)
    clients = [TestClient(app, follow_redirects=False) for _ in range(2)]
    flows = [Flow(c) for c in clients]
    tokens = {f.state: make_token(f.nonce, sub="sub-race", email=email) for f in flows}
    monkeypatch.setattr(google_oidc, "exchange_code", lambda code, verifier: tokens[code])
    results = [None, None]
    barrier = threading.Barrier(2)

    def run(i):
        barrier.wait()
        results[i] = clients[i].get(
            "/api/v1/auth/google/callback",
            params={"code": flows[i].state, "state": flows[i].state},
            headers=flows[i].headers(),
        )

    threads = [threading.Thread(target=run, args=(i,)) for i in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert all(r.status_code == 302 and r.headers["location"] == OK_URL for r in results), [r.headers for r in results]
    assert _db("SELECT count(*) FROM users WHERE email=%s", (email,)) == [(1,)]
    assert _db("SELECT count(*) FROM user_identities WHERE provider_sub='sub-race'") == [(1,)]


# ---------- state / 쿠키 ----------
def test_wrong_state_rejected(new_flow, complete):
    assert _error(complete(new_flow(), state="not-the-state")) == "invalid_state"


def test_state_replay_rejected(client, new_flow, complete):
    flow = new_flow()
    assert complete(flow).headers["location"] == OK_URL
    replay = client.get(
        "/api/v1/auth/google/callback", params={"code": "x", "state": flow.state}, headers=flow.headers()
    )
    assert _error(replay) == "invalid_state"


def test_missing_or_tampered_cookie_rejected(client, new_flow, complete):
    flow = new_flow()
    client.cookies.clear()  # /start 응답 쿠키가 TestClient 쿠키 저장소에 남아 있으므로 비운 뒤 '쿠키 없음'을 재현
    assert (
        _error(client.get("/api/v1/auth/google/callback", params={"code": "x", "state": flow.state})) == "invalid_state"
    )
    tampered = flow.cookie_value[:-3] + ("aaa" if not flow.cookie_value.endswith("aaa") else "bbb")
    assert _error(complete(new_flow(), cookie_value=tampered)) == "invalid_state"


def test_flow_cookie_is_not_an_auth_token(client, new_flow):
    flow = new_flow()
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {flow.cookie_value}"})
    assert r.status_code == 401
    r2 = client.post("/api/v1/auth/refresh", headers={"Cookie": f"refresh_token={flow.cookie_value}"})
    assert r2.status_code == 401


def test_user_cancelled(client, new_flow):
    flow = new_flow()
    r = client.get(
        "/api/v1/auth/google/callback", params={"error": "access_denied", "state": flow.state}, headers=flow.headers()
    )
    assert _error(r) == "cancelled"


# ---------- code 교환 ----------
def test_bad_code_rejected(client, new_flow, monkeypatch):
    def boom(code, verifier):
        raise GoogleOidcError("token_exchange_failed")

    monkeypatch.setattr(google_oidc, "exchange_code", boom)
    flow = new_flow()
    r = client.get(
        "/api/v1/auth/google/callback", params={"code": "expired", "state": flow.state}, headers=flow.headers()
    )
    assert _error(r) == "token_exchange_failed"


def test_exchange_code_unit(monkeypatch):
    import requests

    class R:
        def __init__(self, status, body):
            self.status_code, self._b = status, body

        def json(self):
            return self._b

    calls = {}

    def post(url, data=None, timeout=None):
        calls.update(url=url, data=data, timeout=timeout)
        return R(200, {"id_token": "ID.TOKEN", "access_token": "dropped"})

    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(settings, "google_client_id", CLIENT_ID)
    monkeypatch.setattr(settings, "google_client_secret", CLIENT_SECRET)
    monkeypatch.setattr(settings, "google_redirect_uri", "http://x/cb")
    assert google_oidc.exchange_code("c", "verifier") == "ID.TOKEN"
    assert calls["timeout"] == google_oidc.HTTP_TIMEOUT_SECONDS and calls["data"]["code_verifier"] == "verifier"

    monkeypatch.setattr(requests, "post", lambda *a, **k: R(400, {"error": "invalid_grant"}))
    with pytest.raises(GoogleOidcError) as e1:
        google_oidc.exchange_code("c", "v")
    assert e1.value.reason == "token_exchange_failed"

    def net(*a, **k):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(requests, "post", net)
    with pytest.raises(GoogleOidcError) as e2:
        google_oidc.exchange_code("c", "v")
    assert e2.value.reason == "unavailable"


# ---------- ID Token 검증 (실제 google-auth 검증 경로 사용) ----------
@pytest.mark.parametrize(
    "kwargs",
    [
        {"key": "other_priv"},  # 잘못된 서명
        {"aud": "someone-else"},  # aud 불일치
        {"iss": "https://evil.example"},  # iss 불일치
        {"exp_delta": -3600},  # 만료
    ],
    ids=["bad-signature", "aud-mismatch", "iss-mismatch", "expired"],
)
def test_invalid_id_token_rejected(new_flow, complete, kwargs):
    email = new_marker_email()
    resp = complete(new_flow(), token_kwargs={"email": email, **kwargs})
    assert _error(resp) == "invalid_token"
    assert _db("SELECT count(*) FROM users WHERE email=%s", (email,)) == [(0,)]


def test_nonce_mismatch_rejected(new_flow, complete, make_token):
    email = new_marker_email()
    flow = new_flow()
    token = make_token("a-different-nonce", email=email)
    assert _error(complete(flow, token=token)) == "invalid_token"
    assert _db("SELECT count(*) FROM users WHERE email=%s", (email,)) == [(0,)]


def test_email_not_verified_rejected(new_flow, complete):
    email = new_marker_email()
    assert _error(complete(new_flow(), token_kwargs={"email": email, "email_verified": False})) == "email_unverified"
    assert _db("SELECT count(*) FROM users WHERE email=%s", (email,)) == [(0,)]


def test_email_verified_string_true_accepted(new_flow, complete):
    resp = complete(new_flow(), token_kwargs={"email_verified": "true"})
    assert resp.headers["location"] == OK_URL


# ---------- 기존 회원/보안 정책 ----------
def test_existing_password_account_is_not_merged(client, new_flow, complete, created_emails):
    email = new_marker_email()
    created_emails.append(email)
    reg = client.post("/api/v1/auth/register", json={"email": email, "password": "pw-12345678", "name": "기존"})
    assert reg.status_code == 201
    resp = complete(new_flow(), token_kwargs={"email": email, "sub": "sub-collide"})
    assert _error(resp) == "email_exists"
    assert _db("SELECT count(*) FROM user_identities WHERE provider_sub='sub-collide'") == [(0,)]
    assert client.post("/api/v1/auth/login", json={"email": email, "password": "pw-12345678"}).status_code == 200


def test_existing_email_case_insensitive_not_merged(client, new_flow, complete, created_emails):
    email = new_marker_email()
    created_emails.append(email)
    assert (
        client.post(
            "/api/v1/auth/register", json={"email": email, "password": "pw-12345678", "name": "기존"}
        ).status_code
        == 201
    )
    resp = complete(
        new_flow(),
        token_kwargs={
            "email": email.upper().replace("@HARNESS-TEST.EXAMPLE", "@harness-test.example"),
            "sub": "sub-case",
        },
    )
    assert _error(resp) == "email_exists"


def test_deleted_google_account_rejected(client, new_flow, complete):
    email = new_marker_email()
    assert complete(new_flow(), token_kwargs={"email": email, "sub": "sub-del"}).headers["location"] == OK_URL
    _db("UPDATE users SET deleted_at = now() WHERE email=%s", (email,))
    resp = complete(new_flow(), token_kwargs={"email": email, "sub": "sub-del"})
    assert _error(resp) == "account_disabled"


def test_google_account_cannot_password_login_same_401(client, new_flow, complete):
    email = new_marker_email()
    assert complete(new_flow(), token_kwargs={"email": email, "sub": "sub-nopw"}).headers["location"] == OK_URL
    google_acc = client.post("/api/v1/auth/login", json={"email": email, "password": "anything-goes-123"})
    unknown = client.post("/api/v1/auth/login", json={"email": new_marker_email(), "password": "anything-goes-123"})
    assert google_acc.status_code == unknown.status_code == 401
    assert google_acc.json() == unknown.json()


def test_role_is_always_candidate_even_with_role_claims(new_flow, complete):
    email = new_marker_email()
    resp = complete(new_flow(), token_kwargs={"email": email, "extra": {"role": "admin", "hd": "corp.example"}})
    assert resp.headers["location"] == OK_URL
    assert _db("SELECT role FROM users WHERE email=%s", (email,)) == [("candidate",)]


def test_google_module_has_no_privileged_role_path():
    for path in [Path("app/api/v1/auth_google.py"), Path("app/services/google_oidc.py")]:
        text = path.read_text(encoding="utf-8")
        assert "recruiter" not in text and "UserRole.admin" not in text and "role=payload" not in text, path


def test_untrusted_return_origin_in_cookie_falls_back(client, new_flow, complete, monkeypatch):
    # 쿠키가 서명되어 있어도, 허용 목록에서 빠진 오리진으로는 절대 리다이렉트하지 않는다.
    flow = new_flow()
    monkeypatch.setattr(settings, "google_allowed_return_origins", "http://localhost:9999")
    resp = complete(flow)
    assert resp.headers["location"].startswith("http://localhost:9999/")


# ---------- 장애 격리 ----------
def test_db_failure_issues_no_session(app, client, new_flow, complete, monkeypatch):
    from sqlalchemy.exc import OperationalError

    from app.db.session import SessionLocal

    def failing_db():
        db = SessionLocal()
        db.commit = lambda: (_ for _ in ()).throw(OperationalError("commit", {}, Exception("db down")))
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = failing_db
    email = new_marker_email()
    resp = complete(new_flow(), token_kwargs={"email": email, "sub": "sub-dbfail"})
    assert _error(resp) == "server_error"
    assert _db("SELECT count(*) FROM users WHERE email=%s", (email,)) == [(0,)]


def test_rate_limit(client, monkeypatch):
    from app.api.v1 import auth_google

    monkeypatch.setattr(auth_google, "RATE_LIMIT_PER_MINUTE", 2)
    codes = [client.get("/api/v1/auth/google/start") for _ in range(3)]
    assert [r.status_code for r in codes] == [302, 302, 302]
    assert "accounts.google.com" in codes[0].headers["location"]
    assert _q(codes[2])["error"] == ["rate_limited"]


def test_state_store_down_degrades_gracefully(client, monkeypatch):
    from app.api.v1 import auth_google

    class Dead:
        def incr(self, *a, **k):
            raise ConnectionError("redis down")

    monkeypatch.setattr(auth_google, "_get_redis", lambda: Dead())
    r = client.get("/api/v1/auth/google/start")
    assert (
        r.status_code == 302
        and _q(r)["error"] == ["unavailable"]
        and "g_oauth=" not in "".join(r.headers.get_list("set-cookie")).replace('g_oauth=""', "")
    )


# ---------- 스위치/배선 ----------
def test_switch_off_registers_nothing(monkeypatch):
    monkeypatch.setattr(settings, "google_login_enabled", False)
    app = FastAPI()
    assert google_wiring.include_google_login(app) is False
    assert not [r for r in app.routes if "/auth/google" in getattr(r, "path", "")]


def test_enabled_but_incomplete_config_registers_nothing(monkeypatch):
    monkeypatch.setattr(settings, "google_login_enabled", True)
    monkeypatch.setattr(settings, "google_client_id", CLIENT_ID)
    monkeypatch.setattr(settings, "google_client_secret", None)
    monkeypatch.setattr(settings, "google_redirect_uri", "http://x")
    app = FastAPI()
    assert google_wiring.include_google_login(app) is False
    assert not [r for r in app.routes if "/auth/google" in getattr(r, "path", "")]


def test_enabled_and_complete_registers_routes(google_settings):
    app = FastAPI()
    assert google_wiring.include_google_login(app) is True
    paths = {r.path for r in app.routes}
    assert {"/api/v1/auth/google/start", "/api/v1/auth/google/callback"} <= paths


def test_main_app_default_has_no_google_routes():
    from app.main import app as main_app

    if settings.google_login_enabled:
        pytest.skip("구글 로그인이 켜진 환경")
    assert not [r for r in main_app.routes if "/auth/google" in getattr(r, "path", "")]


# ---------- 로그에 비밀 미노출 ----------
def test_no_secrets_in_logs(client, new_flow, complete, caplog, make_token):
    caplog.set_level(logging.DEBUG)
    flow = new_flow()
    token = make_token(flow.nonce)
    resp = complete(flow, token=token, code="SECRET-AUTH-CODE-777")
    assert resp.headers["location"] == OK_URL
    bad = new_flow()
    complete(bad, token=make_token("wrong-nonce"), code="SECRET-AUTH-CODE-888")
    # httpx(테스트 클라이언트 자체)의 요청 로그는 제외하고 앱 코드가 남긴 로그만 검사한다.
    log_text = "\n".join(
        r.getMessage() for r in caplog.records if not r.name.startswith(("httpx", "httpcore", "asyncio"))
    )
    for secret in [CLIENT_SECRET, "SECRET-AUTH-CODE-777", "SECRET-AUTH-CODE-888", token, flow.state, flow.cookie_value]:
        assert secret not in log_text
    assert User.__name__ == "User"


def test_uvicorn_access_log_redacts_callback_code_and_state():
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        (
            "127.0.0.1:1234",
            "GET",
            "/api/v1/auth/google/callback?code=SECRETCODE&state=SECRETSTATE&scope=openid",
            "1.1",
            302,
        ),
        None,
    )
    assert google_wiring.RedactGoogleCallbackFilter().filter(record) is True
    text = record.getMessage()
    assert "SECRETCODE" not in text and "SECRETSTATE" not in text and "[REDACTED]" in text

    other = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:1", "GET", "/api/v1/auth/me?x=1", "1.1", 200),
        None,
    )
    google_wiring.RedactGoogleCallbackFilter().filter(other)
    assert "x=1" in other.getMessage()
