"""Feature J(REQ-042/043/044, 2026-09-29 사용자 요청) — 채용담당자(recruiter)용
이력서 검토/판단/통보 초안 (`이력서제출_합격통보_신규기능_요청프롬프트.md`
§4-2/§4-4).

기존 `recruiter.py`(리포트 열람)와 파일을 분리해 additive하게 확장한다 —
`recruiter.py`의 `_require_recruiter` 접근 정책(§6.1, 단일조직 전체열람)을
이력서에도 그대로 적용한다(요청 프롬프트 §4-2가 명시한 대로, 구현 착수 시
재확인 없이 기존 정책 재사용 — recruiter 전원이 모든 이력서를 열람 가능).
"""
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.recruiter import _require_recruiter
from app.core.errors import AppError
from app.db.session import get_db
from app.models.resume_application import ResumeApplication, ResumeApplicationStatus
from app.models.user import User
from app.schemas.resume import (
    NotificationDraftOut,
    RecruiterResumeDetailOut,
    RecruiterResumeListItemOut,
    ResumeDecisionIn,
)

router = APIRouter(prefix="/recruiter", tags=["recruiter-resumes"])

# 요청 프롬프트 §4-1 "합격 통보를 받은 지원자는 기존 모의면접 URL에 로그인"을
# 위한 안내 문구용 링크. 실제 배포 도메인은 아직 없어(로컬 개발 단계) 상대
# 경로로만 안내한다 — 운영 배포 시 절대 URL로 교체 필요(11단계 인수인계 대상).
_MOCK_INTERVIEW_LOGIN_HINT = "모의면접 사이트에 이 계정(이메일/비밀번호)으로 로그인해주세요."


def _get_application_or_404(db: Session, application_id: UUID) -> tuple[ResumeApplication, User]:
    row = db.execute(
        select(ResumeApplication, User)
        .join(User, ResumeApplication.candidate_id == User.id)
        .where(ResumeApplication.id == application_id)
    ).first()
    if row is None:
        raise AppError(404, "NOT_FOUND", "Not Found", "이력서 지원서를 찾을 수 없습니다.")
    return row


@router.get("/resumes", response_model=list[RecruiterResumeListItemOut])
def list_resumes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RecruiterResumeListItemOut]:
    _require_recruiter(current_user)
    rows = db.execute(
        select(ResumeApplication, User)
        .join(User, ResumeApplication.candidate_id == User.id)
        .order_by(ResumeApplication.submitted_at.desc())
    ).all()
    return [
        RecruiterResumeListItemOut(
            id=app_.id,
            candidate_id=candidate.id,
            candidate_name=candidate.name,
            candidate_email=candidate.email,
            status=app_.status,
            original_filename=app_.original_filename,
            submitted_at=app_.submitted_at,
            reviewed_at=app_.reviewed_at,
            notified_at=app_.notified_at,
        )
        for app_, candidate in rows
    ]


