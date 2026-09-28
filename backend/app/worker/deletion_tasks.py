"""데이터 삭제/보관기간 자동 파기 배치 (REQ-030/033, 03-system-design.md §6.2, DEC-091 후속).

2026-09-20(DEC-029)에 unit-21로 배정된 뒤 한 번도 구현되지 않은 채 남아있던 두
Celery beat 배치를 이번에 정산한다:

- **`delete_requested_data`**(매 시간): `DELETE /users/me/biometric-data`로 접수된
  `DELETION_REQUESTS(status=pending)`를 실제로 처리해 `completed`로 전이시킨다.
  03-design §6.2 "삭제요청 처리 배치는 매 시간 실행해 24시간 SLA에 충분한 여유를
  둔다"를 그대로 따른다.
- **`purge_expired_data`**(매일 1회): 보관기간(180일, 법률자문 미확정 임시값,
  §6.2·프런트 `LEGAL_DISCLAIMER_TEXT`와 동일 값) 경과분 텍스트 transcript/리포트를
  일괄 파기한다.

**범위 경계**: 03-design §6.2 "보관기간" 행은 명시적으로 "텍스트 transcript/리포트"
만 언급한다 — INTERVIEWS 행 자체, CODE_SUBMISSIONS, WHITEBOARD_SNAPSHOTS는 설계서가
명시하지 않아 이번 배치가 임의로 파기 범위에 포함하지 않았다(범위 확대는 별도 결정
필요, 인수인계).

**타겟별 처리(DeletionRequest.target)**:
- `biometric_only`: 음성 원본 파일은 STT 완료 즉시 삭제되어 이미 디스크에 없다
  (unit-5-note.md §2 최소수집 원칙 — `audio_ref`는 애초에 항상 null). DB에 남아있는
  유일한 "생체정보에서 파생된" 데이터는 음성 턴의 `Transcript.prosody_json`(unit-24,
  Prosody 원시수치)뿐이라, 이 배치는 그 사용자의 모든 음성 턴에서 `prosody_json`을
  null로 지운다(`audio_ref`도 방어적으로 함께 정리).
- `full_account`: **주의 — 이 값을 실제로 생성하는 API 엔드포인트가 현재 코드베이스에
  하나도 없다**(`consents.py` 전수 확인, `DeletionTarget.full_account`는 ERD enum에는
  있으나 03-design §4.2 REST 표에도 이 값을 만드는 엔드포인트가 정의돼 있지 않음).
  그래도 스키마가 이 값을 이미 지원하도록 설계돼 있어(향후 "계정 탈퇴" 기능이
  추가될 가능성 대비) 배치 로직 자체는 방어적으로 구현한다: 본인 소유 면접 전체와
  그 하위 데이터(transcripts/evaluation_reports/code_submissions/whiteboard_snapshots)
  를 실제로 삭제하고, `consents`도 삭제한 뒤 `users.deleted_at`을 채워 소프트
  삭제한다(로그인 차단, `auth.py::login` 기존 `deleted_at is not None` 검사가 그대로
  작동). `deletion_requests` 행 자체와 `users` 행은 감사 추적을 위해 하드 삭제하지
  않는다 — email/name 등 계정 식별 정보를 완전히 스크럽(익명화)할지는 이 배치의
  범위를 넘는 별도 정책 결정이 필요해 포함하지 않았다(사용자 결정 대기, 인수인계).

**운영 인수인계(중요)**: 이 두 태스크가 실제로 "매 시간"·"매일"마다 자동으로
실행되려면, 지금까지 이 프로젝트가 기동해온 `celery worker`(`-Q ai_pipeline`)와는
**별도의 신규 프로세스**인 `celery -A app.services.celery_app beat`가 함께 떠 있어야
한다(Celery beat 스케줄러). 이 배치 코드/스케줄 설정 자체는 이번에 완성·검증했지만,
`celery beat` 프로세스를 실제 운영에 상시 기동하는 것은 11단계(운영 인수인계)
범위의 배포 절차이며, 이 세션은 로컬 검증 시 태스크 함수를 직접 호출해 로직만
검증했다(§ 테스트 결과서 참고, 장시간 스케줄 발화 자체는 실측하지 않음).
"""
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models.code_submission import CodeSubmission
from app.models.consent import Consent
from app.models.deletion_request import DeletionRequest, DeletionRequestStatus, DeletionTarget
from app.models.evaluation_report import EvaluationReport
from app.models.interview import Interview
from app.models.transcript import InputMode, Transcript
from app.models.user import User
from app.models.whiteboard import WhiteboardSnapshot
from app.services.celery_app import celery_app

logger = logging.getLogger(__name__)

# 03-design §6.2: "텍스트 transcript/리포트: 기본 180일(법률자문 확인 필요 —
# 임시값)". frontend/lib/complianceContent.ts의 LEGAL_DISCLAIMER_TEXT와 동일 값을
# 유지해야 화면 고지와 실제 동작이 일치한다.
RETENTION_DAYS = 180


