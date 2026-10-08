"""면접 완료 건의 최종 합격/불합격 처리 + 안내 메일 자동 발송 (2026-10-07 사용자 요청).

이력서 합격 처리(`recruiter_resumes.py::decide_resume`)와 같은 방식이다 — 판단을
저장한 직후 Gmail SMTP로 지원자에게 안내 메일을 자동 발송하고, 발송이 실제로
성공했을 때만 `final_notified_at`을 채운다(DEC-116 패턴 그대로. 배포된 백엔드는
MCP 메일 도구를 직접 호출할 수 없어 MCP가 아니라 SMTP를 쓴다).

이력서 처리와 다른 점(2026-10-07 사용자 결정 4건):
- 메일 문구·드롭다운 항목은 최종 결과 전용이다(서류 전형 문구 재사용 안 함).
- 면접 일정 안내 입력은 없다.
- 한 번 처리하면 변경할 수 없다(409). 잘못된 재발송 사고를 막기 위함이다.
- `completed` 상태의 면접에만 처리할 수 있다.

기존 `recruiter.py`와 파일을 분리해 additive하게 확장한다(`recruiter_resumes.py`와 같은 방식).
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.recruiter import _require_recruiter
from app.core.errors import AppError
from app.db.session import get_db
from app.models.interview import FinalDecision, Interview, InterviewStatus
from app.models.user import User
from app.schemas.recruiter import FinalDecisionIn, FinalDecisionOut
from app.schemas.resume import NotificationDraftOut
from app.services.email_service import EmailSendError, email_configured, send_notification_email

router = APIRouter(prefix="/recruiter", tags=["recruiter-final-decision"])

_MOCK_INTERVIEW_LOGIN_HINT = "모의면접 사이트에 이 계정(이메일/비밀번호)으로 로그인해 결과를 다시 확인하실 수 있습니다."


def _build_final_notification_content(interview: Interview, candidate: User) -> tuple[str, str]:
    """최종 합격/불합격 안내 메일의 제목·본문. 초안 미리보기와 자동 발송이 이 함수를 공유한다."""
    if interview.final_decision == FinalDecision.accepted:
        subject = "[채용 안내] 최종 합격 안내"
        lines = [
            f"{candidate.name}님, 안녕하세요.",
            "",
            "모든 전형을 마치고 최종 합격하셨습니다. 진심으로 축하드립니다.",
        ]
        if interview.final_decision_note:
            lines += ["", interview.final_decision_note]
        lines += ["", _MOCK_INTERVIEW_LOGIN_HINT]
    else:
        subject = "[채용 안내] 최종 결과 안내"
        lines = [
            f"{candidate.name}님, 안녕하세요.",
            "",
            "아쉽게도 이번 채용에서는 최종 합격하지 못하셨습니다.",
        ]
        if interview.final_decision_note:
            lines += ["", interview.final_decision_note]
        lines += ["", "지원해주셔서 진심으로 감사드립니다."]
    return subject, "\n".join(lines)


def _get_interview_or_404(db: Session, interview_id: UUID, *, for_update: bool = False) -> tuple[Interview, User]:
    stmt = select(Interview, User).join(User, Interview.candidate_id == User.id).where(Interview.id == interview_id)
    if for_update:
        # 동시 요청(더블클릭·두 담당자)이 겹쳐도 "한 번만 처리 + 메일 한 번만 발송"을 보장한다.
        stmt = stmt.with_for_update(of=Interview)
    row = db.execute(stmt).first()
    if row is None:
        raise AppError(404, "NOT_FOUND", "Not Found", "면접 세션을 찾을 수 없습니다.")
    return row[0], row[1]


def _to_out(interview: Interview) -> FinalDecisionOut:
    return FinalDecisionOut(
        interview_id=interview.id,
        final_decision=interview.final_decision.value if interview.final_decision else None,
        final_decision_note=interview.final_decision_note,
        final_decided_at=interview.final_decided_at,
        final_notified_at=interview.final_notified_at,
    )


@router.patch("/reports/{interview_id}/final-decision", response_model=FinalDecisionOut)
def decide_final(
    interview_id: UUID,
    payload: FinalDecisionIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FinalDecisionOut:
    """최종 합격/불합격 판단을 1회 저장하고 안내 메일을 자동 발송한다."""
    _require_recruiter(current_user)
    interview, candidate = _get_interview_or_404(db, interview_id, for_update=True)

    if interview.status != InterviewStatus.completed:
        raise AppError(409, "VALIDATION_ERROR", "Conflict", "면접이 완료된 건만 최종 합격/불합격을 처리할 수 있습니다.")
    if interview.final_decision is not None:
        raise AppError(409, "VALIDATION_ERROR", "Conflict", "이미 최종 결과가 처리되어 변경할 수 없습니다.")

    interview.final_decision = FinalDecision(payload.status)
    interview.final_decision_note = payload.decision_note
    interview.final_decided_by = current_user.id
    interview.final_decided_at = datetime.now(UTC)
    db.commit()
    db.refresh(interview)

    # 메일 미설정·SMTP 실패여도 판단 저장은 이미 끝났다. final_notified_at이 비어 있으면
    # 아래 수동 "발송 완료로 표시" 경로가 남는다(실제 발송이 확인된 때만 시각을 채운다).
    if email_configured():
        subject, body = _build_final_notification_content(interview, candidate)
        try:
            send_notification_email(candidate.email, subject, body)
            interview.final_notified_at = datetime.now(UTC)
            db.commit()
            db.refresh(interview)
        except EmailSendError:
            pass  # send_notification_email이 이미 경고 로그를 남겼다.

    return _to_out(interview)


@router.get("/reports/{interview_id}/final-notification-draft", response_model=NotificationDraftOut)
def get_final_notification_draft(
    interview_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationDraftOut:
    """실제로 보낸/보낼 최종 안내 메일 내용을 다시 확인한다(자동 발송 실패 시 수동 발송 참고용 겸용)."""
    _require_recruiter(current_user)
    interview, candidate = _get_interview_or_404(db, interview_id)

    if interview.final_decision is None:
        raise AppError(409, "VALIDATION_ERROR", "Conflict", "아직 최종 합격/불합격이 처리되지 않았습니다.")

    subject, body = _build_final_notification_content(interview, candidate)
    return NotificationDraftOut(to_email=candidate.email, subject=subject, body=body)


@router.post("/reports/{interview_id}/final-mark-notified", response_model=FinalDecisionOut)
def mark_final_notified(
    interview_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FinalDecisionOut:
    """자동 발송이 실패했을 때 담당자가 직접 보낸 뒤 누르는 "발송 완료" 표시. 이미 발송 시각이
    있으면 덮어쓰지 않는다(감사 기록 보존, 멱등)."""
    _require_recruiter(current_user)
    interview, _candidate = _get_interview_or_404(db, interview_id, for_update=True)

    if interview.final_decision is None:
        raise AppError(409, "VALIDATION_ERROR", "Conflict", "아직 최종 합격/불합격이 처리되지 않았습니다.")

    if interview.final_notified_at is None:
        interview.final_notified_at = datetime.now(UTC)
        db.commit()
        db.refresh(interview)
    return _to_out(interview)
