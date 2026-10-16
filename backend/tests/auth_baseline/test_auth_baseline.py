"""기존 이메일/비밀번호 인증의 현재 동작을 고정하는 기준선(characterization) 테스트.

Google 로그인 추가 작업(2026-10-16)이 기존 register/login/refresh/me 동작을 한 비트도 바꾸지
않았음을 증명하기 위한 것이다. 이 파일은 구글 작업 **이전**의 코드에서 먼저 작성·통과시켰고,
작업 후에도 수정 없이 통과해야 한다. 이 테스트가 실패하면 기존 로그인이 바뀐 것이다.

추가로 `BASELINE_MODE=record|compare` + `BASELINE_SNAPSHOT_PATH`를 주면 응답 형태(상태코드, 키 집합,
Set-Cookie 속성, 에러 문구)를 JSON으로 기록/비교한다.
"""

import json
import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import psycopg
import pytest
from jose import jwt

from tests.support.accounts import API_V1, AccountFactory, _database_url, new_marker_email

WRONG_LOGIN_DETAIL = "이메일 또는 비밀번호가 올바르지 않습니다."


def _register(api: httpx.Client, factory: AccountFactory, **overrides):
    email = overrides.pop("email", new_marker_email())
    password = overrides.pop("password", secrets.token_urlsafe(16))
    body = {"email": email, "password": password, "name": "기준선", "role": "candidate", **overrides}
    resp = api.post(f"{API_V1}/auth/register", json=body)
    if resp.status_code == 201:
        factory.created_emails.append(email)
    return email, password, resp


def _login(api: httpx.Client, email: str, password: str) -> httpx.Response:
    resp = api.post(f"{API_V1}/auth/login", json={"email": email, "password": password})
    return resp


def _set_cookie_attrs(resp: httpx.Response) -> dict:
    header = next((v for k, v in resp.headers.multi_items() if k.lower() == "set-cookie"), None)
    assert header is not None, "로그인 응답에 Set-Cookie가 없습니다"
    parts = [p.strip() for p in header.split(";")]
    name, _, _ = parts[0].partition("=")
    attrs = {"name": name}
    for p in parts[1:]:
        k, _, v = p.partition("=")
        attrs[k.lower()] = v or True
    return attrs


def test_register_success_shape(api, account_factory):
    email, _, resp = _register(api, account_factory)
    assert resp.status_code == 201
    body = resp.json()
    assert set(body) == {"id", "email", "name", "role", "created_at"}
    assert body["email"] == email and body["role"] == "candidate" and body["name"] == "기준선"
    assert "password" not in json.dumps(body) and "hash" not in json.dumps(body).lower()


def test_register_duplicate_email_409(api, account_factory):
    email, _, first = _register(api, account_factory)
    assert first.status_code == 201
    _, _, dup = _register(api, account_factory, email=email)
    assert dup.status_code == 409
    assert dup.json()["detail"] == "이미 가입된 이메일입니다."


@pytest.mark.parametrize("role", ["recruiter", "admin"])
def test_register_rejects_non_candidate_role(api, account_factory, role):
    _, _, resp = _register(api, account_factory, role=role)
    assert resp.status_code == 422


def test_register_validation(api):
    short = api.post(f"{API_V1}/auth/register", json={"email": new_marker_email(), "password": "short", "name": "x"})
    assert short.status_code == 422
    bad_email = api.post(
        f"{API_V1}/auth/register", json={"email": "not-an-email", "password": "longenough1", "name": "x"}
    )
    assert bad_email.status_code == 422


def test_login_success_shape_and_cookie(api, account_factory):
    email, password, _ = _register(api, account_factory)
    resp = _login(api, email, password)
    api.cookies.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"access_token", "token_type", "user"}
    assert body["token_type"] == "bearer"
    assert set(body["user"]) == {"id", "email", "name", "role", "created_at"}
    claims = jwt.get_unverified_claims(body["access_token"])
    assert claims["type"] == "access" and claims["role"] == "candidate" and claims["sub"] == body["user"]["id"]
    cookie = _set_cookie_attrs(resp)
    assert cookie["name"] == "refresh_token"
    assert cookie.get("httponly") is True
    assert str(cookie.get("samesite")).lower() == "lax"
    assert cookie.get("path") == "/api/v1/auth"
    assert cookie.get("max-age") == str(7 * 24 * 60 * 60)
    assert ("secure" in cookie) == (os.environ.get("COOKIE_SECURE", "true").lower() == "true")


def test_login_failures_are_identical_401(api, account_factory):
    email, password, _ = _register(api, account_factory)
    wrong_pw = _login(api, email, "wrong-password-xyz")
    unknown = _login(api, new_marker_email(), password)
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json() == unknown.json()
    assert wrong_pw.json()["detail"] == WRONG_LOGIN_DETAIL
    assert "set-cookie" not in wrong_pw.headers and "set-cookie" not in unknown.headers


