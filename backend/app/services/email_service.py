"""Feature J 후속(2026-09-30, 사용자 지시) — 합격/불합격 결정 시 지원자 안내 메일을
백엔드가 완전 자동으로 발송한다. Gmail SMTP + 앱 비밀번호(일반 로그인 비밀번호
아님) 사용 — MCP 메일 도구는 이 세션 안에서만 동작해 배포된 백엔드가 스스로
호출할 수 없으므로(§2 결정, DEC 기록) 채택하지 않는다.
"""
import logging
import smtplib
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)

_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 587
_SMTP_TIMEOUT_SECONDS = 10


class EmailSendError(Exception):
    """SMTP 발송 실패 — 호출부가 잡아서 판단 저장 자체는 막지 않고 우아하게
    처리한다(prosody_engine과 동일한 관용구: 부가 기능 실패가 핵심 흐름을
    막지 않는다)."""


def email_configured() -> bool:
    return bool(settings.gmail_address and settings.gmail_app_password)


def send_notification_email(to_email: str, subject: str, body: str) -> None:
    if not email_configured():
        raise EmailSendError("GMAIL_ADDRESS/GMAIL_APP_PASSWORD가 설정되지 않았습니다.")

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.gmail_address
    msg["To"] = to_email

    try:
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=_SMTP_TIMEOUT_SECONDS) as server:
            server.starttls()
            server.login(settings.gmail_address, settings.gmail_app_password)
            server.sendmail(settings.gmail_address, [to_email], msg.as_string())
    except Exception as exc:
        logger.warning("이메일 자동 발송 실패 (to=%s): %s", to_email, exc)
        raise EmailSendError(f"이메일 발송에 실패했습니다: {exc}") from exc
