"""03-system-design.md §3.1 ERD의 QUESTIONS 테이블 (REQ-007, Feature C, RAG 질문은행).

pgvector 확장(`vector` 컬럼 타입)으로 임베딩을 저장하고, `app/services/rag_engine.py`가
코사인 유사도 + MMR로 현재 대화 맥락과 유사한 질문 후보를 검색한다. 임베딩 차원(384)은
선정된 임베딩 모델(sentence-transformers `paraphrase-multilingual-MiniLM-L12-v2`,
다국어 지원, 03-system-design.md §2.4)의 출력 차원에 고정된다 — 모델을 교체하면 이
컬럼 차원과 기존 저장된 임베딩을 전부 재생성해야 한다(비가역성 Medium).

`TRANSCRIPTS.question_id`는 unit-4가 FK 제약 없이 nullable 컬럼만 만들어뒀다
(app/models/transcript.py 모듈 docstring 참고) — 이 유닛에서 QUESTIONS가 실제로
생기므로 마이그레이션에서 FK 제약을 추가한다.
"""
import uuid
from datetime import datetime
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Enum, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

# sentence-transformers paraphrase-multilingual-MiniLM-L12-v2 출력 차원(실측 확인,
# unit-7-note.md §6 참고). 이 값을 바꾸면 반드시 새 Alembic revision + 재임베딩이 필요.
EMBEDDING_DIM = 384


class QuestionCategory(StrEnum):
    technical = "technical"
    behavioral = "behavioral"
    # opening_question job(§4.3 DEC-024 갭8)이 세션 시작 직후 고르는 전용 카테고리.
    opening = "opening"


class QuestionSource(StrEnum):
    bank = "bank"
    generated = "generated"


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[QuestionCategory] = mapped_column(
        Enum(QuestionCategory, name="question_category"), nullable=False, index=True
    )
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False)
    rubric_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    source: Mapped[QuestionSource] = mapped_column(
        Enum(QuestionSource, name="question_source"), nullable=False, default=QuestionSource.bank
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
