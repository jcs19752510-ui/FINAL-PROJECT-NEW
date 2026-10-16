"""외부 인증 제공자(Google) 계정과 내부 회원(users)의 연결 (2026-10-16).

users 테이블은 변경하지 않는다. 식별 기준은 이메일이 아니라 제공자의 불변 식별자(`sub`)이며
(provider, provider_sub)에 UNIQUE 제약을 둔다. Google 토큰(access/id/refresh)은 저장하지 않는다.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class UserIdentity(Base):
    __tablename__ = "user_identities"
    __table_args__ = (UniqueConstraint("provider", "provider_sub", name="uq_user_identities_provider_sub"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
