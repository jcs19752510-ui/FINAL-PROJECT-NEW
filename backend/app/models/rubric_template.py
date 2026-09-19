"""03-system-design.md §3.1 ERD의 RUBRIC_TEMPLATES 테이블 (REQ-014, Feature F, unit-13).

`recruiter_id`가 null이면 "시스템 기본 템플릿"(§3.1 주석, 04-ux-design [R-03] 빈 상태
"기본 템플릿을 복사해 시작하세요")이다. `interviews.rubric_template_id`는 unit-2가
FK 제약 없이 nullable 컬럼만 만들어 두었고(app/models/interview.py 참고), 이 유닛의
마이그레이션에서 FK 제약을 추가한다.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class RubricTemplate(Base):
    __tablename__ = "rubric_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recruiter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # [{"name": str, "weight": int(0~100), "description": str}, ...] — 03-design §4.2
    # "RUBRIC_TEMPLATES(name, criteria_json)와 1:1 대응, 갭 없음" 원문 그대로.
    criteria_json: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
