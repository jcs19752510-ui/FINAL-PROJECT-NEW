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


class VoicePreviewResponse(BaseModel):
    """POST /interviews/{id}/turns/preview 응답 (unit-36, STT 실시간 스트리밍 미리보기).

    DB에 아무것도 저장하지 않는 순수 조회성 응답이라 `TranscriptOut`과 달리
    id/turn_index 등이 없다 — 화면에 "지금까지 인식된 텍스트"를 보여주는
    용도로만 쓰인다.
    """

    text: str


class TranscriptOut(BaseModel):
    id: UUID
    interview_id: UUID
    question_id: UUID | None
    turn_index: int
    speaker: str
    input_mode: str
    content_text: str
    audio_ref: str | None
    # unit-24(원안 REQ-018/019 축소판, 2026-09-22 사용자 승인) — speaker=user·
    # input_mode=voice가 아니면 항상 null(분석 실패 시에도 null, 그레이스풀 디그레이드).
    prosody: dict | None = Field(default=None, validation_alias="prosody_json")
    created_at: datetime

    model_config = {"from_attributes": True}


class TurnAcceptedResponse(BaseModel):
    """03-system-design.md §4.2: `POST /interviews/{id}/turns` → `202 {job_id}`."""

    job_id: str
