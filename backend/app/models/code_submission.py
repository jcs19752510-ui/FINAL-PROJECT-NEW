"""03-system-design.md §3.1 ERD의 CODE_SUBMISSIONS 테이블 (REQ-008, Feature D, unit-9).

`language`는 ERD상 자유 문자열(`string language`)이나, 04-ux-design.md [C-07]이
"언어 선택 드롭다운" UI를 명시하고 있어 API 경계(스키마)에서 화이트리스트로 제한한다
(게이트2 "시스템 경계 입력 검증" — 임의 문자열 저장 방지). 화이트리스트 자체는
`app/schemas/code_submission.py`에 둔다(ERD/모델은 설계서 원문 그대로 `string` 컬럼
유지, 검증 로직만 API 계층 책임).

`content`는 REQ-036/03-design §6.3 새니타이즈 대상으로 지정되어 있으나, 그 새니타이즈는
"렌더링 시점"(추후 recruiter 대시보드/리포트가 이 값을 화면에 보여줄 때) 방어이며 이번
유닛은 그 렌더링 화면을 만들지 않는다(오케스트레이터 지시 범위 — 에디터 UI+저장 API만).
따라서 저장 시점에는 원문 그대로 보관하고, 향후 이 값을 HTML로 렌더링하는 화면을 만드는
유닛이 §6.3 화이트리스트 새니타이즈를 반드시 적용해야 한다는 점을 unit-9-note.md에 남긴다.

REQ-008은 "실행 없음"(DEC-008, Out-of-Scope)이 확정되어 있으므로 이 테이블/모델은
순수 저장소이며 코드 실행과 관련된 어떤 필드/로직도 갖지 않는다.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CodeSubmission(Base):
    __tablename__ = "code_submissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interviews.id"), nullable=False, index=True
    )
    language: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
