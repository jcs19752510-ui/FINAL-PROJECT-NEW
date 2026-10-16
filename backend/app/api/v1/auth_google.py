"""Google 계정 연동 로그인 (2026-10-16, 기존 이메일/비밀번호 인증과 완전히 분리된 신규 라우터).

- GET /auth/google/start    : state/nonce/PKCE 생성 → Google 인증 화면으로 리다이렉트
- GET /auth/google/callback : state 검증 → 코드 교환 → ID Token 검증 → 회원 조회/가입 → 기존 방식의
                              리프레시 쿠키 발급 → 프런트(`/login/google`)로 리다이렉트

기존 `auth.py`는 수정하지 않고 `_set_refresh_cookie`, `create_refresh_token`을 호출만 한다.
신규 가입 역할은 항상 candidate이며, 이미 users에 있는 이메일은 자동 병합하지 않는다.
액세스 토큰은 URL로 넘기지 않는다 — 프런트가 기존 `/auth/refresh`로 받아간다.
"""

import hashlib
import logging
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.auth import _set_refresh_cookie
from app.core.config import settings
from app.core.errors import AppError
from app.core.security import create_refresh_token, hash_password
from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.user_identity import UserIdentity
from app.services import google_oidc
from app.services.google_oidc import GoogleOidcError
from app.services.prompt_safety import RateLimitExceeded, _get_redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/google", tags=["auth-google"])

PROVIDER = "google"
RATE_LIMIT_PER_MINUTE = 30
RESULT_PATH = "/login/google"


def _rate_limit(kind: str, request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    key = f"rate_limit:google_{kind}:{hashlib.sha256(ip.encode()).hexdigest()[:16]}"
    redis = _get_redis()
    count = redis.incr(key)
    if count == 1:
        redis.expire(key, 60)
    if count > RATE_LIMIT_PER_MINUTE:
        raise RateLimitExceeded("google login rate limit")


def _state_key(state: str) -> str:
    return f"google_oauth:state:{hashlib.sha256(state.encode()).hexdigest()}"


def _clear_flow_cookie(response: RedirectResponse) -> None:
    response.delete_cookie(google_oidc.FLOW_COOKIE_NAME, path=google_oidc.FLOW_COOKIE_PATH)


def _redirect(origin: str, **params: str) -> RedirectResponse:
    response = RedirectResponse(f"{origin}{RESULT_PATH}?{urlencode(params)}", status_code=302)
    response.headers["Cache-Control"] = "no-store"
    _clear_flow_cookie(response)
    return response


def _fallback_origin() -> str | None:
    origins = google_oidc.allowed_return_origins()
    return origins[0] if origins else None


@router.get("/start")
def google_start(request: Request, return_to: str | None = None) -> RedirectResponse:
    origin = google_oidc.resolve_return_origin(return_to)
    if origin is None:
        raise AppError(400, "VALIDATION_ERROR", "Bad Request", "허용되지 않은 복귀 주소입니다.")
    try:
        _rate_limit("start", request)
        flow = google_oidc.start_flow(origin)
        # 일회용 보장: 콜백에서 이 키를 삭제(DEL)에 성공한 요청만 통과시킨다.
        _get_redis().set(_state_key(flow.state), "1", ex=google_oidc.FLOW_TTL_SECONDS)
    except RateLimitExceeded:
        return _redirect(origin, error="rate_limited")
    except Exception:
        logger.warning("google login start failed (state store unavailable)")
        return _redirect(origin, error="unavailable")

    response = RedirectResponse(flow.authorize_url, status_code=302)
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        key=google_oidc.FLOW_COOKIE_NAME,
        value=flow.cookie_value,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=google_oidc.FLOW_TTL_SECONDS,
        path=google_oidc.FLOW_COOKIE_PATH,
    )
    return response


def _find_or_create_user(db: Session, profile: google_oidc.GoogleProfile) -> User:
    identity = db.scalar(
        select(UserIdentity).where(UserIdentity.provider == PROVIDER, UserIdentity.provider_sub == profile.sub)
    )
    if identity is not None:
        user = db.get(User, identity.user_id)
        if user is None or user.deleted_at is not None:
            raise GoogleOidcError("account_disabled")
        return user

    # 같은 이메일(대소문자 무시)의 기존 회원이 있으면 자동 연결하지 않는다.
    existing = db.scalar(select(User).where(func.lower(User.email) == profile.email.lower()))
    if existing is not None:
        raise GoogleOidcError("email_exists")

    user = User(
        email=profile.email,
        # 비밀번호 로그인이 불가능한 계정: 아무도 모르는 임의 값의 해시(평문은 즉시 폐기).
        password_hash=hash_password(secrets.token_urlsafe(48)),
        name=profile.name,
        role=UserRole.candidate,
    )
    db.add(user)
    try:
        db.flush()
        db.add(
            UserIdentity(
                user_id=user.id,
                provider=PROVIDER,
                provider_sub=profile.sub,
                email=profile.email,
                email_verified=profile.email_verified,
            )
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        # 같은 구글 계정의 동시 콜백이 먼저 가입을 마쳤을 수 있다 → 그 회원으로 로그인 처리.
        identity = db.scalar(
            select(UserIdentity).where(UserIdentity.provider == PROVIDER, UserIdentity.provider_sub == profile.sub)
        )
        if identity is None:
            raise GoogleOidcError("email_exists") from None
        winner = db.get(User, identity.user_id)
        if winner is None or winner.deleted_at is not None:
            raise GoogleOidcError("account_disabled") from None
        return winner
    db.refresh(user)
    return user


@router.get("/callback")
def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    fallback = _fallback_origin()
    origin = fallback
    try:
        _rate_limit("callback", request)
        flow = google_oidc.read_flow_cookie(request.cookies.get(google_oidc.FLOW_COOKIE_NAME))
        origin = flow.origin if flow.origin in google_oidc.allowed_return_origins() else fallback
        if error:
            raise GoogleOidcError("cancelled")
        if not code or not state or not google_oidc.states_match(state, flow.state):
            raise GoogleOidcError("invalid_state")
        # 일회용: 키 삭제에 실패(이미 사용/만료)하면 재사용으로 본다.
        if _get_redis().delete(_state_key(flow.state)) != 1:
            raise GoogleOidcError("invalid_state")

        id_token = google_oidc.exchange_code(code, flow.verifier)
        profile = google_oidc.verify_id_token(id_token, expected_nonce=flow.nonce)
        user = _find_or_create_user(db, profile)
        refresh_token = create_refresh_token(user.id)
    except RateLimitExceeded:
        return _redirect(origin, error="rate_limited") if origin else _no_origin()
    except GoogleOidcError as exc:
        logger.info("google login rejected: reason=%s", exc.reason)
        return _redirect(origin, error=exc.reason) if origin else _no_origin()
    except Exception:
        db.rollback()
        logger.exception("google login failed unexpectedly")
        return _redirect(origin, error="server_error") if origin else _no_origin()

    if origin is None:
        return _no_origin()
    response = _redirect(origin, status="ok")
    _set_refresh_cookie(response, refresh_token)
    logger.info("google login ok: user_id=%s", user.id)
    return response


def _no_origin() -> RedirectResponse:
    raise AppError(400, "VALIDATION_ERROR", "Bad Request", "복귀 주소 설정이 없습니다.")
