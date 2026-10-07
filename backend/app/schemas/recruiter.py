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
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.interview import RubricOut, StarOut


# 2026-09-30(사용자 지시): 채용담당자(recruiter) 계정은 더 이상 공개 회원가입
# (`POST /auth/register`)으로 만들 수 없다 — 그 엔드포인트는 role을 candidate로
# 고정 제한했다(app/schemas/user.py::RegisterRequest). 이 스키마는 "이미 로그인한
# 채용담당자만" 호출 가능한 신규 보호 엔드포인트(`POST /recruiter/recruiters`)
# 전용이며, role 필드 자체가 없다 — 항상 recruiter로 고정 생성되므로 호출자가
# 임의로 다른 role을 지정할 수 있는 여지를 아예 없앴다.
class RecruiterCreateIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=100)


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
    pass_fail_recommendation: str | None = None
    star: StarOut | None = None
    summary_text: str | None = None
    details: dict | None = None
    # v15(03-system-design v4 §4.6 (5), unit-37) — [R-02]도 [C-11]과 같은 루브릭
    # 섹션을 쓴다(04-ux-design.md [C-11]/[R-02] 공통 명세).
    rubric: RubricOut | None = None
    # 최종 합격/불합격(2026-10-07) — 미처리면 전부 None.
    final_decision: Literal["accepted", "rejected"] | None = None
    final_decision_note: str | None = None
    final_decided_at: datetime | None = None
    final_notified_at: datetime | None = None


class FinalDecisionOut(BaseModel):
    interview_id: UUID
    final_decision: Literal["accepted", "rejected"] | None = None
    final_decision_note: str | None = None
    final_decided_at: datetime | None = None
    final_notified_at: datetime | None = None


class FinalDecisionIn(BaseModel):
    """최종 합격/불합격 처리 입력. 안내 문구는 필수(이력서 합격 처리와 동일)이며,
    프런트가 드롭다운으로만 고르게 하지만 서버도 공백·과도한 길이를 거부한다."""

    status: Literal["accepted", "rejected"]
    decision_note: str = Field(min_length=1, max_length=500)

    # 앞뒤 공백을 먼저 제거한 뒤 길이(1~500)를 검사한다(공백만 입력하면 빈 문자열로 422).
    @field_validator("decision_note", mode="before")
    @classmethod
    def _strip_note(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v
