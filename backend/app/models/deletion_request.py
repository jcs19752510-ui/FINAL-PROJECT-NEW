"""03-system-design.md §3.1 ERD의 DELETION_REQUESTS 테이블 (REQ-030, Feature G, unit-14).

`status`는 ERD 원문 그대로 `pending|completed` 2값만 가진다(오케스트레이터 지시문이
언급한 "pending/processing/completed" 3단계는 03-design ERD에 없는 상태값이라 임의로
추가하지 않았다 — 설계서 원문 우선). 실제 하드 삭제(파기) 배치("delete_requested_data"
Celery beat 잡, 03-design §6.2)는 REQ-033을 담당하는 unit-15의 책임이며 이번 유닛은
요청 접수와 `pending` 상태 유지까지만 다룬다(unit-14-note.md §2 참고). 그 배치가
실제로 파기를 완료하면 `status`를 `completed`로, `completed_at`을 채우는 방식으로
연동될 것을 전제로 컬럼을 마련해 둔다.
"""
import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class DeletionTarget(StrEnum):
    biometric_only = "biometric_only"
    full_account = "full_account"


class DeletionRequestStatus(StrEnum):
    pending = "pending"
    completed = "completed"


class DeletionRequest(Base):
    __tablename__ = "deletion_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    target: Mapped[DeletionTarget] = mapped_column(Enum(DeletionTarget, name="deletion_target"), nullable=False)
    status: Mapped[DeletionRequestStatus] = mapped_column(
        Enum(DeletionRequestStatus, name="deletion_request_status"),
        nullable=False,
        default=DeletionRequestStatus.pending,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
