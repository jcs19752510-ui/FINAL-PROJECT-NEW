"""03-system-design.md §3.1 ERD의 CONSENTS 테이블 (최소 구현).

unit-2(REQ-002, `/interviews/{id}/start`의 DEC-023 게이트: `ai_interview_notice`
동의 검사)가 구조적으로 필요로 하는 최소 스키마만 여기서 만든다. `POST /consents`,
`GET /users/me/consents`, 철회(`/consents/{id}/revoke`) 등 동의 관리 REST API 전체는
REQ-029/030/032를 담당하는 unit-14/unit-15의 책임이며 이번 유닛 범위가 아니다
(unit-2-note.md "설계서 대비 편차" 참고).
"""
import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ConsentType(StrEnum):
    biometric_voice = "biometric_voice"
    ai_interview_notice = "ai_interview_notice"


class Consent(Base):
    __tablename__ = "consents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    consent_type: Mapped[ConsentType] = mapped_column(Enum(ConsentType, name="consent_type"), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
