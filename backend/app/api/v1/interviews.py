"""REQ-002/REQ-013: 면접 세션 생성/시작/종료/재개 상태머신 (03-system-design.md §3, §4.2, §6.2).

범위(unit-2, Feature B): `POST /interviews`(생성), `POST /interviews/{id}/start`(시작),
`POST /interviews/{id}/end`(종료) 3개 엔드포인트.

범위(unit-3, Feature B, REQ-013): `GET /interviews/{id}`(상세조회 — 세션 메타데이터
기준 재개 가능 여부 판단), `POST /interviews/{id}/resume`(중단된 세션 재개). 실제
대화(turn)/코드/화이트보드 콘텐츠 복원은 아직 해당 데이터가 없어(TRANSCRIPTS/
CODE_SUBMISSIONS/WHITEBOARD_SNAPSHOTS 모델 미생성) 이번 유닛 책임이 아니다 — 03-design
§4.2가 신설한 `GET /interviews/{id}/code-submissions`·`GET /interviews/{id}/whiteboard`는
각각 unit-9(라이브 코딩)·unit-17(화이트보드)이 자신의 모델을 만들 때 구현한다
(unit-3-note.md §1 참고). `GET /interviews`(목록 조회)는 여전히 이번 유닛 범위 밖이다
(unit-2-note.md "설계서 대비 편차" §2-6 그대로 유지).
"""
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.errors import AppError
from app.db.session import get_db
from app.models.consent import Consent, ConsentType
from app.models.interview import Interview, InterviewStatus, ReportStatus
from app.models.user import User, UserRole
from app.schemas.interview import InterviewDetailOut, InterviewEndResponse, InterviewOut, InterviewStartResponse
from app.services.job_queue import enqueue_opening_question_job, enqueue_report_generation_job

router = APIRouter(prefix="/interviews", tags=["interviews"])

# REQ-013 / DEC-026: 03-design §4.1은 `SESSION_EXPIRED`(410) 에러코드만 정의하고
# "장시간 경과"의 정확한 시간 값은 05단계(구현)가 확정하도록 04-ux-design.md [C-12]가
# 명시적으로 위임했다. 이 유닛에서 24시간으로 확정한다 — 근거: (1) live로 전환된 뒤
# WS/turn 인프라가 아직 없어(unit-4 이후 범위) 서버가 최근 활동 시각을 알 방법이
# `started_at` 외에는 없다, (2) 하루가 지나도록 끝나지 않은 연습 세션은 사실상 방치된
# 세션으로 보는 것이 합리적 기본값이다. 상수 하나로 격리되어 있어 되돌리기 쉬우며
# (Low 비가역성), unit-4 이후 실제 마지막 turn 시각 기준으로 바꿀 수 있다.
SESSION_EXPIRY = timedelta(hours=24)


def _get_own_interview(interview_id: UUID, current_user: User, db: Session) -> Interview:
    """본인 소유 세션만 조회/조작 가능하게 한다 (수평 권한 상승 방지)."""
    interview = db.get(Interview, interview_id)
    if interview is None:
        raise AppError(404, "NOT_FOUND", "Not Found", "면접 세션을 찾을 수 없습니다.")
    if interview.candidate_id != current_user.id:
        # 존재 여부까지 노출하지 않기 위해 404와 동일한 메시지 형태를 쓰지 않고
        # 명시적으로 403을 반환한다 — 이 리소스에 대한 소유권이 없다는 사실 자체는
        # 로그인한 본인 계정 컨텍스트 안에서 노출되어도 무방하다(로그인 계정 존재
        # 여부를 묻는 auth 흐름과는 성격이 다름).
        raise AppError(403, "AUTH_FORBIDDEN", "Forbidden", "본인의 면접 세션만 조작할 수 있습니다.")
    return interview


def _has_active_consent(db: Session, user_id, consent_type: ConsentType) -> bool:
    stmt = select(Consent).where(
        Consent.user_id == user_id,
        Consent.consent_type == consent_type,
        Consent.revoked_at.is_(None),
    )
    return db.scalar(stmt) is not None


def _apply_lazy_expiry(interview: Interview, db: Session) -> Interview:
    """REQ-013: `live`/`paused` 세션이 SESSION_EXPIRY를 넘겼으면 `expired`로 확정한다.

    03-design §5.3/§5.4는 이 프로젝트에 별도 배치/타이머 인프라를 두지 않는다(단일서버,
    베스트에포트). 그 대신 04-ux-design [C-12]가 명시한 대로 "서버가 내려주는
    SESSION_EXPIRED를 그대로 표시"하는 방식 — 즉 클라이언트가 실제로 조회/재개를
    시도하는 시점에 반응적으로(lazy) 판정한다. 판정 결과(`expired`)는 DB에 즉시
    커밋해, 이후 같은 세션을 다시 조회해도 재계산 없이 같은 상태가 나오게 한다.
    """
    if interview.status in (InterviewStatus.live, InterviewStatus.paused) and interview.started_at is not None:
        elapsed = datetime.now(UTC) - interview.started_at
        if elapsed > SESSION_EXPIRY:
            interview.status = InterviewStatus.expired
            db.commit()
            db.refresh(interview)
    return interview


