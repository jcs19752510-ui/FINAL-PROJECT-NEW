"""Celery 앱 설정 — Redis 브로커/백엔드 (03-system-design.md §1.3/§2.1, DEC-019).

**워커 기동 명령(운영 규칙, DEC-019 그대로 준수)**:
    celery -A app.services.celery_app worker --concurrency=1 --pool=solo -Q ai_pipeline

`--pool=solo --concurrency=1`이 필수인 이유는 DEC-019에 기록되어 있다(GPU/CUDA류
컨텍스트가 프로세스 fork와 호환되지 않는 문제가 잘 알려져 있어, 기본 `prefork` 풀을
쓰면 깨질 위험이 있음). 이 프로젝트는 Vulkan 백엔드(llm_engine.py)를 쓰지만 동일한
원칙을 그대로 적용한다 — 워커가 여러 개(또는 prefork로 여러 자식 프로세스) 뜨면
`llama-server` 서브프로세스가 포트(8091)/VRAM을 두고 서로 충돌한다.

**Celery beat 스케줄(2026-09-28, DEC-092, `app/worker/deletion_tasks.py`)**:
`delete_requested_data`/`purge_expired_data`는 위 AI 워커와 **별도의 프로세스**인
`celery -A app.services.celery_app beat`가 떠 있어야 실제로 주기 실행된다(beat는
스케줄만 트리거하고, 실제 태스크는 여전히 `-Q ai_pipeline` 워커가 소비 — 같은 큐를
공유해 GPU 워커와 리소스 경합 없음, 두 배치 모두 DB만 다룸).
"""
from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

# unit-7 재작업(DEF-010): 이 워커 프로세스는 `app.worker.tasks`가 직접 import하는
# 모델(Interview/Question/Transcript)만 메타데이터에 등록해왔다. `Interview.recruiter_id`
# 등 `users.id`를 가리키는 FK 문자열은 `users` 테이블이 `Base.metadata`에 등록되어
# 있어야 해석되는데, 이 워커는 그 테이블을 아무도 import하지 않아 `Interview`를
# 수정·flush하면 `NoReferencedTableError`가 발생한다(unit-7-test.md TC-042 실측,
# 현재 워커 태스크는 Interview를 수정하지 않아 미발현이지만 unit-10 리포트 job에서
# 발현될 잠복 결함). `alembic/env.py`와 동일한 원칙으로 모든 모델을 명시적으로
# import해 워커 프로세스에서도 전체 메타데이터가 항상 등록되게 한다.
from app.models.code_submission import CodeSubmission  # noqa: F401  # 메타데이터 등록을 위해 임포트 필요
from app.models.consent import Consent  # noqa: F401  # 메타데이터 등록을 위해 임포트 필요
from app.models.deletion_request import DeletionRequest  # noqa: F401  # 메타데이터 등록을 위해 임포트 필요
from app.models.evaluation_report import EvaluationReport  # noqa: F401  # 메타데이터 등록을 위해 임포트 필요
from app.models.interview import Interview  # noqa: F401  # 메타데이터 등록을 위해 임포트 필요
from app.models.question import Question  # noqa: F401  # 메타데이터 등록을 위해 임포트 필요
from app.models.resume_application import ResumeApplication  # noqa: F401  # 메타데이터 등록을 위해 임포트 필요
from app.models.rubric_template import RubricTemplate  # noqa: F401  # 메타데이터 등록을 위해 임포트 필요
from app.models.transcript import Transcript  # noqa: F401  # 메타데이터 등록을 위해 임포트 필요
from app.models.user import User  # noqa: F401  # 메타데이터 등록을 위해 임포트 필요
from app.models.whiteboard import WhiteboardSnapshot  # noqa: F401  # 메타데이터 등록을 위해 임포트 필요

celery_app = Celery(
    "ai_interview_worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks", "app.worker.deletion_tasks"],
)

celery_app.conf.update(
    task_default_queue="ai_pipeline",
    task_track_started=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        # REQ-030, 03-design §6.2: "매 시간 실행해 24시간 SLA에 충분한 여유를 둔다"
        "delete-requested-data-hourly": {
            "task": "app.worker.deletion_tasks.delete_requested_data",
            "schedule": crontab(minute=0),
        },
        # REQ-033, 03-design §6.2: "purge_expired_data 배치(Celery beat, 매일 1회)"
        "purge-expired-data-daily": {
            "task": "app.worker.deletion_tasks.purge_expired_data",
            "schedule": crontab(hour=3, minute=0),
        },
    },
)
