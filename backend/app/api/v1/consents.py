"""REQ-029/REQ-030 (Feature G, unit-14): 생체정보(음성) 동의 등록/철회/이력 조회 +
개인정보(생체정보) 삭제 요청 접수/조회 (03-system-design.md §3, §4.2, §6.2, DEC-023/024).

이 라우터가 만드는 `CONSENTS` 레코드는 unit-2/unit-4가 이미 `/interviews/{id}/start`,
`/interviews/{id}/turns`에서 실시간 재조회로 소비하고 있다(`app/models/consent.py`,
unit-2-note.md §2-2). 이번 유닛은 그 레코드를 생성/철회/조회하는 REST API 표면만
추가하며, `interviews.py`(면접 세션/턴 상태머신, unit-2~4 소유)는 건드리지 않는다.

실제 하드 삭제(파기) 배치("delete_requested_data" Celery beat 잡, 03-design §6.2)는
REQ-033을 담당하는 unit-15의 책임이다 — 이 라우터는 `DELETION_REQUESTS`를
`pending` 상태로 접수하는 것까지만 다룬다(unit-14-note.md §2 참고).
"""
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.errors import AppError
from app.db.session import get_db
from app.models.consent import Consent
from app.models.deletion_request import DeletionRequest, DeletionRequestStatus, DeletionTarget
from app.models.interview import Interview
from app.models.user import User
from app.schemas.consent import (
    ConsentCreate,
    ConsentOut,
    DataExportOut,
    DeletionRequestOut,
    InterviewSummaryExport,
)

router = APIRouter(tags=["consents"])


@router.post("/consents", response_model=ConsentOut, status_code=status.HTTP_201_CREATED)
def create_consent(
    payload: ConsentCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Consent:
    """사전고지(`ai_interview_notice`) 또는 생체정보(`biometric_voice`) 동의 등록
    (03-design §4.2 `POST /consents`). 동일 종류 동의를 다시 등록해도 거부하지 않고
    새 레코드를 만든다 — `CONSENTS`는 각 동의 "이벤트"를 남기는 이력 테이블이고
    (ERD상 (user_id, consent_type) 유니크 제약 없음), 활성 동의 여부 판정은 항상
    "철회되지 않은 레코드가 존재하는가"로 이루어지므로(§6.2, `_has_active_consent`류
    로직) 중복 등록이 정합성을 깨지 않는다.
    """
    consent = Consent(
        user_id=current_user.id,
        consent_type=payload.consent_type,
        granted_at=datetime.now(UTC),
        ip_address=request.client.host if request.client else None,
    )
    db.add(consent)
    db.commit()
    db.refresh(consent)
    return consent


@router.post("/consents/{consent_id}/revoke", response_model=ConsentOut, status_code=status.HTTP_200_OK)
def revoke_consent(
    consent_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Consent:
    """동의 철회 (03-design §4.2 `POST /consents/{id}/revoke`, REQ-030).

    실제 강제(차단) 동작은 이 엔드포인트가 아니라 `CONSENTS.revoked_at`을 소비하는
    쪽(unit-2 `/start`, unit-4 `/turns`)의 실시간 재조회에서 일어난다(DEC-023) — 이
    엔드포인트는 그 재조회가 참조할 `revoked_at`을 기록하는 것이 유일한 책임이다.
    """
    consent = db.get(Consent, consent_id)
    if consent is None:
        raise AppError(404, "NOT_FOUND", "Not Found", "동의 기록을 찾을 수 없습니다.")
    if consent.user_id != current_user.id:
        raise AppError(403, "AUTH_FORBIDDEN", "Forbidden", "본인의 동의 기록만 철회할 수 있습니다.")
    if consent.revoked_at is not None:
        raise AppError(409, "VALIDATION_ERROR", "Conflict", "이미 철회된 동의입니다.")

    consent.revoked_at = datetime.now(UTC)
    db.commit()
    db.refresh(consent)
    return consent


@router.get("/users/me/consents", response_model=list[ConsentOut], status_code=status.HTTP_200_OK)
def list_my_consents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Consent]:
    """(03-design v2 §4.2 신규, DEC-024 갭1) 내 동의 이력 조회 — [C-13] 마이페이지가
    클라이언트 로컬 저장값 대신 서버 상태를 표시하도록 함."""
    stmt = (
        select(Consent)
        .where(Consent.user_id == current_user.id)
        .order_by(Consent.granted_at.desc())
    )
    return list(db.scalars(stmt).all())


@router.delete("/users/me/biometric-data", response_model=DeletionRequestOut, status_code=status.HTTP_202_ACCEPTED)
def request_biometric_data_deletion(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DeletionRequest:
    """생체정보(음성) 즉시 삭제 요청 (03-design §4.2 `DELETE /users/me/biometric-data`,
    REQ-030/033) → `DELETION_REQUESTS`를 `target=biometric_only`, `status=pending`으로
    생성한다. 실제 파기(하드 삭제)는 REQ-033(unit-15) 소관 배치 잡의 책임이라 이
    엔드포인트는 요청 접수만 수행한다(unit-14-note.md §2).
    """
    deletion_request = DeletionRequest(
        user_id=current_user.id,
        target=DeletionTarget.biometric_only,
        status=DeletionRequestStatus.pending,
    )
    db.add(deletion_request)
    db.commit()
    db.refresh(deletion_request)
    return deletion_request


@router.get("/users/me/deletion-requests", response_model=list[DeletionRequestOut], status_code=status.HTTP_200_OK)
def list_my_deletion_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DeletionRequest]:
    """(03-design v2 §4.2 신규, DEC-024 갭2) 내 삭제 요청 처리 상태 조회."""
    stmt = (
        select(DeletionRequest)
        .where(DeletionRequest.user_id == current_user.id)
        .order_by(DeletionRequest.requested_at.desc())
    )
    return list(db.scalars(stmt).all())


@router.get("/users/me/data-export", response_model=DataExportOut, status_code=status.HTTP_200_OK)
def export_my_data(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DataExportOut:
    """unit-33(GDPR 제20조/CCPA 열람권 기술 대응, 2026-09-22 사용자 승인):
    계정에 연결된 개인정보를 한 곳에서 조회 가능하게 한다. 대화 원문은
    포함하지 않는다(`schemas/consent.py`의 `DataExportOut` docstring 참고).
    """
    consents = list(
        db.scalars(select(Consent).where(Consent.user_id == current_user.id).order_by(Consent.granted_at.desc()))
    )
    deletion_requests = list(
        db.scalars(
            select(DeletionRequest)
            .where(DeletionRequest.user_id == current_user.id)
            .order_by(DeletionRequest.requested_at.desc())
        )
    )
    interviews = list(
        db.scalars(
            select(Interview).where(Interview.candidate_id == current_user.id).order_by(Interview.created_at.desc())
        )
    )

    return DataExportOut(
        exported_at=datetime.now(UTC),
        user_id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        account_created_at=current_user.created_at,
        consents=[ConsentOut.model_validate(c) for c in consents],
        deletion_requests=[DeletionRequestOut.model_validate(d) for d in deletion_requests],
        interviews=[
            InterviewSummaryExport(
                interview_id=iv.id, status=iv.status.value, started_at=iv.started_at,
                ended_at=iv.ended_at, overall_score=iv.overall_score,
            )
            for iv in interviews
        ],
    )
