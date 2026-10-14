"""Feature J(REQ-040~044) — 이력서 지원서 스키마."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.resume_application import ResumeApplicationStatus


class MyResumeStatusOut(BaseModel):
    """`GET /users/me/resume-status` — 지원자 본인이 볼 수 있는 최소 정보.
    `reviewed_by`/`notified_at` 등 내부 감사 필드는 노출하지 않는다.
    """

    id: UUID
    status: ResumeApplicationStatus
    original_filename: str
    decision_note: str | None
    interview_schedule_note: str | None
    submitted_at: datetime
    reviewed_at: datetime | None
    profile_status: str = "pending"

    model_config = {"from_attributes": True}


class AiCriterionOut(BaseModel):
    name: str
    score: int
    evidence: str


class AiReasonsOut(BaseModel):
    summary: str = ""
    criteria: list[AiCriterionOut] = []
    strengths: list[str] = []
    concerns: list[str] = []


class RecruiterResumeListItemOut(BaseModel):
    id: UUID
    candidate_id: UUID
    candidate_name: str
    candidate_email: str
    status: ResumeApplicationStatus
    original_filename: str
    submitted_at: datetime
    reviewed_at: datetime | None
    notified_at: datetime | None
    ai_state: str = "no_criteria"
    ai_verdict: str | None = None
    ai_score: int | None = None
    ai_analyzed_at: datetime | None = None


class RecruiterResumeDetailOut(RecruiterResumeListItemOut):
    ai_threshold: int | None = None
    ai_criteria_version: int | None = None
    current_criteria_version: int = 0
    ai_stale: bool = False
    ai_error: str | None = None
    ai_reasons: AiReasonsOut | None = None
    content_type: str
    file_size_bytes: int
    decision_note: str | None
    interview_schedule_note: str | None


class ResumeDecisionIn(BaseModel):
    # pending으로 되돌리는 것은 이 엔드포인트의 책임이 아니다(재제출 시 자동으로만
    # pending이 된다) — 관리자는 accepted/rejected만 명시적으로 선택한다.
    status: ResumeApplicationStatus
    decision_note: str | None = None
    interview_schedule_note: str | None = None


class NotificationDraftOut(BaseModel):
    """프롬프트 §2 결정#3(반자동 통보) — 관리자가 이 내용을 그대로 복사해
    본인의 Claude+MCP 메일 도구로 발송한다. 백엔드는 발송하지 않는다.
    """

    to_email: str
    subject: str
    body: str
