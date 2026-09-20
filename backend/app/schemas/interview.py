from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class InterviewOut(BaseModel):
    id: UUID
    candidate_id: UUID
    recruiter_id: UUID | None
    rubric_template_id: UUID | None
    status: str
    report_status: str
    started_at: datetime | None
    ended_at: datetime | None
    overall_score: Decimal | None
    created_at: datetime

    model_config = {"from_attributes": True}


class InterviewDetailOut(InterviewOut):
    """REQ-013(unit-3): 세션 메타데이터 기준 재개 가능 여부 판단용 상세 조회 응답.

    `resumable`은 `status`가 `live`/`paused`일 때만 true — 클라이언트가 [C-12] 세션
    재개 화면에서 "이어서 진행" 버튼을 노출할지 판단하는 데 쓰는 파생 필드([C-12] 04-ux-design
    §2 참고). turn_index/코드/화이트보드 등 실제 콘텐츠 복원 필드는 이 유닛의 책임이
    아니다(unit-4/unit-9가 TRANSCRIPTS/CODE_SUBMISSIONS/WHITEBOARD_SNAPSHOTS 모델을
    만든 뒤 별도 응답 필드로 추가해야 함, unit-3-note.md 참고).
    """

    resumable: bool


class InterviewListItemOut(BaseModel):
    """REQ-002(unit-19): `GET /interviews`(내 면접 목록) 항목. [C-03] 지원자 홈 전용.

    03-design §4.2가 명시한 `status`/`report_status`/`started_at`/`overall_score`에 목록
    렌더링에 필요한 최소 필드(`id`/`ended_at`/`created_at`)와 파생 필드 `resumable`을
    더한다. 본인 소유 목록이지만 `candidate_id`/`recruiter_id`/`rubric_template_id` 같은
    내부 식별자는 이 화면이 쓰지 않으므로 응답에서 제외한다(최소 노출).
    """

    id: UUID
    status: str
    report_status: str
    started_at: datetime | None
    ended_at: datetime | None
    overall_score: Decimal | None
    created_at: datetime
    resumable: bool

    model_config = {"from_attributes": True}


class InterviewStartResponse(BaseModel):
    job_id: str
    message: str = "AI가 첫 질문을 준비 중입니다"
    interview: InterviewOut


class InterviewEndResponse(BaseModel):
    job_id: str
    interview: InterviewOut