def _purge_biometric_only(db, user_id) -> int:
    """해당 사용자의 음성 턴에서 생체정보 파생 데이터(prosody_json)를 제거한다.

    반환값은 실제로 정리된 행 수(테스트/로그용).
    """
    interview_ids = db.scalars(select(Interview.id).where(Interview.candidate_id == user_id)).all()
    if not interview_ids:
        return 0

    voice_transcripts = db.scalars(
        select(Transcript).where(
            Transcript.interview_id.in_(interview_ids),
            Transcript.input_mode == InputMode.voice,
        )
    ).all()
    count = 0
    for t in voice_transcripts:
        if t.prosody_json is not None or t.audio_ref is not None:
            t.prosody_json = None
            t.audio_ref = None
            count += 1
    return count


def _purge_full_account(db, user: User) -> dict:
    """해당 사용자의 면접·대화·리포트·동의 전체를 삭제하고 계정을 소프트 삭제한다.

    현재 이 target을 생성하는 API가 없어(모듈 docstring 참고) 실제 운영 트래픽에서는
    호출되지 않지만, 스키마가 지원하는 값이라 방어적으로 구현해둔다.
    """
    interview_ids = db.scalars(select(Interview.id).where(Interview.candidate_id == user.id)).all()
    counts = {"transcripts": 0, "evaluation_reports": 0, "code_submissions": 0, "whiteboard_snapshots": 0}
    if interview_ids:
        counts["transcripts"] = db.execute(
            delete(Transcript).where(Transcript.interview_id.in_(interview_ids))
        ).rowcount
        counts["evaluation_reports"] = db.execute(
            delete(EvaluationReport).where(EvaluationReport.interview_id.in_(interview_ids))
        ).rowcount
        counts["code_submissions"] = db.execute(
            delete(CodeSubmission).where(CodeSubmission.interview_id.in_(interview_ids))
        ).rowcount
        counts["whiteboard_snapshots"] = db.execute(
            delete(WhiteboardSnapshot).where(WhiteboardSnapshot.interview_id.in_(interview_ids))
        ).rowcount
        db.execute(delete(Interview).where(Interview.id.in_(interview_ids)))

    db.execute(delete(Consent).where(Consent.user_id == user.id))
    user.deleted_at = datetime.now(UTC)
    return counts


@celery_app.task(name="app.worker.deletion_tasks.delete_requested_data")
def delete_requested_data() -> dict:
    """REQ-030: `DELETION_REQUESTS(status=pending)`를 실제로 처리해 `completed`로
    전이시킨다. Celery beat로 매 시간 실행(아래 celery_app.py의 beat_schedule).

    한 건 처리 실패가 나머지 요청 처리를 막지 않도록, 요청 1건당 개별 예외 경계를
    둔다(worker/tasks.py의 워커 태스크 최상위 경계 원칙과 동일).
    """
    db = SessionLocal()
    processed = 0
    failed = 0
    try:
        pending = db.scalars(
            select(DeletionRequest).where(DeletionRequest.status == DeletionRequestStatus.pending)
        ).all()
        for req in pending:
            try:
                user = db.get(User, req.user_id)
                if user is None:
                    logger.warning("deletion_request %s: user_id %s 없음 — completed로만 전이", req.id, req.user_id)
                elif req.target == DeletionTarget.biometric_only:
                    n = _purge_biometric_only(db, req.user_id)
                    logger.info("deletion_request %s: biometric_only 정리 %d건", req.id, n)
                elif req.target == DeletionTarget.full_account:
                    counts = _purge_full_account(db, user)
                    logger.info("deletion_request %s: full_account 정리 %s", req.id, counts)
                req.status = DeletionRequestStatus.completed
                req.completed_at = datetime.now(UTC)
                db.commit()
                processed += 1
            except Exception:  # noqa: BLE001 — 요청 1건 실패가 나머지를 막지 않게 격리
                db.rollback()
                logger.exception("deletion_request %s 처리 중 예외 — pending 상태 유지, 다음 회차 재시도", req.id)
                failed += 1
    finally:
        db.close()
    logger.info("delete_requested_data 배치 완료: processed=%d failed=%d", processed, failed)
    return {"processed": processed, "failed": failed}


@celery_app.task(name="app.worker.deletion_tasks.purge_expired_data")
def purge_expired_data() -> dict:
    """REQ-033: 보관기간(180일) 경과한 텍스트 transcript/리포트를 일괄 파기한다.
    Celery beat로 매일 1회 실행(아래 celery_app.py의 beat_schedule).

    범위는 모듈 docstring 참고 — INTERVIEWS/CODE_SUBMISSIONS/WHITEBOARD_SNAPSHOTS는
    03-design §6.2가 명시하지 않아 포함하지 않는다.
    """
    cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)
    db = SessionLocal()
    try:
        transcripts_deleted = db.execute(delete(Transcript).where(Transcript.created_at < cutoff)).rowcount
        reports_deleted = db.execute(delete(EvaluationReport).where(EvaluationReport.created_at < cutoff)).rowcount
        db.commit()
    except Exception:  # noqa: BLE001 — 배치 최상위 경계, 다음 스케줄에 재시도
        db.rollback()
        logger.exception("purge_expired_data 배치 중 예외 발생")
        raise
    finally:
        db.close()
    logger.info(
        "purge_expired_data 배치 완료: transcripts=%d reports=%d cutoff=%s",
        transcripts_deleted,
        reports_deleted,
        cutoff.isoformat(),
    )
    return {"transcripts_deleted": transcripts_deleted, "reports_deleted": reports_deleted}
