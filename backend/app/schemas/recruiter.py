"""REQ-011: 채용담당자 대시보드 응답 스키마 (unit-12, Feature F).

03-system-design.md §4.2 `/recruiter/reports`에 대응한다. `EVALUATION_REPORTS`
테이블이 아직 없어(unit-10/11 미착수) 점수/추천등급/STAR 등 리포트 본문 필드는
스키마에 포함하지 않는다 — 있는 것처럼 필드를 만들어두고 항상 null을 채우는 방식은
가짜 데이터에 가깝다고 판단해, 대신 `report_available`/`message`로 상태를 정직하게
설명한다(recruiter.py 모듈 docstring 참고).
"""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


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
