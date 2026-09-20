"""03-system-design.md §3.1 ERD의 WHITEBOARD_SNAPSHOTS 테이블 (REQ-017, Feature H, unit-17).

DEC-008: AI가 화이트보드를 시각적으로 분석하는 기능은 Out-of-Scope(REQ-021)다. 이
테이블/모델은 순수 드로잉 캔버스의 스냅샷(JSON)을 저장/조회하는 용도로만 쓰이며,
분석 관련 컬럼/로직은 추가하지 않는다.

ERD(03-design §3.1)는 `id`/`interview_id`/`canvas_json`/`created_at` 4개 컬럼만
정의한다. `PUT /interviews/{id}/whiteboard`가 "저장"인데 테이블에 UPDATE 대상 단일
행이 없다 — 03-design은 이 테이블을 스냅샷 이력 테이블로 설계했으므로(예: `AUDIT_LOGS`,
`CONSENTS`와 동일하게 "매 시점의 상태를 새 행으로 남기는" 패턴), `PUT`을 "새 스냅샷
행 추가 후 최신 행을 정답으로 취급"으로 구현한다(unit-17-note.md §2 참고, 두 가지
해석이 갈리지 않는 additive-only 결정이라 규칙A 질문 대상이 아님).
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class WhiteboardSnapshot(Base):
    __tablename__ = "whiteboard_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interviews.id"), nullable=False, index=True
    )
    canvas_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