def test_login_deleted_account_same_401(api, account_factory):
    email, password, resp = _register(api, account_factory)
    with psycopg.connect(_database_url(), connect_timeout=5) as conn, conn.cursor() as cur:
        cur.execute("UPDATE users SET deleted_at = now() WHERE email = %s", (email,))
    deleted = _login(api, email, password)
    unknown = _login(api, new_marker_email(), password)
    assert deleted.status_code == 401
    assert deleted.json() == unknown.json()


def test_refresh_flow(api, account_factory):
    email, password, _ = _register(api, account_factory)
    login = _login(api, email, password)
    refresh_token = login.cookies.get("refresh_token") or _set_cookie_attrs(login)  # httpx가 쿠키를 저장
    resp = api.post(f"{API_V1}/auth/refresh")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"access_token", "token_type"} and body["token_type"] == "bearer"
    me = api.get(f"{API_V1}/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200 and me.json()["email"] == email
    api.cookies.clear()
    assert refresh_token


def test_refresh_rejections(api, account_factory):
    api.cookies.clear()
    no_cookie = api.post(f"{API_V1}/auth/refresh")
    assert no_cookie.status_code == 401

    garbage = httpx.post(f"{api.base_url}{API_V1}/auth/refresh", cookies={"refresh_token": "not.a.jwt"})
    assert garbage.status_code == 401

    email, password, _ = _register(api, account_factory)
    login = _login(api, email, password)
    api.cookies.clear()
    access = login.json()["access_token"]
    as_refresh = httpx.post(f"{api.base_url}{API_V1}/auth/refresh", cookies={"refresh_token": access})
    assert as_refresh.status_code == 401


def test_me_variants(api, account_factory):
    email, password, _ = _register(api, account_factory)
    login = _login(api, email, password)
    api.cookies.clear()
    token = login.json()["access_token"]

    ok = api.get(f"{API_V1}/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200 and set(ok.json()) == {"id", "email", "name", "role", "created_at"}

    assert api.get(f"{API_V1}/auth/me").status_code == 401
    assert api.get(f"{API_V1}/auth/me", headers={"Authorization": "Bearer abc.def.ghi"}).status_code == 401

    claims = jwt.get_unverified_claims(token)
    forged = jwt.encode({**claims, "exp": datetime.now(UTC) + timedelta(minutes=5)}, "wrong-secret", algorithm="HS256")
    assert api.get(f"{API_V1}/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401

    expired = jwt.encode(
        {**claims, "exp": datetime.now(UTC) - timedelta(minutes=5)},
        os.environ.get("JWT_SECRET_KEY", ""),
        algorithm="HS256",
    )
    if os.environ.get("JWT_SECRET_KEY"):
        assert api.get(f"{API_V1}/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401

    refresh_like = jwt.encode(
        {"sub": claims["sub"], "type": "refresh", "exp": datetime.now(UTC) + timedelta(minutes=5)},
        os.environ.get("JWT_SECRET_KEY", "x"),
        algorithm="HS256",
    )
    if os.environ.get("JWT_SECRET_KEY"):
        assert api.get(f"{API_V1}/auth/me", headers={"Authorization": f"Bearer {refresh_like}"}).status_code == 401


def test_unknown_auth_paths_stay_404_without_google(api):
    """구글 로그인이 꺼진 기본 상태에서 /auth/google/* 는 존재하지 않아야 한다(작업 후에도 동일)."""
    if os.environ.get("GOOGLE_LOGIN_ENABLED", "false").lower() == "true":
        pytest.skip("구글 로그인이 켜진 실행에서는 해당 없음")
    assert api.get(f"{API_V1}/auth/google/start", follow_redirects=False).status_code == 404
    assert api.get(f"{API_V1}/auth/google/callback", follow_redirects=False).status_code == 404


def test_snapshot_record_or_compare(api, account_factory):
    mode = os.environ.get("BASELINE_MODE")
    path = os.environ.get("BASELINE_SNAPSHOT_PATH")
    if not mode or not path:
        pytest.skip("BASELINE_MODE/BASELINE_SNAPSHOT_PATH 미지정")
    email, password, reg = _register(api, account_factory)
    dup = _register(api, account_factory, email=email)[2]
    login = _login(api, email, password)
    api.cookies.clear()
    bad = _login(api, email, "nope-nope-nope")
    me_noauth = api.get(f"{API_V1}/auth/me")
    refresh_noauth = api.post(f"{API_V1}/auth/refresh")
    cookie = _set_cookie_attrs(login)
    cookie.pop("expires", None)
    snap = {
        "register": [reg.status_code, sorted(reg.json())],
        "register_dup": [dup.status_code, dup.json()],
        "login": [login.status_code, sorted(login.json()), sorted(login.json()["user"])],
        "login_cookie": cookie,
        "login_bad": [bad.status_code, bad.json()],
        "me_noauth": [me_noauth.status_code, me_noauth.json()],
        "refresh_noauth": [refresh_noauth.status_code, refresh_noauth.json()],
    }
    target = Path(path)
    if mode == "record":
        target.write_text(json.dumps(snap, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    else:
        assert json.loads(target.read_text(encoding="utf-8")) == json.loads(json.dumps(snap, sort_keys=True))
    _ = uuid
