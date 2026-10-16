"""Google 로그인 라우터를 앱에 연결하는 단일 지점 (2026-10-16).

`GOOGLE_LOGIN_ENABLED`가 꺼져 있거나 필수 설정이 비어 있으면 라우터를 **등록하지 않는다**(→ 경로 404).
등록 중 어떤 오류가 나도 앱 기동과 기존 라우터에는 영향이 없도록 예외를 삼키고 경고만 남긴다.
"""

import logging
import re

from fastapi import FastAPI

from app.core.config import settings

logger = logging.getLogger(__name__)

_SENSITIVE_QUERY = re.compile(r"([?&](?:code|state|scope|authuser|prompt|hd)=)[^&\s\"]*")


class RedactGoogleCallbackFilter(logging.Filter):
    """uvicorn 액세스 로그의 `/auth/google/callback?code=...&state=...` 에서 인증 코드·state를 가린다."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if (
            isinstance(args, tuple)
            and len(args) >= 3
            and isinstance(args[2], str)
            and "/auth/google/callback" in args[2]
        ):
            record.args = (*args[:2], _SENSITIVE_QUERY.sub(r"\1[REDACTED]", args[2]), *args[3:])
        return True


def _install_log_redaction() -> None:
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, RedactGoogleCallbackFilter) for f in access.filters):
        access.addFilter(RedactGoogleCallbackFilter())


def google_login_ready() -> bool:
    return bool(
        settings.google_login_enabled
        and settings.google_client_id
        and settings.google_client_secret
        and settings.google_redirect_uri
    )


def include_google_login(app: FastAPI) -> bool:
    if not settings.google_login_enabled:
        return False
    if not google_login_ready():
        logger.warning(
            "GOOGLE_LOGIN_ENABLED=true 이지만 GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET/GOOGLE_REDIRECT_URI 중 "
            "비어 있는 값이 있어 Google 로그인을 비활성 상태로 둡니다. 기존 로그인은 영향 없습니다."
        )
        return False
    try:
        from app.api.v1.auth_google import router as auth_google_router

        app.include_router(auth_google_router, prefix="/api/v1")
        _install_log_redaction()
    except Exception:
        logger.exception("Google 로그인 라우터 등록에 실패해 비활성 상태로 둡니다. 기존 로그인은 영향 없습니다.")
        return False
    return True
