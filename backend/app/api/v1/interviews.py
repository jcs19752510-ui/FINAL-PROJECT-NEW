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
(unit-2-note.md "설계서 대비 편차" §2-6 그대로 유지) — **unit-19가 이 갭을 메운다**(아래).

범위(unit-19, Feature B, REQ-002, DEC-029): `GET /interviews`(내 면접 목록, [C-03] 지원자
홈 전용). 03-design §4.2가 DEC-024 갭1로 신설한 엔드포인트다.

범위(unit-4, Feature C, REQ-003): `POST /interviews/{id}/turns`(**텍스트 전용**, 03-design
§4.2/§6.2 DEC-023 — 텍스트 제출은 생체정보 동의 검사와 무관하게 항상 허용). 음성
(multipart) 제출은 unit-5(REQ-004/005) 범위다. `GET /interviews/{id}/transcripts`는
03-design §4.2 표에 명시되지 않았으나, [C-06] 면접장 "로딩(초기 진입) — 이전 대화
이력 로드" 상태가 구조적으로 요구하는 조회 API라 unit-3의 `GET /interviews/{id}`
선례와 동일한 근거(additive, 두 갈래 해석 없음)로 이번 유닛에서 신설한다(unit-4-note.md
참고). AI 응답 생성(꼬리질문 LLM 호출)은 unit-7 범위이며, 이 유닛은 `job_queue.py`
스텁으로 API 계약(202 + WS 이벤트 스키마)만 완성한다.

범위(unit-5, Feature C, REQ-004/REQ-005): `POST /interviews/{id}/turns`를 **음성
(multipart) 제출까지 지원하도록 확장**한다. 03-design §4.3이 "턴 제출은 항상 REST
`POST /interviews/{id}/turns` 하나의 경로로만 이루어진다(텍스트는 JSON, 음성은
multipart)"라고 명시했으므로 별도 엔드포인트를 신설하지 않고 같은 경로를
`Content-Type`으로 분기한다(`_submit_voice_turn`/`_submit_text_turn`). DEC-023에
따라 음성 제출일 때만 매 요청 실시간으로 `biometric_voice` 동의를 재검사하고,
동의가 없거나 철회됐으면 `403 CONSENT_REQUIRED_VOICE`를 반환하며 오디오는 어떤
형태로도 저장하지 않는다(`app/services/stt_engine.py`가 디스크에 파일을 쓰지 않고
메모리에서만 처리). STT(`transcribe_audio`)는 실제로 동작하지만, AI 응답 생성
(LLM 꼬리질문)은 여전히 unit-7 범위라 `enqueue_turn_job` 스텁을 그대로 재사용한다.

