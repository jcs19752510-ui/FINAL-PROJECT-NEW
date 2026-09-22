"""03-system-design.md §3.1 ERD의 EVALUATION_REPORTS 테이블 (REQ-009/010/012, Feature E).

`interview_id`는 UK(면접 1건당 리포트 1건, `POST /report/regenerate`는 기존 행을
갱신한다). `overall_recommendation`은 REQ-031(개인정보 보호법 제37조의2 자동화된
결정 거부권)에 따라 `recommend/neutral/not_recommend` 3단계 권고 등급만 허용하고,
"합격/불합격 확정" 필드는 스키마에 만들지 않는다(§3.2). `star_json`이 1차
데이터소스이고 `summary_text`는 LLM이 STAR 스키마 파싱에 실패했을 때만 채워지는
폴백 전용 필드다(§4.4). `star_json`/`summary_text`/`details_json`은 REQ-036
새니타이즈 대상 — 이 값들을 렌더링하는 화면(프런트)이 XSS 방어를 책임진다(저장
시점에는 원문 그대로 보관, `app/models/code_submission.py`의 동일 원칙 참고).
"""
import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class OverallRecommendation(StrEnum):
    recommend = "recommend"
    neutral = "neutral"
    not_recommend = "not_recommend"


class EvaluationReport(Base):
    __tablename__ = "evaluation_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interviews.id"), nullable=False, unique=True, index=True
    )
    technical_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    communication_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cultural_fit_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overall_recommendation: Mapped[OverallRecommendation | None] = mapped_column(
        Enum(OverallRecommendation, name="overall_recommendation"), nullable=True
    )
    # {"situation": str, "task": str, "action": str, "result": str} — §4.4. 파싱
    # 성공 시에만 채워지고, 실패 시 null(그 경우 summary_text가 폴백으로 채워짐).
    star_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
