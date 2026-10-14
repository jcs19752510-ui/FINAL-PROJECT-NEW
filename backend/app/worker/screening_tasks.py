"""이력서 AI 합격 판정 Celery 태스크 (2026-10-14).

- `screen_resume_job(application_id)`: 제출 직후 1건 즉시 처리(job_queue.enqueue_screening_job).
- `screen_pending_resumes`: beat 가 매분 호출 — 현재 면접기준으로 미분석/실패(상한 미만) 이력서를
  `screening_batch_size` 건씩 순차 처리한다. 건마다 별도 DB 세션이라 한 건의 예외가 나머지를 막지 않는다.

`celery -A app.services.celery_app beat` 프로세스가 떠 있어야 배치가 돈다(워커와 별개 프로세스).
"""
import logging
import uuid

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.celery_app import celery_app

logger = logging.getLogger(__name__)


def _screen_one(application_id: uuid.UUID) -> str:
    from app.services import resume_screening  # LLM 의존 모듈은 지연 import

    with SessionLocal() as db:
        return resume_screening.screen_application(db, application_id)


@celery_app.task(name="app.worker.screening_tasks.screen_resume_job")
def screen_resume_job(application_id: str) -> str:
    try:
        return _screen_one(uuid.UUID(str(application_id)))
    except Exception:  # noqa: BLE001
        logger.exception("이력서 AI 판정 job 실패: %s", application_id)
        return "failed"


@celery_app.task(name="app.worker.screening_tasks.screen_pending_resumes")
def screen_pending_resumes() -> dict:
    counts = {"done": 0, "failed": 0, "skipped": 0}
    if not settings.screening_enabled:
        return counts
    from app.services import resume_screening

    with SessionLocal() as db:
        ids = resume_screening.list_pending_ids(db, settings.screening_batch_size)
    for application_id in ids:
        try:
            result = _screen_one(application_id)
        except Exception:  # noqa: BLE001 — 한 건의 오류가 나머지를 막지 않게
            logger.exception("이력서 AI 판정 실패: %s", application_id)
            result = "failed"
        counts[result] = counts.get(result, 0) + 1
    if ids:
        logger.info("이력서 AI 판정 배치: 대상 %d건 %s", len(ids), counts)
    return counts
