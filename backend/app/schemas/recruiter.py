"""REQ-011: 채용담당자 대시보드 응답 스키마 (unit-12, Feature F).

03-system-design.md §4.2 `/recruiter/reports`에 대응한다.

**Feature E(리포트 생성, REQ-009/010/012) 반영**: `EVALUATION_REPORTS` 테이블이
생겼고 `report_status=ready` 실제 경로도 생겼으므로, `RecruiterReportDetailOut`이
`app/schemas/interview.py::ReportOut`(캐노니컬 스키마)의 필드를 그대로 포함한다.
`report_available=false`인 경우(none/queued/failed)에는 여전히 `message`로만
안내하고 점수/STAR 필드는 null이다 — "가짜 데이터 금지" 원칙은 유지한다.
"""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.interview import StarOut


class RecruiterInterviewListItemOut(BaseModel):
    interview_id: UUID
    candidate_name: str
    candidate_email: str
    status: str
    report_status: str
    started_at: datetime | None
    ended_at: datetime | None
    overall_score: Decimal | None


class RecruiterReportDetailOut(BaseModel):
    interview_id: UUID
    candidate_name: str
    candidate_email: str
    status: str
    report_status: str
    started_at: datetime | None
    ended_at: datetime | None
    overall_score: Decimal | None
    report_available: bool
    message: str
    technical_score: int | None = None
    communication_score: int | None = None
    cultural_fit_score: int | None = None
    overall_recommendation: str | None = None
    star: StarOut | None = None
    summary_text: str | None = None
    details: dict | None = None
