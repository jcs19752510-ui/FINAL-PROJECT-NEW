"""라이브 코딩 문제 — 원본 REQ-F-004 정답 판정의 근거(입출력 테스트케이스). 2026-10-12.

표준입력으로 입력을 받아 표준출력으로 답을 내는 방식이라 Python/JavaScript 모두 같은 문제를 쓴다.
`tests_json`: [{"input": str, "expected": str, "hidden": bool}]. hidden 테스트는 API 로 노출하지 않는다.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CodingProblem(Base):
    __tablename__ = "coding_problems"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False)
    tests_json: Mapped[list] = mapped_column(JSONB, nullable=False)
    perf_json: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
