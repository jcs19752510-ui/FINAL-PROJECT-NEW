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


class StarOut(BaseModel):
    situation: str
    task: str
    action: str
    result: str


# REQ-031(개인정보 보호법 제37조의2 자동화된 결정 거부권): 모든 리포트 응답에 고정
# 문구로 포함한다 — `overall_recommendation`이 권고 등급일 뿐 최종판정이 아님을
# 매 응답마다 명시한다(03-design §8 "자동화된 결정 금지" 그대로).
REPORT_DISCLAIMER = "이 결과는 참고용 AI 평가이며, 최종 채용 결정은 인간이 내립니다."


class ReportOut(BaseModel):
    """`GET /interviews/{id}/report` — 지원자([C-11])/채용담당자([R-02]) 공용 캐노니컬
    응답(03-design §4.2). `report_status=queued`일 때는 이 스키마 대신 202
    `{status:"processing"}`을 반환한다(인터뷰 라우터 참고).
    """

    interview_id: UUID
    report_status: str
    overall_score: Decimal | None
    technical_score: int | None
    communication_score: int | None
    cultural_fit_score: int | None
    overall_recommendation: str | None
    # 원안(REQ-F-006/007) 복원분(2026-09-22 사용자 명시 승인) — REPORT_DISCLAIMER와
    # 함께가 아니면 단독 노출 금지(app/models/evaluation_report.py 모듈 docstring 참고).
    pass_fail_recommendation: str | None
    star: StarOut | None
    # star 파싱 성공 시 null, 실패 시에만 채워지는 폴백 텍스트(§3.1/§4.4).
    summary_text: str | None
    details: dict | None
    disclaimer: str = REPORT_DISCLAIMER