@router.get("/resumes/{application_id}", response_model=RecruiterResumeDetailOut)
def get_resume_detail(
    application_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecruiterResumeDetailOut:
    _require_recruiter(current_user)
    app_, candidate = _get_application_or_404(db, application_id)
    return RecruiterResumeDetailOut(
        id=app_.id,
        candidate_id=candidate.id,
        candidate_name=candidate.name,
        candidate_email=candidate.email,
        status=app_.status,
        original_filename=app_.original_filename,
        submitted_at=app_.submitted_at,
        reviewed_at=app_.reviewed_at,
        notified_at=app_.notified_at,
        content_type=app_.content_type,
        file_size_bytes=app_.file_size_bytes,
        decision_note=app_.decision_note,
        interview_schedule_note=app_.interview_schedule_note,
    )


@router.get("/resumes/{application_id}/file")
def download_resume_file(
    application_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """원문 PDF 다운로드 — recruiter 전용(모델 docstring 참고, 파일 자체
    저장 암호화는 이번 범위 밖이라 접근 통제가 유일한 보호막이다)."""
    _require_recruiter(current_user)
    app_, _candidate = _get_application_or_404(db, application_id)
    return FileResponse(
        app_.file_path,
        media_type=app_.content_type,
        filename=app_.original_filename,
    )


@router.patch("/resumes/{application_id}/decision", response_model=RecruiterResumeDetailOut)
def decide_resume(
    application_id: UUID,
    payload: ResumeDecisionIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecruiterResumeDetailOut:
    """서류 합격/불합격 판단 저장 (요청 프롬프트 §4-2). `interview_schedule_note`는
    안내용일 뿐 어떤 게이트에도 쓰이지 않는다(§2 결정#4)."""
    _require_recruiter(current_user)
    app_, candidate = _get_application_or_404(db, application_id)

    if payload.status not in (ResumeApplicationStatus.accepted, ResumeApplicationStatus.rejected):
        raise AppError(422, "VALIDATION_ERROR", "Validation Error", "판단 결과는 accepted 또는 rejected여야 합니다.")

    app_.status = payload.status
    app_.decision_note = payload.decision_note
    app_.interview_schedule_note = payload.interview_schedule_note
    app_.reviewed_by = current_user.id
    app_.reviewed_at = datetime.now(UTC)
    db.commit()
    db.refresh(app_)

    return RecruiterResumeDetailOut(
        id=app_.id,
        candidate_id=candidate.id,
        candidate_name=candidate.name,
        candidate_email=candidate.email,
        status=app_.status,
        original_filename=app_.original_filename,
        submitted_at=app_.submitted_at,
        reviewed_at=app_.reviewed_at,
        notified_at=app_.notified_at,
        content_type=app_.content_type,
        file_size_bytes=app_.file_size_bytes,
        decision_note=app_.decision_note,
        interview_schedule_note=app_.interview_schedule_note,
    )


@router.get("/resumes/{application_id}/notification-draft", response_model=NotificationDraftOut)
def get_notification_draft(
    application_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationDraftOut:
    """반자동 통보(요청 프롬프트 §2 결정#3) — 백엔드는 발송하지 않고, 관리자가
    그대로 복사해 본인의 Claude+MCP 메일 도구로 보낼 수 있는 제목/본문만
    생성한다."""
    _require_recruiter(current_user)
    app_, candidate = _get_application_or_404(db, application_id)

    if app_.status == ResumeApplicationStatus.pending:
        raise AppError(409, "VALIDATION_ERROR", "Conflict", "아직 판단(합격/불합격)이 저장되지 않았습니다.")

    if app_.status == ResumeApplicationStatus.accepted:
        subject = "[채용 안내] 서류 전형 합격 및 모의면접 안내"
        lines = [
            f"{candidate.name}님, 안녕하세요.",
            "",
            "서류 전형에 합격하셨습니다. 축하드립니다.",
        ]
        if app_.interview_schedule_note:
            lines += ["", f"면접 일정 안내: {app_.interview_schedule_note}"]
        if app_.decision_note:
            lines += ["", app_.decision_note]
        lines += ["", _MOCK_INTERVIEW_LOGIN_HINT, "로그인 후 합격 여부를 다시 확인하실 수 있으며, 이어서 모의면접을 진행해주세요."]
    else:
        subject = "[채용 안내] 서류 전형 결과 안내"
        lines = [
            f"{candidate.name}님, 안녕하세요.",
            "",
            "아쉽게도 이번 서류 전형에서는 합격하지 못하셨습니다.",
        ]
        if app_.decision_note:
            lines += ["", app_.decision_note]
        lines += ["", "지원해주셔서 감사합니다."]

    return NotificationDraftOut(to_email=candidate.email, subject=subject, body="\n".join(lines))


@router.post("/resumes/{application_id}/mark-notified", response_model=RecruiterResumeDetailOut)
def mark_resume_notified(
    application_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecruiterResumeDetailOut:
    """관리자가 MCP 메일 도구로 실제 발송을 마친 뒤 수동으로 누르는 "통보 완료"
    체크(요청 프롬프트 §4-2). 감사 추적용 — 몇 번을 눌러도 최신 시각으로만
    갱신되는 멱등 동작이다(재발송 시나리오를 막지 않기 위한 구현 세부값)."""
    _require_recruiter(current_user)
    app_, candidate = _get_application_or_404(db, application_id)

    if app_.status == ResumeApplicationStatus.pending:
        raise AppError(409, "VALIDATION_ERROR", "Conflict", "아직 판단(합격/불합격)이 저장되지 않았습니다.")

    app_.notified_at = datetime.now(UTC)
    db.commit()
    db.refresh(app_)

    return RecruiterResumeDetailOut(
        id=app_.id,
        candidate_id=candidate.id,
        candidate_name=candidate.name,
        candidate_email=candidate.email,
        status=app_.status,
        original_filename=app_.original_filename,
        submitted_at=app_.submitted_at,
        reviewed_at=app_.reviewed_at,
        notified_at=app_.notified_at,
        content_type=app_.content_type,
        file_size_bytes=app_.file_size_bytes,
        decision_note=app_.decision_note,
        interview_schedule_note=app_.interview_schedule_note,
    )
