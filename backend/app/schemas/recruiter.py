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

from pydantic import BaseModel, EmailStr, Field

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