@router.post("", response_model=InterviewOut, status_code=status.HTTP_201_CREATED)
def create_interview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Interview:
    # 03-design §6.1: INTERVIEWS.candidate_id가 세션의 주체이므로 지원자(candidate)만
    # 자신의 면접 세션을 생성할 수 있다(recruiter/admin은 면접 응시자가 아님).
    if current_user.role != UserRole.candidate:
        raise AppError(403, "AUTH_FORBIDDEN", "Forbidden", "지원자(candidate)만 면접 세션을 생성할 수 있습니다.")

    interview = Interview(
        candidate_id=current_user.id,
        status=InterviewStatus.scheduled,
        report_status=ReportStatus.none,
    )
    db.add(interview)
    db.commit()
    db.refresh(interview)
    return interview


@router.post("/{interview_id}/start", response_model=InterviewStartResponse, status_code=status.HTTP_202_ACCEPTED)
def start_interview(
    interview_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InterviewStartResponse:
    interview = _get_own_interview(interview_id, current_user, db)

    if interview.status != InterviewStatus.scheduled:
        raise AppError(
            409,
            "VALIDATION_ERROR",
            "Conflict",
            f"scheduled 상태의 세션만 시작할 수 있습니다 (현재 상태: {interview.status.value}).",
        )

    # DEC-023: /start는 ai_interview_notice 동의만 검사한다. biometric_voice는
    # 여기서 절대 검사하지 않는다(§6.2) — 음성 제출 시점(/turns, unit-5 이후 범위)으로
    # 이동되었다.
    if not _has_active_consent(db, current_user.id, ConsentType.ai_interview_notice):
        raise AppError(
            403,
            "CONSENT_REQUIRED_NOTICE",
            "Forbidden",
            "AI 면접 진행/평가 사실에 대한 사전고지 동의가 필요합니다.",
        )

    interview.status = InterviewStatus.live
    interview.started_at = datetime.now(UTC)
    db.commit()
    db.refresh(interview)

    job_id = enqueue_opening_question_job(interview.id)

    return InterviewStartResponse(job_id=job_id, interview=InterviewOut.model_validate(interview))


@router.post("/{interview_id}/end", response_model=InterviewEndResponse, status_code=status.HTTP_202_ACCEPTED)
def end_interview(
    interview_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InterviewEndResponse:
    interview = _get_own_interview(interview_id, current_user, db)

    if interview.status != InterviewStatus.live:
        raise AppError(
            409,
            "VALIDATION_ERROR",
            "Conflict",
            f"live 상태의 세션만 종료할 수 있습니다 (현재 상태: {interview.status.value}).",
        )

    interview.status = InterviewStatus.completed
    interview.ended_at = datetime.now(UTC)
    interview.report_status = ReportStatus.queued
    db.commit()
    db.refresh(interview)

    job_id = enqueue_report_generation_job(interview.id)

    return InterviewEndResponse(job_id=job_id, interview=InterviewOut.model_validate(interview))


def _to_detail(interview: Interview) -> InterviewDetailOut:
    resumable = interview.status in (InterviewStatus.live, InterviewStatus.paused)
    return InterviewDetailOut(**InterviewOut.model_validate(interview).model_dump(), resumable=resumable)


@router.get("/{interview_id}", response_model=InterviewDetailOut, status_code=status.HTTP_200_OK)
def get_interview(
    interview_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InterviewDetailOut:
    """REQ-013: 재접속 시 "지금 이 세션이 어디까지 진행됐는지" 판단용 상세 조회.

    현재 세션 메타데이터(status/report_status/started_at/ended_at 등)와 파생 필드
    `resumable`만 반환한다. turn/코드/화이트보드 등 실제 콘텐츠는 아직 존재하지
    않으므로(unit-4~9 이후 범위) 포함하지 않는다.
    """
    interview = _get_own_interview(interview_id, current_user, db)
    interview = _apply_lazy_expiry(interview, db)
    return _to_detail(interview)


@router.post("/{interview_id}/resume", response_model=InterviewDetailOut, status_code=status.HTTP_200_OK)
def resume_interview(
    interview_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InterviewDetailOut:
    """REQ-013: 중단된 세션 재개(03-design §4.2 `/resume`).

    `live`(재접속 시 아직 별도 중단 감지 메커니즘이 없어 그대로 진행 가능한 상태) 또는
    `paused`(향후 유닛이 명시적으로 설정할 수 있는 상태, ERD에 존재)에서만 재개 가능.
    `paused`였다면 `live`로 전환하고, 이미 `live`면 멱등하게 그대로 둔다(§5.4 job
    idempotency 원칙을 세션 재개에도 동일 적용). `scheduled`/`completed`는 애초에
    "중단"이 성립하지 않는 상태라 409, 만료됐으면 410을 반환한다.
    """
    interview = _get_own_interview(interview_id, current_user, db)
    interview = _apply_lazy_expiry(interview, db)

    if interview.status == InterviewStatus.expired:
        raise AppError(
            410,
            "SESSION_EXPIRED",
            "Gone",
            "이 세션은 만료되어 재개할 수 없습니다. 새 면접을 시작해 주세요.",
        )

    if interview.status not in (InterviewStatus.live, InterviewStatus.paused):
        raise AppError(
            409,
            "VALIDATION_ERROR",
            "Conflict",
            f"live 또는 paused 상태의 세션만 재개할 수 있습니다 (현재 상태: {interview.status.value}).",
        )

    if interview.status == InterviewStatus.paused:
        interview.status = InterviewStatus.live
        db.commit()
        db.refresh(interview)

    return _to_detail(interview)
