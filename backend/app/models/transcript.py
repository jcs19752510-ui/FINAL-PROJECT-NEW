"""03-system-design.md §3.1 ERD의 TRANSCRIPTS 테이블 (REQ-003, Feature C).

이번 유닛(unit-4)은 **텍스트 턴만** 다룬다(오케스트레이터 지시 범위). `speaker`/
`input_mode` enum 자체는 ERD 전체 값(ai/user, text/voice)을 그대로 만들어두되,
실제로 이 유닛이 기록하는 값은 `speaker=user`(지원자 텍스트 답변)뿐이다.
`speaker=ai` 행은 `opening_question`/일반 턴 LLM 응답이 실제로 처리된 뒤(unit-7)
AI Worker가 기록하며, 이번 유닛은 그 워커를 만들지 않는다(job_queue.py 스텁 경계
참고).

`question_id`는 ERD상 QUESTIONS 테이블(RAG 질문은행)을 가리키는 FK다. unit-4는
QUESTIONS가 아직 없어 FK 제약 없이 nullable 컬럼만 만들었으나(unit-2의
`rubric_template_id` 선례), unit-7이 QUESTIONS를 생성하면서 별도 revision으로 FK
제약을 추가했다(`app/models/question.py`, RAG로 선정된 질문은행 항목을 가리킴).
"""
import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.question import Question  # noqa: F401  # FK 대상 테이블 메타데이터 등록 필요(아래 참고)

# SQLAlchemy는 `ForeignKey("questions.id")`를 해석할 때 `questions` 테이블이 이미
# `Base.metadata`에 등록되어 있어야 한다. alembic/env.py는 모든 모델을 명시적으로
# import해 이 문제가 없지만, FastAPI 앱(app/main.py) 쪽은 `app/models/question.py`를
# 아무도 import하지 않으면 `questions` 테이블이 메타데이터에 없어 flush 시점에
# `NoReferencedTableError`가 발생한다(unit-7 실측으로 확인) — 위 import로 이 순서
# 문제를 해결한다.


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
    # unit-7: QUESTIONS 생성과 함께 FK 제약 추가(위 모듈 docstring 참고).
    question_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id"), nullable=True
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[Speaker] = mapped_column(Enum(Speaker, name="transcript_speaker"), nullable=False)
    input_mode: Mapped[InputMode] = mapped_column(Enum(InputMode, name="transcript_input_mode"), nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    audio_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
