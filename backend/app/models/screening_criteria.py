"""이력서 AI 합격 판정용 면접기준(2026-10-14 사용자 요청).

회사 공통 1개 — 이 테이블에는 행이 최대 1개만 존재한다(없으면 `version=0`인 미등록 상태로 취급).
`version`은 기준이 저장될 때마다 1씩 증가하며, 이력서의 `ai_criteria_version`과 다르면
"현재 기준으로 미분석"이므로 1분 배치가 다시 분석한다.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

DEFAULT_PASS_THRESHOLD = 70
MAX_CRITERIA_CHARS = 4000
MAX_AI_ATTEMPTS = 3  # 분석 실패 시 자동 재시도 상한(상한 도달 시 failed 로 표시)


class ScreeningCriteria(Base):
    __tablename__ = "screening_criteria"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    criteria_text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    pass_threshold: Mapped[int] = mapped_column(Integer, nullable=False, server_default=str(DEFAULT_PASS_THRESHOLD))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
