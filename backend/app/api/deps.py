from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import JWTError, decode_token
from app.db.session import get_db
from app.models.user import User

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise AppError(401, "AUTH_INVALID_TOKEN", "Unauthorized", "인증 토큰이 필요합니다.")
    try:
        payload = decode_token(credentials.credentials)
    except JWTError as exc:
        raise AppError(401, "AUTH_INVALID_TOKEN", "Unauthorized", "유효하지 않거나 만료된 토큰입니다.") from exc

    if payload.get("type") != "access":
        raise AppError(401, "AUTH_INVALID_TOKEN", "Unauthorized", "액세스 토큰이 아닙니다.")

    user_id = payload.get("sub")
    if user_id is None:
        raise AppError(401, "AUTH_INVALID_TOKEN", "Unauthorized", "토큰에 사용자 정보가 없습니다.")

    user = db.get(User, UUID(user_id))
    if user is None or user.deleted_at is not None:
        raise AppError(401, "AUTH_INVALID_TOKEN", "Unauthorized", "사용자를 찾을 수 없습니다.")

    return user
