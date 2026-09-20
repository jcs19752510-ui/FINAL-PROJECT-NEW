import asyncio

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.auth import router as auth_router
from app.api.v1.code_submissions import router as code_submissions_router
from app.api.v1.consents import router as consents_router
from app.api.v1.interviews import router as interviews_router
from app.api.v1.ops import router as ops_router
from app.api.v1.recruiter import router as recruiter_router
from app.api.v1.whiteboard import router as whiteboard_router
from app.api.v1.ws import redis_relay_loop
from app.api.v1.ws import router as ws_router
from app.core.config import settings
from app.core.errors import AppError, app_error_handler, validation_error_handler
from app.services.job_watchdog import job_watchdog_loop
from app.services.tts_engine import MEDIA_ROOT

app = FastAPI(title="AI 모의면접 플랫폼 API", version="0.1.0")

# unit-7(REQ-007): AI Worker(Celery, 별도 프로세스)가 Redis Pub/Sub으로 발행한
# §4.3 WS 이벤트를 이 API 프로세스의 ConnectionManager로 중계하는 백그라운드
# 태스크(app/api/v1/ws.py `redis_relay_loop` 참고).
_relay_task: asyncio.Task | None = None
# unit-7 재작업(DEF-008/DEC-035 Q3): 처리 중 워커 크래시로 유실된 job에 대한 실패
# 통지 감시 루프(app/services/job_watchdog.py 참고).
_watchdog_task: asyncio.Task | None = None


@app.on_event("startup")
async def _start_background_tasks() -> None:
    global _relay_task, _watchdog_task
    _relay_task = asyncio.create_task(redis_relay_loop())
    _watchdog_task = asyncio.create_task(job_watchdog_loop())


@app.on_event("shutdown")
async def _stop_background_tasks() -> None:
    if _relay_task is not None:
        _relay_task.cancel()
    if _watchdog_task is not None:
        _watchdog_task.cancel()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(code_submissions_router, prefix="/api/v1")
app.include_router(consents_router, prefix="/api/v1")
app.include_router(interviews_router, prefix="/api/v1")
app.include_router(ops_router, prefix="/api/v1")
app.include_router(recruiter_router, prefix="/api/v1")
app.include_router(whiteboard_router, prefix="/api/v1")
# 03-system-design.md §4.3: WebSocket 경로는 `/api/v1` 프리픽스 없이 `/ws/interviews/{id}`.
app.include_router(ws_router)

# unit-6(REQ-006): §4.3 `turn_result.audio_url` 표기(`/media/xxx.wav`)와 동일한
# 경로 규칙으로, 합성된 음성 파일을 `/api/v1` 프리픽스 없이 정적 서빙한다.
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(MEDIA_ROOT)), name="media")


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
