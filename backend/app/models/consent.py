"""03-system-design.md §3.1 ERD의 CONSENTS 테이블 (최소 구현).

unit-2(REQ-002, `/interviews/{id}/start`의 DEC-023 게이트: `ai_interview_notice`
동의 검사)가 구조적으로 필요로 하는 최소 스키마만 여기서 만든다. `POST /consents`,
`GET /users/me/consents`, 철회(`/consents/{id}/revoke`) 등 동의 관리 REST API 전체는
REQ-029/030/032를 담당하는 unit-14/unit-15의 책임이며 이번 유닛 범위가 아니다
(unit-2-note.md "설계서 대비 편차" 참고).

**ip_address 암호화(unit-25, 원안 REQ-N-003 축소판, 2026-09-22 사용자 승인)**:
`EncryptedString`(AES-256-GCM, `app/services/field_encryption.py`)으로 저장 시
투명 암호화한다. 이 컬럼을 선택한 이유: (1) `ConsentOut` 스키마가 애초에 이 값을
API로 반환하지 않아(내부 감사 로그 전용) 암호화해도 어떤 응답 경로도 바꿀 필요가
없음, (2) LLM/리포트 생성 등 텍스트 처리 파이프라인과 전혀 얽히지 않아 별도로
발견된 `TRANSCRIPTS.content_text` 인코딩 손상 결함과 완전히 무관 — 그 결함이
해결되기 전에도 안전하게 암호화 가능한 필드다. `TRANSCRIPTS.content_text` 등
핵심 대화 콘텐츠 컬럼은 그 결함 조사가 선행되어야 해 이번 범위에서 의도적으로
제외했다(`unit-25-note.md` 참고). 저장 폭은 원문(IPv6 최대 45자) 대비 암호화
오버헤드(논스+태그+base64 팽창)를 감안해 64→255자로 넓혔다(마이그레이션 동반).
"""
import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.services.field_encryption import EncryptedString


class ConsentType(StrEnum):
    biometric_voice = "biometric_voice"
    ai_interview_notice = "ai_interview_notice"


class LawfulBasis(StrEnum):
    """GDPR 제6조가 정의하는 6가지 적법 근거(unit-34, 2026-09-23 사용자 승인).

    이 프로젝트의 현재 동의 흐름은 전부 명시적 opt-in이라 실질적으로는 항상
    `consent`다 — 그런데도 이 필드를 추가한 이유는 (1) GDPR 준수 여부를 실제로
    판단할 법무 검토 전까지 "지금은 전부 consent 기반"이라는 사실 자체를 DB에
    명시적으로 남겨 감사 가능하게 하고, (2) 향후 다른 근거(예: 계약 이행)가
    필요한 동의 유형이 추가될 때 스키마 변경 없이 확장 가능하게 하기 위함이다.
    """

    consent = "consent"
    contract = "contract"
    legal_obligation = "legal_obligation"
    vital_interests = "vital_interests"
    public_task = "public_task"
    legitimate_interests = "legitimate_interests"


class Consent(Base):
    __tablename__ = "consents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    consent_type: Mapped[ConsentType] = mapped_column(Enum(ConsentType, name="consent_type"), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(EncryptedString(255), nullable=True)
    # unit-34(GDPR 제6조 적법근거 기록, 2026-09-23 사용자 승인): 이 프로젝트의
    # 모든 동의는 명시적 opt-in이라 기본값을 'consent'로 고정한다(위 클래스
    # docstring 참고). NOT NULL + server_default라 기존 행도 일괄 채워진다.
    lawful_basis: Mapped[LawfulBasis] = mapped_column(
        Enum(LawfulBasis, name="lawful_basis"),
        nullable=False,
        server_default=LawfulBasis.consent.value,
    )
