from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.models.consent import ConsentType, LawfulBasis
from app.models.deletion_request import DeletionRequestStatus, DeletionTarget


class ConsentCreate(BaseModel):
    consent_type: ConsentType


class ConsentOut(BaseModel):
    id: UUID
    consent_type: ConsentType
    granted_at: datetime
    revoked_at: datetime | None
    # unit-34(GDPR 제6조 적법근거, 2026-09-23 사용자 승인) — 이 서비스의 모든
    # 동의는 명시적 opt-in이라 항상 "consent"다(app/models/consent.py 참고).
    lawful_basis: LawfulBasis

    model_config = {"from_attributes": True}


class DeletionRequestOut(BaseModel):
    id: UUID
    target: DeletionTarget
    status: DeletionRequestStatus
    requested_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


# unit-33(원안 REQ-N-003 확장, GDPR 제20조 "데이터 이동권"/CCPA "열람권" 기술적
# 대응, 2026-09-22 사용자 승인): 코드로 "법적 준수"를 주장하지 않는다 — 이건
# GDPR/CCPA가 공통으로 요구하는 구체적 기술 요건(보유 데이터를 기계가 읽을 수
# 있는 형태로 제공) 중 이 세션이 실제로 구현·검증 가능한 조각일 뿐이다. 실제
# 법적 준수 여부는 `docs/harness/units/unit-33-note.md`의 갭 분석과 별도 법무
# 검토가 필요하다.
class InterviewSummaryExport(BaseModel):
    interview_id: UUID
    status: str
    started_at: datetime | None
    ended_at: datetime | None
    overall_score: Decimal | None


class DataExportOut(BaseModel):
    """`GET /users/me/data-export` 응답 — 계정에 연결된 개인정보를 한 번에
    조회 가능한 형태로 제공한다. 대화 원문(TRANSCRIPTS.content_text)은
    포함하지 않는다 — 그 컬럼은 별도로 발견된 인코딩 손상 결함(unit-24) 조사가
    끝나기 전까지 건드리지 않기로 한 결정과 동일한 이유로 이번 범위에서 제외
    했다(unit-33-note.md §2).
    """

    exported_at: datetime
    user_id: UUID
    email: str
    name: str
    account_created_at: datetime
    consents: list[ConsentOut]
    deletion_requests: list[DeletionRequestOut]
    interviews: list[InterviewSummaryExport]