범위(unit-6, Feature C, REQ-006): `POST /interviews/{id}/tts-preview`(신규,
설계서 §4.2 REST 표에는 없는 준비/검증 엔드포인트 — 아래 라우터 docstring 참고).
`app/services/tts_engine.py`(Piper 어댑터)가 임의의 텍스트를 실제 음성(WAV)으로
합성해 `/media/tts/*.wav`로 저장하고, 이 엔드포인트는 그 결과 URL을 반환한다.
LLM(unit-7)이 아직 없어 "AI가 생성한 응답 텍스트" 자체는 존재하지 않으므로,
`turn_result.audio_url`(§4.3)을 실제 인터뷰 턴 흐름에 연결하는 것은 이번 유닛
범위가 아니다 — TTS 서비스 자체(텍스트→음성)와 그 결과를 API로 내려받는 경로만
실제로 완성한다.
"""
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_user
from app.core.errors import AppError
from app.db.session import get_db
from app.models.consent import Consent, ConsentType
from app.models.evaluation_report import EvaluationReport
from app.models.interview import Interview, InterviewStatus, ReportStatus
from app.models.transcript import InputMode, Speaker, Transcript
from app.models.user import User, UserRole
from app.schemas.interview import (
    InterviewDetailOut,
    InterviewEndResponse,
    InterviewListItemOut,
    InterviewOut,
    InterviewStartResponse,
    ReportOut,
    StarOut,
)
from app.schemas.transcript import TranscriptOut, TurnAcceptedResponse, TurnCreate, VoicePreviewResponse
from app.services.job_queue import enqueue_opening_question_job, enqueue_report_generation_job, enqueue_turn_job
from app.services.prompt_safety import (
    RateLimitExceeded,
    check_and_increment_preview_rate_limit,
    check_and_increment_turn_rate_limit,
    log_injection_attempt,
)
from app.services.prosody_engine import ProsodyAnalysisError, analyze_prosody
from app.services.stt_engine import SttTranscriptionError, transcribe_audio
from app.services.tts_engine import TtsSynthesisError, synthesize_speech_file
from app.services.turn_numbering import insert_transcript_with_retry

logger = logging.getLogger(__name__)

# unit-5: 설계서에 명시되지 않은 구현 세부값(비가역성 낮음, 상수 하나로 격리). 음성
# 답변 하나가 이 크기를 넘으면 422로 거부해 대용량 업로드로 메모리를 소모하지 않게
# 한다 — 약 10분 분량의 16kHz/16bit 모노 WAV 원본 크기 이상의 여유를 둔 값.
MAX_VOICE_UPLOAD_BYTES = 25 * 1024 * 1024

# 사용자 요청(2026-09-21): LLM(unit-7, 1.5B)이 `control:"end_interview"`를 신뢰성 있게
# 내지 못해(관찰상 거의 발생 안 함) 실사용 중 면접이 끝없이 이어지는 문제가 실측됨.
# 프런트에 종료 UI가 없던 갭과 맞물려 후보자가 답변을 몇 번 해야 하는지 알 수 없었다.
# 설계서에 명시된 값이 아닌 구현 세부값(상수 하나로 격리, 되돌리기 쉬움) — 지원자 턴
# (speaker=user) 개수 기준으로 5회를 넘는 제출은 거부한다.
MAX_CANDIDATE_TURNS = 5

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


def _to_list_item(interview: Interview) -> InterviewListItemOut:
    return InterviewListItemOut(
        id=interview.id,
        status=interview.status.value,
        report_status=interview.report_status.value,
        started_at=interview.started_at,
        ended_at=interview.ended_at,
        overall_score=interview.overall_score,
        created_at=interview.created_at,
        resumable=interview.status in (InterviewStatus.live, InterviewStatus.paused),
    )


@router.get("", response_model=list[InterviewListItemOut], status_code=status.HTTP_200_OK)
def list_my_interviews(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[InterviewListItemOut]:
    """REQ-002(unit-19, DEC-029): 내(지원자 본인) 면접 목록 — [C-03] 지원자 홈용 (03-design §4.2).

    소유자 필터는 쿼리 파라미터가 아니라 인증된 사용자 id로만 서버가 고정한다(타인 세션
    노출 = 수평 권한 상승 방지). 면접 세션의 주체는 candidate뿐이므로(`create_interview`와
    동일 근거, §6.1 RBAC) 그 외 역할은 403이다. 정렬은 04-ux-design [C-03] "최근 면접"에 따라
    카드에 표시되는 일시(`started_at`, 아직 시작 전이면 `created_at`) 내림차순(동률은 id
    내림차순으로 고정)이고, 설계서에 없는 페이지네이션/필터는 도입하지 않는다.
    24시간을 넘긴 `live`/`paused`는 상세/재개 조회와 동일하게 이 시점에 `expired`로
    확정해, 홈의 "진행 중 세션" 안내가 재개 불가 세션을 가리키지 않게 한다.
    """
    if current_user.role != UserRole.candidate:
        raise AppError(403, "AUTH_FORBIDDEN", "Forbidden", "지원자(candidate)만 본인 면접 목록을 조회할 수 있습니다.")

    stmt = (
        select(Interview)
        .where(Interview.candidate_id == current_user.id)
        .order_by(func.coalesce(Interview.started_at, Interview.created_at).desc(), Interview.id.desc())
    )
    interviews = list(db.scalars(stmt).all())
    return [_to_list_item(_apply_lazy_expiry(interview, db)) for interview in interviews]


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


def _get_report_viewable_interview(interview_id: UUID, current_user: User, db: Session) -> Interview:
    """`GET /{id}/report`(Feature E) 캐노니컬 RBAC: 03-design §6.1 "채용담당자
    대시보드 — recruiter 역할이면 전 지원자 리포트 열람 가능(단일 조직 MVP 정책,
    organization_id 세분화 없음)" + 지원자 본인 소유. `_get_own_interview`와 달리
    recruiter도 통과시킨다.
    """
    interview = db.get(Interview, interview_id)
    if interview is None:
        raise AppError(404, "NOT_FOUND", "Not Found", "면접 세션을 찾을 수 없습니다.")
    if current_user.role != UserRole.recruiter and interview.candidate_id != current_user.id:
        raise AppError(403, "AUTH_FORBIDDEN", "Forbidden", "본인의 면접 세션이거나 채용담당자만 조회할 수 있습니다.")
    return interview


def _report_to_out(interview: Interview, report: EvaluationReport | None) -> ReportOut:
    star = StarOut(**report.star_json) if report is not None and report.star_json else None
    return ReportOut(
        interview_id=interview.id,
        report_status=interview.report_status.value,
        overall_score=interview.overall_score,
        technical_score=report.technical_score if report else None,
        communication_score=report.communication_score if report else None,
        cultural_fit_score=report.cultural_fit_score if report else None,
        overall_recommendation=report.overall_recommendation.value
        if report and report.overall_recommendation
        else None,
        pass_fail_recommendation=report.pass_fail_recommendation.value
        if report and report.pass_fail_recommendation
        else None,
        star=star,
        summary_text=report.summary_text if report else None,
        details=report.details_json if report else None,
    )


@router.get("/{interview_id}/report", response_model=None)
def get_report(
    interview_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReportOut | JSONResponse:
    """캐노니컬 리포트 조회(Feature E, REQ-009/010/012, 03-design §4.2 그대로) —
    지원자 본인([C-11])과 채용담당자([R-02])가 공유한다(`app/api/v1/recruiter.py`가
    이 로직의 얇은 래퍼로 recruiter 전용 경로도 계속 제공한다).
    """
    interview = _get_report_viewable_interview(interview_id, current_user, db)

    if interview.report_status == ReportStatus.none:
        raise AppError(409, "VALIDATION_ERROR", "Conflict", "면접이 아직 종료되지 않아 리포트가 없습니다.")
    if interview.report_status == ReportStatus.queued:
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"status": "processing"})
    if interview.report_status == ReportStatus.failed:
        raise AppError(
            409,
            "REPORT_GENERATION_FAILED",
            "Conflict",
            "리포트 생성에 실패했습니다. `/report/regenerate`로 다시 시도해주세요.",
        )

    report = db.scalar(select(EvaluationReport).where(EvaluationReport.interview_id == interview_id))
    return _report_to_out(interview, report)


@router.post("/{interview_id}/report/regenerate", status_code=status.HTTP_202_ACCEPTED)
def regenerate_report(
    interview_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """리포트 재시도(Feature E, 03-design §4.2) — `report_status=failed`일 때만
    허용한다. 재시도 실행 주체는 지원자 본인으로 한정한다(recruiter는 열람만
    가능, `/end`와 동일하게 세션 소유자만 상태를 바꿀 수 있다는 원칙 유지).
    """
    interview = _get_own_interview(interview_id, current_user, db)

    if interview.report_status != ReportStatus.failed:
        raise AppError(
            409,
            "VALIDATION_ERROR",
            "Conflict",
            f"리포트 생성이 실패한 세션만 재시도할 수 있습니다 (현재 상태: {interview.report_status.value}).",
        )

    interview.report_status = ReportStatus.queued
    db.commit()

    job_id = enqueue_report_generation_job(interview.id)
    return {"job_id": job_id}


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


def _ensure_turn_submittable(interview: Interview, db: Session) -> Interview:
    """텍스트/음성 공통: `live` 상태 세션에만 턴 제출을 허용한다 (03-design §4.2)."""
    interview = _apply_lazy_expiry(interview, db)

    if interview.status == InterviewStatus.expired:
        raise AppError(
            410,
            "SESSION_EXPIRED",
            "Gone",
            "이 세션은 만료되었습니다. 새 면접을 시작해 주세요.",
        )

    if interview.status != InterviewStatus.live:
        raise AppError(
            409,
            "VALIDATION_ERROR",
            "Conflict",
            f"live 상태의 세션에만 턴을 제출할 수 있습니다 (현재 상태: {interview.status.value}).",
        )

    candidate_turn_count = db.execute(
        select(func.count())
        .select_from(Transcript)
        .where(Transcript.interview_id == interview.id, Transcript.speaker == Speaker.user)
    ).scalar_one()
    if candidate_turn_count >= MAX_CANDIDATE_TURNS:
        raise AppError(
            409,
            "TURN_LIMIT_REACHED",
            "Conflict",
            f"답변 횟수 제한({MAX_CANDIDATE_TURNS}회)에 도달했습니다. 면접을 종료해주세요.",
        )
    return interview


def _submit_text_turn(interview: Interview, payload: TurnCreate, db: Session) -> TurnAcceptedResponse:
    """REQ-003: 텍스트 턴 제출 (03-design §4.2/§4.3).

    DEC-023: 텍스트(`input_mode=text`) 제출은 `biometric_voice` 동의 검사와 무관하게
    항상 허용한다 — 이 검사는 음성(multipart) 제출(`_submit_voice_turn`)에만 적용된다.

    턴 채번은 `app/services/turn_numbering.py`(DEF-002/DEC-035 Q5, `(interview_id,
    turn_index)` 유니크 제약 + 재시도)로 통일한다.

    unit-27(REQ-035/038, AI 안전장치, 2026-09-22 사용자 승인): 레이트리밋(사용자당
    분당 상한 — interview_id가 아닌 candidate_id 기준인 이유는 prompt_safety.py
    모듈 주석 참고, 기존 "세션당 턴 5회 제한"과 겹치지 않게 하기 위함)을 먼저
    검사하고, 인젝션 의심 패턴은 차단 없이 감사 로그만 남긴다(오탐으로 정상
    답변을 막지 않기 위함).
    """
    try:
        check_and_increment_turn_rate_limit(str(interview.candidate_id))
    except RateLimitExceeded as exc:
        raise AppError(429, "RATE_LIMIT_EXCEEDED", "Too Many Requests", str(exc)) from exc
    log_injection_attempt(str(interview.candidate_id), str(interview.id), payload.text)

    transcript = insert_transcript_with_retry(
        db,
        interview.id,
        lambda turn_index: Transcript(
            interview_id=interview.id,
            turn_index=turn_index,
            speaker=Speaker.user,
            input_mode=InputMode.text,
            content_text=payload.text,
        ),
    )

    job_id = enqueue_turn_job(interview.id, transcript.id)
    return TurnAcceptedResponse(job_id=job_id)


async def _submit_voice_turn(
    interview: Interview, current_user: User, db: Session, request: Request
) -> TurnAcceptedResponse:
    """REQ-004/REQ-005: 음성(multipart) 턴 제출 (03-design §4.2/§4.3/§6.2 DEC-023).

    (1) `biometric_voice` 동의를 **매 요청마다 실시간으로 DB 재조회**해 검사한다
    (세션 컨텍스트 캐시 금지, §6.2). 동의가 없거나 철회됐으면 오디오를 조금도
    읽지 않고(멀티파트 파싱조차 시도하지 않고) 즉시 403을 반환한다.
    (2) STT는 `app/services/stt_engine.py`(faster-whisper)로 실제 변환하며, 변환에
    쓰인 오디오 바이트는 메모리에서만 존재하다가 함수 종료와 함께 버려진다(디스크
    미기록, §6.2 최소수집).
    (3) 변환된 텍스트만 `TRANSCRIPTS(input_mode=voice, audio_ref=null)`로 영구 저장한다.
    (4) AI 응답 생성(LLM)은 unit-7 범위라 텍스트 턴과 동일하게 `enqueue_turn_job`
    스텁으로 202 계약만 충족한다.
    """
    if not _has_active_consent(db, current_user.id, ConsentType.biometric_voice):
        raise AppError(
            403,
            "CONSENT_REQUIRED_VOICE",
            "Forbidden",
            "음성으로 답변하려면 생체정보(음성) 수집 동의가 필요합니다.",
        )

    # unit-27(REQ-038, 2026-09-22 사용자 승인): 오디오 파싱/STT를 시작하기 전에
    # 레이트리밋부터 검사한다 — 한도 초과 요청이 무거운 STT 작업까지 도달하지
    # 않게 해 자원 낭비를 줄인다(간단한 Redis 카운터 증가만 수행, 오늘 실제
    # 장애가 있었던 STT/threadpool 로직은 전혀 건드리지 않음).
    try:
        check_and_increment_turn_rate_limit(str(current_user.id))
    except RateLimitExceeded as exc:
        raise AppError(429, "RATE_LIMIT_EXCEEDED", "Too Many Requests", str(exc)) from exc

    try:
        form = await request.form()
    except Exception as exc:  # noqa: BLE001 — 잘못된 multipart 인코딩 등 클라이언트 입력 오류
        raise AppError(422, "VALIDATION_ERROR", "Validation Error", "multipart 형식이 올바르지 않습니다.") from exc

    audio = form.get("audio")
    if audio is None or not hasattr(audio, "read"):
        raise AppError(422, "VALIDATION_ERROR", "Validation Error", "음성 파일(`audio` 필드)이 필요합니다.")

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise AppError(422, "VALIDATION_ERROR", "Validation Error", "빈 음성 파일입니다.")
    if len(audio_bytes) > MAX_VOICE_UPLOAD_BYTES:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "Validation Error",
            f"음성 파일이 너무 큽니다 (최대 {MAX_VOICE_UPLOAD_BYTES // (1024 * 1024)}MB).",
        )

    try:
        # 장애 대응(2026-09-22): faster-whisper STT는 초 단위로 걸릴 수 있는 동기
        # CPU 작업이다. 이 함수는 `async def` 체인 안에서 직접 호출되므로 스레드풀
        # 없이 부르면 그 몇 초 동안 프로세스 전체의 이벤트 루프가 멈춘다(다른 모든
        # 요청/WS가 응답 불능이 됨) — 음성 답변 제출이 실제 백엔드 행을 일으킨
        # 근본 원인 중 하나로 확인되어 명시적으로 스레드풀에 위임한다.
        text = await run_in_threadpool(transcribe_audio, audio_bytes)
    except SttTranscriptionError as exc:
        raise AppError(
            504,
            "AI_SERVICE_TIMEOUT",
            "Gateway Timeout",
            "음성 인식 처리 중 오류가 발생했습니다. 다시 시도해주세요.",
        ) from exc

    # unit-24(원안 REQ-018/019 축소판, Prosody 분석, 2026-09-22 사용자 승인): STT와
    # 동일하게 동기 CPU 작업이라 반드시 threadpool로 위임한다(위 "장애 대응" 주석과
    # 동일 원칙 — 블로킹 재발 방지). 실패해도 턴 저장 자체는 막지 않는 선택적 부가
    # 분석이므로 별도 예외를 상위로 전파하지 않고 그레이스풀 디그레이드한다.
    prosody_json: dict | None = None
    try:
        prosody_json = await run_in_threadpool(analyze_prosody, audio_bytes)
    except ProsodyAnalysisError:
        logger.warning("prosody 분석 실패 — 그레이스풀 디그레이드(턴 저장에는 영향 없음)", exc_info=True)
    finally:
        # §6.2 최소수집: 이 스코프를 벗어나면 audio_bytes를 참조하는 곳이 없어 GC
        # 대상이 된다 — 별도 임시파일을 만들지 않았으므로 파기할 파일 자체가 없다.
        del audio_bytes

    if not text:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "Validation Error",
            "음성에서 텍스트를 인식하지 못했습니다. 다시 녹음해주세요.",
        )

    log_injection_attempt(str(interview.candidate_id), str(interview.id), text)

    transcript = await run_in_threadpool(
        insert_transcript_with_retry,
        db,
        interview.id,
        lambda turn_index: Transcript(
            interview_id=interview.id,
            turn_index=turn_index,
            speaker=Speaker.user,
            input_mode=InputMode.voice,
            content_text=text,
            audio_ref=None,
            prosody_json=prosody_json,
        ),
    )

    job_id = await run_in_threadpool(enqueue_turn_job, interview.id, transcript.id)
    return TurnAcceptedResponse(job_id=job_id)


@router.post("/{interview_id}/turns", response_model=TurnAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_turn(
    interview_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TurnAcceptedResponse:
    """턴 제출(텍스트 JSON 또는 음성 multipart) — 03-design §4.2/§4.3 "하나의 경로".

    `Content-Type: multipart/form-data`이면 음성 경로(`_submit_voice_turn`)로,
    그 외에는 텍스트 경로(`_submit_text_turn`)로 분기한다. 텍스트 경로는 unit-4가
    이미 사용하던 방식(FastAPI가 아닌 이 함수가 직접 `request.json()`을 파싱)과
    동일하게 `Content-Type` 헤더값과 무관하게 본문을 JSON으로 해석해 하위호환을
    유지한다(FastAPI의 pydantic 바디 파라미터도 원래 Content-Type을 검사하지 않고
    `request.json()`을 호출하는 것과 동일한 동작).
    """
    # 장애 대응(2026-09-22): 이 라우트는 `await request.body()`/`.form()`이 필요해
    # `async def`인데, 아래 헬퍼들은 전부 동기(블로킹) DB 호출이다. `async def`
    # 라우트는 FastAPI가 자동으로 스레드풀에 위임해주지 않으므로(그건 `def` 라우트만
    # 해당), 직접 호출하면 그 블로킹 동안 프로세스 전체의 단일 이벤트 루프가 멈춘다
    # (`ws.py::_authenticate`와 동일한 근본 원인, 실제 백엔드 응답 불능 장애로 실측
    # 확인됨). 매 턴 제출마다 지나가는 경로라 영향이 커 스레드풀로 명시적으로 넘긴다.
    interview = await run_in_threadpool(_get_own_interview, interview_id, current_user, db)
    interview = await run_in_threadpool(_ensure_turn_submittable, interview, db)

    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        return await _submit_voice_turn(interview, current_user, db, request)

    body = await request.body()
    try:
        payload = TurnCreate.model_validate_json(body)
    except ValidationError as exc:
        raise AppError(422, "VALIDATION_ERROR", "Validation Error", str(exc.errors())) from exc
    return await run_in_threadpool(_submit_text_turn, interview, payload, db)


@router.post(
    "/{interview_id}/turns/preview",
    response_model=VoicePreviewResponse,
    status_code=status.HTTP_200_OK,
)
async def submit_voice_preview(
    interview_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VoicePreviewResponse:
    """REQ-004 축소판(unit-36, STT 실시간 스트리밍 미리보기, 2026-09-23 사용자 승인).

    지원자가 답변을 녹음하는 "도중"(아직 최종 제출 전) 약 4초 간격으로 짧은
    오디오 조각을 이 엔드포인트로 보내면, STT로만 변환해 텍스트를 즉시
    돌려준다 — 화면에 "지금까지 인식된 답변" 미리보기를 보여주기 위함이다.

    **기존 `_submit_voice_turn`(오늘 실제 장애가 있었던 경로)은 전혀 건드리지
    않는다** — 별도 엔드포인트로 완전히 분리했다:
    - `TRANSCRIPTS`에 아무것도 저장하지 않는다(순수 조회성, 최종 제출이 아님).
    - AI 응답 생성 job을 큐에 넣지 않는다.
    - prosody 분석을 하지 않는다(최종 제출 시에만 의미 있음, 매 4초마다 돌리면
      자원 낭비).
    - 별도의 더 여유로운 레이트리밋(`check_and_increment_preview_rate_limit`)을
      쓴다 — 정식 턴 레이트리밋(분당 10회)을 쓰면 답변 하나 녹음하는 도중에도
      바로 429가 나기 때문.
    - 인식 결과가 빈 문자열이어도(무음 구간 등) 422로 거부하지 않고 빈 문자열
      그대로 반환한다 — 최종 제출과 달리 "이 조각에는 말이 없었다"가 정상 상태.
    """
    interview = await run_in_threadpool(_get_own_interview, interview_id, current_user, db)
    if interview.status != InterviewStatus.live:
        raise AppError(
            409,
            "VALIDATION_ERROR",
            "Conflict",
            f"live 상태의 세션에만 미리보기를 요청할 수 있습니다 (현재 상태: {interview.status.value}).",
        )

    if not await run_in_threadpool(_has_active_consent, db, current_user.id, ConsentType.biometric_voice):
        raise AppError(
            403,
            "CONSENT_REQUIRED_VOICE",
            "Forbidden",
            "음성 미리보기를 사용하려면 생체정보(음성) 수집 동의가 필요합니다.",
        )

    try:
        check_and_increment_preview_rate_limit(str(current_user.id))
    except RateLimitExceeded as exc:
        raise AppError(429, "RATE_LIMIT_EXCEEDED", "Too Many Requests", str(exc)) from exc

    try:
        form = await request.form()
    except Exception as exc:  # noqa: BLE001 — 잘못된 multipart 인코딩 등 클라이언트 입력 오류
        raise AppError(422, "VALIDATION_ERROR", "Validation Error", "multipart 형식이 올바르지 않습니다.") from exc

    audio = form.get("audio")
    if audio is None or not hasattr(audio, "read"):
        raise AppError(422, "VALIDATION_ERROR", "Validation Error", "음성 파일(`audio` 필드)이 필요합니다.")

    audio_bytes = await audio.read()
    if not audio_bytes:
        # 최종 제출과 달리 조용히 빈 텍스트를 돌려준다 — 미리보기 조각 하나가
        # 비어있는 건 정상적인 무음 구간일 수 있다.
        return VoicePreviewResponse(text="")
    if len(audio_bytes) > MAX_VOICE_UPLOAD_BYTES:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "Validation Error",
            f"음성 조각이 너무 큽니다 (최대 {MAX_VOICE_UPLOAD_BYTES // (1024 * 1024)}MB).",
        )

    try:
        text = await run_in_threadpool(transcribe_audio, audio_bytes)
    except SttTranscriptionError:
        # 미리보기는 부가 기능이라 STT가 실패해도 사용자 작업을 막지 않는다
        # (그레이스풀 디그레이드 — 다음 4초 조각에서 다시 시도됨).
        logger.warning("음성 미리보기 STT 실패 — 그레이스풀 디그레이드", exc_info=True)
        return VoicePreviewResponse(text="")
    finally:
        del audio_bytes

    return VoicePreviewResponse(text=text)


@router.get("/{interview_id}/transcripts", response_model=list[TranscriptOut], status_code=status.HTTP_200_OK)
def list_transcripts(
    interview_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Transcript]:
    """(신규, unit-4 additive — 위 모듈 docstring 참고) [C-06] 초기 진입/재접속 시
    채팅 타임라인을 복원하기 위한 대화 이력 조회. `turn_index` 오름차순으로 반환한다.
    """
    interview = _get_own_interview(interview_id, current_user, db)
    stmt = (
        select(Transcript)
        .where(Transcript.interview_id == interview.id)
        .order_by(Transcript.turn_index.asc())
    )
    return list(db.scalars(stmt).all())


class TtsPreviewRequest(BaseModel):
    """`POST /interviews/{id}/tts-preview` 요청 바디. 최대 길이는 설계서 미명시
    구현 세부값 — 진단용 엔드포인트 남용 방지를 위해 보수적으로 제한한다(unit-4의
    `TurnCreate.text` 4000자 제한보다 좁게 잡은 이유: 이 엔드포인트는 실제 AI 응답이
    아니라 임의 텍스트를 넣는 준비/검증 용도이므로 그만큼 짧게 제한해도 목적에
    지장이 없다).
    """

    text: str = Field(min_length=1, max_length=500)


class TtsPreviewResponse(BaseModel):
    audio_url: str


@router.post(
    "/{interview_id}/tts-preview",
    response_model=TtsPreviewResponse,
    status_code=status.HTTP_200_OK,
)
def synthesize_tts_preview(
    interview_id: UUID,
    payload: TtsPreviewRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TtsPreviewResponse:
    """REQ-006: Piper 기반 TTS 실제 합성 준비/검증 엔드포인트.

    **범위 경계(unit-6, 설계서 대비 편차 — unit-6-note.md §2 참고)**: 03-design
    §4.2 REST 표에는 이 엔드포인트가 명시되어 있지 않다. AI 응답(꼬리질문 등) 텍스트는
    LLM(unit-7)이 아직 없어 존재하지 않으므로, `turn_result` 이벤트의 `audio_url`을
    실제 AI 발화에 연결하는 것은 이번 유닛 범위가 아니다(§4.3). 이 엔드포인트는
    `app/services/tts_engine.py`(Piper 어댑터)가 임의의 텍스트를 실제로 음성 파일로
    합성하고, 그 결과를 클라이언트가 API로 내려받아 재생할 수 있음을 증명하기 위한
    준비/검증 경로다 — unit-7이 LLM 응답을 만들면 그 `speak_text`를 동일한
    `synthesize_speech_file()` 함수에 넘겨 `turn_result.audio_url`을 채우면 된다.
    본인 소유 세션에서만 호출 가능하게 제한해(수평 권한 상승 방지) 남용 범위를
    최소화했다(전역 레이트리밋 자체는 REQ-038/unit-8 범위이며 이 엔드포인트에는
    적용돼 있지 않다).
    """
    _get_own_interview(interview_id, current_user, db)

    try:
        audio_url = synthesize_speech_file(payload.text)
    except TtsSynthesisError as exc:
        raise AppError(
            504,
            "AI_SERVICE_TIMEOUT",
            "Gateway Timeout",
            "음성 합성 처리 중 오류가 발생했습니다. 다시 시도해주세요.",
        ) from exc

    return TtsPreviewResponse(audio_url=audio_url)
