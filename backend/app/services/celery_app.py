"""Celery 앱 설정 — Redis 브로커/백엔드 (03-system-design.md §1.3/§2.1, DEC-019).

**워커 기동 명령(운영 규칙, DEC-019 그대로 준수)**:
    celery -A app.services.celery_app worker --concurrency=1 --pool=solo -Q ai_pipeline

`--pool=solo --concurrency=1`이 필수인 이유는 DEC-019에 기록되어 있다(GPU/CUDA류
컨텍스트가 프로세스 fork와 호환되지 않는 문제가 잘 알려져 있어, 기본 `prefork` 풀을
쓰면 깨질 위험이 있음). 이 프로젝트는 Vulkan 백엔드(llm_engine.py)를 쓰지만 동일한
원칙을 그대로 적용한다 — 워커가 여러 개(또는 prefork로 여러 자식 프로세스) 뜨면
`llama-server` 서브프로세스가 포트(8091)/VRAM을 두고 서로 충돌한다.
"""
from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "ai_interview_worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_default_queue="ai_pipeline",
    task_track_started=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)
