from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TurnCreate(BaseModel):
    """POST /interviews/{id}/turns 텍스트 전용 요청 바디 (03-system-design.md §4.2).

    설계서 예시는 텍스트 턴을 `{"text":"..."}`로 표기한다. 최대 길이(4000자)는
    설계서에 명시되지 않은 구현 세부값 — 시스템 경계 입력 검증(게이트2 체크리스트)을
    위해 이 유닛에서 보수적으로 확정했다(비가역성 낮음, 이후 단위가 조정 가능).
    """

    text: str = Field(min_length=1, max_length=4000)


class TranscriptOut(BaseModel):
    id: UUID
    interview_id: UUID
    question_id: UUID | None
    turn_index: int
    speaker: str
    input_mode: str
    content_text: str
    audio_ref: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TurnAcceptedResponse(BaseModel):
    """03-system-design.md §4.2: `POST /interviews/{id}/turns` → `202 {job_id}`."""

    job_id: str
