"""Feature J(REQ-040~044, 2026-09-29 사용자 요청) — 채용 지원(이력서) 심사.

`이력서제출_합격통보_신규기능_요청프롬프트.md` §4-3 데이터 모델 제안을 그대로
구현한다. `candidate_id`는 계정 공유 결정(같은 문서 §2 결정#2)에 따라 기존
`users` 테이블을 그대로 참조 — 이력서 제출자 전용 신규 role/테이블을 따로
만들지 않는다.

**하나의 계정 = 하나의 활성 이력서 지원서** (`candidate_id` UNIQUE). 재제출
정책: `POST /resumes`를 다시 호출하면 기존 행을 덮어쓰며 상태를 `pending`으로
되돌리고 이전 판단(`decision_note`/`interview_schedule_note`/`reviewed_*`/
`notified_at`)을 초기화한다 — "다시 제출 = 심사를 처음부터 다시 요청"으로
해석한다(구현 세부값, 이 문서가 사용자에게 별도로 확인받지 않은 항목이라
비가역성 낮음, 추후 피드백에 따라 정책 조정 가능).

**파일 저장**: 원문은 `backend/var/resumes/`에 디스크 저장(기존 Piper 음성
파일이 `backend/var/`를 쓰는 관례를 그대로 따름), DB에는 경로만 보관한다.
파일 자체의 저장 시 암호화(AES-256-GCM, `field_encryption.py`)는 이번
구현에서는 적용하지 않았다 — PDF 등 바이너리를 컬럼 암호화 인프라
(`EncryptedString`/`EncryptedText`는 `str` 텍스트 전용)에 그대로 태우려면
base64 인코딩 등 추가 설계가 필요해 임의로 확장하지 않았다. 접근 통제
(recruiter role만 다운로드 가능, `recruiter_resumes.py` 참고)로 최소 보호는
하되, **파일 자체의 저장 암호화는 후속 보안 검토 대상으로 명시적으로 남겨둔다**
(요청 프롬프트 §4-3과 동일한 취지 — 임의로 안전하다고 주장하지 않음).
"""
import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ResumeApplicationStatus(StrEnum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"


class ResumeApplication(Base):
    __tablename__ = "resume_applications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True, index=True
    )
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ResumeApplicationStatus] = mapped_column(
        Enum(ResumeApplicationStatus, name="resume_application_status"),
        nullable=False,
        server_default=ResumeApplicationStatus.pending.value,
    )
    # 합격 시 안내 문구 또는 불합격 사유 — 관리자가 자유 텍스트로 입력.
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 프롬프트 §2 결정#4: 강제력 없는 안내용 정보일 뿐이다. 이 값이 있어도
    # 모의면접 시작 가능 여부에는 어떤 영향도 주지 않는다(코드 어디에서도
    # 이 필드로 게이트하지 않는다 — `frontend/components/CandidateHome.tsx`의
    # 게이트 로직은 `status`만 본다).
    interview_schedule_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 관리자가 "MCP로 실제 발송 완료"를 수동으로 표시한 시각(프롬프트 §2 결정#3 —
    # 백엔드는 이메일을 자동 발송하지 않는다, 감사 추적용 타임스탬프만 남긴다).
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
