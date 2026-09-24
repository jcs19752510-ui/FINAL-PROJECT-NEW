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
from app.api.v1.webcam_emotion import router as webcam_emotion_router
from app.api.v1.webrtc_signaling import router as webrtc_signaling_router
from app.api.v1.whiteboard import router as whiteboard_router
from app.api.v1.ws import redis_relay_loop
from app.api.v1.ws import router as ws_router
from app.core.config import settings
from app.core.errors import AppError, app_error_handler, validation_error_handler
from app.services.job_watchdog import job_watchdog_loop
from app.services.prosody_engine import warmup as warmup_prosody_engine
from app.services.tts_engine import MEDIA_ROOT

app = FastAPI(title="AI 모의면접 플랫폼 API", version="0.1.0")

# unit-7(REQ-007): AI Worker(Celery, 별도 프로세스)가 Redis Pub/Sub으로 발행한
# §4.3 WS 이벤트를 이 API 프로세스의 ConnectionManager로 중계하는 백그라운드
# 태스크(app/api/v1/ws.py `redis_relay_loop` 참고).
_relay_task: asyncio.Task | None = None
# unit-7 재작업(DEF-008/DEC-035 Q3): 처리 중 워커 크래시로 유실된 job에 대한 실패
# 통지 감시 루프(app/services/job_watchdog.py 참고).
_watchdog_task: asyncio.Task | None = None
# unit-24(원안 REQ-018/019 축소판, Prosody 분석, 2026-09-22 사용자 승인): numba JIT
# 콜드 스타트 실측(최대 약 32초, app/services/prosody_engine.py warmup() docstring
# 참고)이 실사용자의 첫 음성 답변에 그대로 전가되지 않도록, 기동 직후 백그라운드에서
# 미리 한 번 호출해 예열한다. `run_in_executor`로 스레드풀에 위임해 서버 기동
# 자체(다른 라우트 응답성)를 막지 않는다.
_prosody_warmup_task: asyncio.Task | None = None


async def _run_prosody_warmup() -> None:
    # 2026-09-22 실측 결함: `loop.run_in_executor(...)`는 코루틴이 아니라 `Future`를
    # 반환해 `asyncio.create_task()`에 직접 넘기면 `TypeError: a coroutine was
    # expected`로 서버 기동 자체가 실패함을 확인(uvicorn 서버 프로세스로 직접
    # 재현). 코루틴으로 감싸 `await`해야 한다.
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, warmup_prosody_engine)


@app.on_event("startup")
async def _start_background_tasks() -> None:
    global _relay_task, _watchdog_task, _prosody_warmup_task
    _relay_task = asyncio.create_task(redis_relay_loop())
    _watchdog_task = asyncio.create_task(job_watchdog_loop())
    _prosody_warmup_task = asyncio.create_task(_run_prosody_warmup())


@app.on_event("shutdown")
async def _stop_background_tasks() -> None:
    if _relay_task is not None:
        _relay_task.cancel()
    if _watchdog_task is not None:
        _watchdog_task.cancel()
    if _prosody_warmup_task is not None:
        _prosody_warmup_task.cancel()

@app.middleware("http")
async def _security_headers_middleware(request, call_next):
    """unit-25(원안 REQ-N-001 축소판, 전송 시 TLS 1.3 암호화) — 2026-09-22 사용자
    승인. 이 애플리케이션 프로세스 자체는 TLS를 종단하지 않는다(03-design §6.4,
    `deploy/nginx.conf.sample` 참고) — 이 미들웨어는 nginx가 이미 TLS로 넘겨준
    뒤에도 앱 계층에서 한 번 더 방어선을 두는 역할이다(응답 헤더 삽입은 전송
    자체를 암호화하지 않으므로 TLS 종단을 대체하지 않는다).

    HSTS는 `settings.cookie_secure`(운영에서 True, 로컬 http 개발에서 False)를
    그대로 재사용해 로컬 http 개발 환경에는 보내지 않는다 — localhost에 HSTS를
    잘못 보내면 브라우저가 그 오리진을 영구히 HTTPS 전용으로 기억해버리는 부작용이
    있어(개발 편의성 실측 리스크), 이미 존재하는 같은 신호를 재사용해 별도
    환경변수를 늘리지 않았다(구현 세부값, 비가역성 낮음).
    """
    response = await call_next(request)
    if settings.cookie_secure:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


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
app.include_router(webcam_emotion_router, prefix="/api/v1")
app.include_router(whiteboard_router, prefix="/api/v1")
# 03-system-design.md §4.3: WebSocket 경로는 `/api/v1` 프리픽스 없이 `/ws/interviews/{id}`.
app.include_router(ws_router)
# unit-28(원안 §2.2 Signaling Server, 2026-09-22 사용자 승인): 기존 turn_result
# push 채널과 완전히 분리된 별도 경로(webrtc_signaling.py 모듈 docstring 참고).
app.include_router(webrtc_signaling_router)

# unit-6(REQ-006): §4.3 `turn_result.audio_url` 표기(`/media/xxx.wav`)와 동일한
# 경로 규칙으로, 합성된 음성 파일을 `/api/v1` 프리픽스 없이 정적 서빙한다.
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(MEDIA_ROOT)), name="media")


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
