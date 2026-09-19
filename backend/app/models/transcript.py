"""03-system-design.md §3.1 ERD의 TRANSCRIPTS 테이블 (REQ-003, Feature C).

이번 유닛(unit-4)은 **텍스트 턴만** 다룬다(오케스트레이터 지시 범위). `speaker`/
`input_mode` enum 자체는 ERD 전체 값(ai/user, text/voice)을 그대로 만들어두되,
실제로 이 유닛이 기록하는 값은 `speaker=user`(지원자 텍스트 답변)뿐이다.
`speaker=ai` 행은 `opening_question`/일반 턴 LLM 응답이 실제로 처리된 뒤(unit-7)
AI Worker가 기록하며, 이번 유닛은 그 워커를 만들지 않는다(job_queue.py 스텁 경계
참고).

`question_id`는 ERD상 QUESTIONS 테이블(RAG 질문은행, unit-7 책임)을 가리키는 FK이나
QUESTIONS 테이블이 아직 존재하지 않는다. unit-2의 `rubric_template_id` 선례를 그대로
따라 FK 제약 없이 nullable 컬럼만 만든다 — unit-7이 QUESTIONS를 생성할 때 별도
revision으로 FK 제약을 추가해야 한다.
"""
import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Speaker(StrEnum):
    ai = "ai"
    user = "user"


class InputMode(StrEnum):
    text = "text"
    voice = "voice"


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interviews.id"), nullable=False, index=True
    )
    # FK 제약 없음(위 모듈 docstring 참고) — unit-7이 QUESTIONS 생성 시 추가.
    question_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[Speaker] = mapped_column(Enum(Speaker, name="transcript_speaker"), nullable=False)
    input_mode: Mapped[InputMode] = mapped_column(Enum(InputMode, name="transcript_input_mode"), nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    audio_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
