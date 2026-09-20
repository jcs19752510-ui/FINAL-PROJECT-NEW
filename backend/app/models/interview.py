"""03-system-design.md §3.1 ERD의 INTERVIEWS 테이블 (REQ-002, Feature B).

`rubric_template_id`는 ERD상 FK이나, 이를 가리키는 RUBRIC_TEMPLATES 테이블은
unit-13(REQ-014, Feature F)이 아직 만들지 않았다. unit-1이 확립한 선례(03-design
§3.3 "이후 변경은 유닛 단위로 순차 revision 추가")를 그대로 따라, 이번 유닛에서는
nullable UUID 컬럼만 만들고 FK 제약은 unit-13이 RUBRIC_TEMPLATES를 만들 때 별도
revision으로 추가한다(unit-2-note.md "설계서 대비 편차" 참고). MVP 기본 경로(§6.1,
지원자 자율 연습)에서는 이 값이 항상 null이다.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class InterviewStatus(StrEnum):
    scheduled = "scheduled"
    live = "live"
    paused = "paused"
    completed = "completed"
    expired = "expired"


class ReportStatus(StrEnum):
    none = "none"
    queued = "queued"
    ready = "ready"
    failed = "failed"


class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    recruiter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # FK 제약 없음(위 모듈 docstring 참고) — unit-13이 RUBRIC_TEMPLATES 생성 시 추가.
    rubric_template_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[InterviewStatus] = mapped_column(
        Enum(InterviewStatus, name="interview_status"), nullable=False, default=InterviewStatus.scheduled
    )
    report_status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus, name="report_status"), nullable=False, default=ReportStatus.none
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 1), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
