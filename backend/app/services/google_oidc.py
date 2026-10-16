"""Google OAuth 2.0 / OpenID Connect(Authorization Code + PKCE) 보조 함수 (2026-10-16).

이 모듈은 Google과의 통신·검증만 담당하고 회원 DB/세션은 건드리지 않는다
(app/api/v1/auth_google.py 가 사용). google-auth / requests 는 함수 안에서 지연 임포트한다 —
라이브러리에 문제가 있어도 앱 기동과 기존 로그인에 영향이 없도록 하기 위함이다.
토큰/코드/Client Secret은 어떤 경우에도 로그나 예외 메시지에 싣지 않는다.
"""

import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

from jose import JWTError, jwt

from app.core.config import settings

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
SCOPES = "openid email profile"
HTTP_TIMEOUT_SECONDS = 10
FLOW_TTL_SECONDS = 600
FLOW_COOKIE_NAME = "g_oauth"
FLOW_COOKIE_PATH = "/api/v1/auth/google"


class GoogleOidcError(Exception):
    """`reason`은 프런트로 전달되는 짧은 오류 코드다(내부 상세는 담지 않는다)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class GoogleProfile:
    sub: str
    email: str
    email_verified: bool
    name: str


def _flow_key() -> bytes:
    # 기존 JWT(access/refresh)와 서명 키를 분리한다: 같은 비밀값에서 파생하되 용도 문자열을 섞어,
    # 이 쿠키가 기존 인증 토큰으로 통용되거나 그 반대가 되지 않게 한다.
    return hashlib.sha256(f"{settings.jwt_secret_key}|google_oauth_flow".encode()).digest()


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def pkce_challenge(verifier: str) -> str:
    return _b64url(hashlib.sha256(verifier.encode()).digest())


def allowed_return_origins() -> list[str]:
    return [o.strip().rstrip("/") for o in settings.google_allowed_return_origins.split(",") if o.strip()]


def resolve_return_origin(return_to: str | None) -> str | None:
    """허용 목록과 **정확히 일치**하는 오리진만 돌려준다(Open Redirect 방지). 없으면 첫 번째 허용 오리진."""
    origins = allowed_return_origins()
    if not origins:
        return None
    if return_to is None or return_to == "":
        return origins[0]
    candidate = return_to.strip().rstrip("/")
    return candidate if candidate in origins else None


@dataclass(frozen=True)
class FlowStart:
    state: str
    cookie_value: str
    authorize_url: str


def start_flow(origin: str) -> FlowStart:
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    now = int(time.time())
    cookie_value = jwt.encode(
        {
            "typ": "google_oauth",
            "state": state,
            "nonce": nonce,
            "cv": verifier,
            "origin": origin,
            "iat": now,
            "exp": now + FLOW_TTL_SECONDS,
        },
        _flow_key(),
        algorithm="HS256",
    )
    query = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "state": state,
            "nonce": nonce,
            "code_challenge": pkce_challenge(verifier),
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
    )
    return FlowStart(state=state, cookie_value=cookie_value, authorize_url=f"{AUTH_ENDPOINT}?{query}")


@dataclass(frozen=True)
class FlowState:
    state: str
    nonce: str
    verifier: str
    origin: str


def read_flow_cookie(cookie_value: str | None) -> FlowState:
    if not cookie_value:
        raise GoogleOidcError("invalid_state")
    try:
        data = jwt.decode(cookie_value, _flow_key(), algorithms=["HS256"])
    except JWTError as exc:
        raise GoogleOidcError("invalid_state") from exc
    if data.get("typ") != "google_oauth":
        raise GoogleOidcError("invalid_state")
    return FlowState(state=data["state"], nonce=data["nonce"], verifier=data["cv"], origin=data["origin"])


def states_match(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def exchange_code(code: str, verifier: str) -> str:
    """인증 코드를 서버에서 토큰 엔드포인트로 교환해 id_token 원문만 돌려준다(access/refresh 토큰은 버린다)."""
    import requests

    try:
        resp = requests.post(
            TOKEN_ENDPOINT,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": verifier,
            },
            timeout=HTTP_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise GoogleOidcError("unavailable") from exc
    if resp.status_code != 200:
        raise GoogleOidcError("token_exchange_failed")
    try:
        id_token = resp.json().get("id_token")
    except ValueError as exc:
        raise GoogleOidcError("token_exchange_failed") from exc
    if not id_token:
        raise GoogleOidcError("token_exchange_failed")
    return id_token


def _default_http_request():
    from google.auth.transport import requests as google_requests

    class _TimeoutRequest(google_requests.Request):
        def __call__(self, url, method="GET", body=None, headers=None, timeout=HTTP_TIMEOUT_SECONDS, **kwargs):
            return super().__call__(url, method, body, headers, timeout=timeout, **kwargs)

    return _TimeoutRequest()


def verify_id_token(raw_id_token: str, *, expected_nonce: str, http_request=None) -> GoogleProfile:
    """서명(Google 공개 인증서), iss, aud, exp 를 검증한 뒤 nonce까지 확인한다. 단순 디코딩이 아니다."""
    from google.auth import exceptions as google_exceptions
    from google.oauth2 import id_token as google_id_token

    try:
        claims = google_id_token.verify_oauth2_token(
            raw_id_token,
            http_request or _default_http_request(),
            audience=settings.google_client_id,
            clock_skew_in_seconds=10,
        )
    except google_exceptions.TransportError as exc:  # Google 인증서 조회 실패 → 서비스 불가(토큰 탓이 아님)
        raise GoogleOidcError("unavailable") from exc
    except (ValueError, google_exceptions.GoogleAuthError) as exc:  # 서명/aud/exp/iss 검증 실패
        raise GoogleOidcError("invalid_token") from exc
    except Exception as exc:  # 그 밖의 예기치 않은 오류 — 로그인 실패로만 처리
        raise GoogleOidcError("unavailable") from exc

    if not hmac.compare_digest(str(claims.get("nonce", "")).encode(), expected_nonce.encode()):
        raise GoogleOidcError("invalid_token")
    sub = claims.get("sub")
    email = claims.get("email")
    if not sub or not email or len(str(sub)) > 255 or len(str(email)) > 255:
        raise GoogleOidcError("invalid_token")
    verified = claims.get("email_verified")
    # Google은 bool 또는 "true" 문자열로 줄 수 있다.
    email_verified = verified is True or str(verified).lower() == "true"
    if not email_verified:
        raise GoogleOidcError("email_unverified")
    email = str(email).strip()
    name = str(claims.get("name") or email.split("@", 1)[0]).strip()[:100] or "구글 사용자"
    return GoogleProfile(sub=str(sub), email=email, email_verified=True, name=name)
