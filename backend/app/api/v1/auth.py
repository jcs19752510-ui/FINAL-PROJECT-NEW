"""REQ-001: 회원가입/로그인/역할관리 (03-system-design.md §4.2, §6.1)."""
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.errors import AppError
from app.core.security import (
    JWTError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import AccessTokenResponse, LoginRequest, RegisterRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "refresh_token"


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.jwt_refresh_token_expire_days * 24 * 60 * 60,
        path="/api/v1/auth",
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> User:
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise AppError(409, "VALIDATION_ERROR", "Conflict", "이미 가입된 이메일입니다.")

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        name=payload.name,
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email))
    # 계정 존재 여부를 노출하지 않기 위해 이메일 불일치/비밀번호 불일치를 동일 에러로 처리한다
    # (04-ux-design.md [C-02] 보안 원칙).
    if user is None or user.deleted_at is not None or not verify_password(payload.password, user.password_hash):
        raise AppError(401, "AUTH_INVALID_TOKEN", "Unauthorized", "이메일 또는 비밀번호가 올바르지 않습니다.")

    access_token = create_access_token(user.id, user.role.value)
    refresh_token = create_refresh_token(user.id)
    _set_refresh_cookie(response, refresh_token)

    return TokenResponse(access_token=access_token, user=UserOut.model_validate(user))


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh(request: Request, db: Session = Depends(get_db)) -> AccessTokenResponse:
    """03-system-design.md §6.1이 refresh 토큰(httpOnly 쿠키) 존재를 명시했으나 별도 엔드포인트
    스펙은 API 표(§4.2)에 없다 — 표준 JWT refresh 관례로 최소 구현한다(unit-1-note.md 편차 기록).
    refresh 토큰 자체는 재발급하지 않는다(회전 없음, MVP 최소 구현)."""
    token = request.cookies.get(REFRESH_COOKIE_NAME)
    if token is None:
        raise AppError(401, "AUTH_INVALID_TOKEN", "Unauthorized", "refresh 토큰이 없습니다.")

    try:
        payload = decode_token(token)
    except JWTError as exc:
        raise AppError(401, "AUTH_INVALID_TOKEN", "Unauthorized", "유효하지 않거나 만료된 refresh 토큰입니다.") from exc

    if payload.get("type") != "refresh":
        raise AppError(401, "AUTH_INVALID_TOKEN", "Unauthorized", "refresh 토큰이 아닙니다.")

    user = db.get(User, UUID(payload["sub"]))
    if user is None or user.deleted_at is not None:
        raise AppError(401, "AUTH_INVALID_TOKEN", "Unauthorized", "사용자를 찾을 수 없습니다.")

    return AccessTokenResponse(access_token=create_access_token(user.id, user.role.value))


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
