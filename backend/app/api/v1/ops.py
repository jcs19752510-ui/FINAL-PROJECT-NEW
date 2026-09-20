"""REQ-016: 운영자 기본 모니터링 (03-system-design.md §4.2 `GET /ops/health`, §7.2 지표).

범위(unit-18, Feature H): `GET /api/v1/ops/health` — admin 역할 전용
(04-ux-design.md [O-01] "관리자 역할로 로그인" — recruiter는 별도 [R-01] 리포트 열람
화면을 쓰므로 이 화면의 대상이 아니다).

**실측 가능/불가능 경계 (가짜 데이터로 채우지 않음)**: 이 시점에 실제로 존재하는
하위 시스템은 INTERVIEWS 테이블뿐이다. Celery/Redis 큐(`app/services/job_queue.py`는
job_id만 발급하는 정당한 순서상 스텁, unit-4/7/10이 실제 큐를 구축할 예정), GPU AI
Worker(unit-6/7), Prometheus 메트릭 수집(03-design §7.2, 이 코드베이스에는 아직 도입되지
않음)이 모두 미구축이므로:
- `active_sessions`: `INTERVIEWS.status='live'` 카운트 — DB로 실측 가능하므로 실제 값.
- `queue_length` / `gpu_memory_used_bytes` / `error_rate`: 근거 시스템이 없어 상시 0(0.0).
각 필드가 실측인지 스텁인지는 응답의 `notes`에 명시해, 03-design §7.2의 "낡은/부재
데이터라도 정직하게 보이는 것이 숨기는 것보다 낫다" 원칙을 지킨다.
"""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.errors import AppError
from app.db.session import get_db
from app.models.interview import Interview, InterviewStatus
from app.models.user import User, UserRole
from app.schemas.ops import OpsHealthOut

router = APIRouter(prefix="/ops", tags=["ops"])


@router.get("/health", response_model=OpsHealthOut)
def get_ops_health(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OpsHealthOut:
    if current_user.role != UserRole.admin:
        raise AppError(403, "AUTH_FORBIDDEN", "Forbidden", "관리자(admin)만 접근할 수 있습니다.")

    active_sessions = (
        db.scalar(select(func.count()).select_from(Interview).where(Interview.status == InterviewStatus.live))
        or 0
    )

    return OpsHealthOut(
        queue_length=0,
        gpu_memory_used_bytes=0,
        error_rate=0.0,
        active_sessions=active_sessions,
        checked_at=datetime.now(UTC),
        notes={
            "queue_length": "실제 큐(Celery/Redis) 미구축 — job_queue.py는 job_id 발급 스텁만 존재"
            "(unit-4/7/10 예정). 항상 0.",
            "gpu_memory_used_bytes": "GPU AI Worker 미구축 — 측정 불가. 항상 0.",
            "error_rate": "Prometheus/로그 집계 파이프라인 미구축(03-design §7.2) — 측정 불가. 항상 0.0.",
            "active_sessions": "INTERVIEWS.status='live' 실측값.",
        },
    )
