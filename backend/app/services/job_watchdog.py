"""처리 중 워커 크래시로 유실된 job에 대한 실패 통지 (unit-7 재작업, DEF-008/DEC-035 Q3).

**DEC-035 Q3 채택안 "실패 통지(단순)"**: LLM 단계 처리 중 워커 프로세스가 죽으면
Celery 기본 설정(`task_acks_late=False`)상 메시지는 이미 ack되어 재전달되지 않고,
그 job은 영구히 유실된다(unit-7-test.md TC-014 실측 — 워커 재기동 후에도 해당 job
이벤트가 다시 오지 않음). `acks_late`+멱등 재처리(중복 응답 위험, 복잡도)는 기각됐다
(DEC-035) — 대신 워커가 스스로 하지 못하는 실패 통지(프로세스가 죽어 코드를 실행할
수 없으므로)를 API 프로세스가 대신 감시해서 대체한다.

동작 방식: `app/services/job_queue.py`가 job을 enqueue한 직후 `register_job()`으로
Redis에 `job_watch:{job_id}` 키(TTL 있음, 자동 소멸)를 남긴다. `job_watchdog_loop()`
(`app/main.py` startup에서 `redis_relay_loop`과 함께 기동)가 주기적으로 그 키들을
스캔해 Celery task 상태(`AsyncResult.state`)를 확인한다:
  - PENDING(아직 워커가 못 받음): 그대로 둔다 — 워커가 꺼져 있어 대기 중인 정상
    상황(AC5)과 구분하지 않으면 오탐이 생긴다.
  - STARTED: 최초로 STARTED를 관측한 시각을 기록해두고, 그로부터
    `_STARTED_TIMEOUT_SECONDS`가 지나도 SUCCESS/FAILURE로 전이하지 않으면 처리 중
    유실로 간주해 WS `error` 이벤트를 발행한다(§4.3 이벤트 스키마 그대로).
  - SUCCESS/FAILURE: 이미 태스크 자신이 `turn_result`/`error`를 발행했으므로 감시
    키만 정리한다(중복 알림 방지).

이 감시는 순수 부가 기능이다 — 태스크가 정상적으로 끝나는 경로는 전혀 건드리지
않으며, 지연이 발생해도(예: 최대 관찰 주기) 정상 이벤트 전달을 막지 않는다.
"""
import asyncio
import json
import logging
import time
import uuid

import redis
import redis.asyncio as aioredis
from celery.result import AsyncResult

from app.core.config import settings
from app.services.celery_app import celery_app
from app.services.ws_publisher import publish_ws_event

logger = logging.getLogger(__name__)

_WATCH_KEY_PREFIX = "job_watch:"
# PENDING(워커 다운으로 대기 중, AC5 정상 시나리오) 상태의 job도 이 시간이 지나면
# 감시를 그만둔다 — Redis TTL로 키가 자동 소멸해 무한히 스캔 대상이 늘어나지 않게
# 한다. 이 시점 이후 워커가 늦게 살아나 처리해도 turn_result는 정상 도착한다
# (감시가 끊길 뿐 태스크 자체의 동작과는 무관).
_WATCH_KEY_TTL_SECONDS = 600
# 콜드스타트(llama-server 기동 최대 60s) + LLM 생성 재시도(최대 2회 x 25s) + TTS(10s)
# 최악 시나리오(약 120초)를 넉넉히 초과하는 값으로, 정상 처리 중인 job을 실패로
# 오탐하지 않도록 여유를 둔다(DEC-035 Q3 "단순 실패 통지" 취지 — 오탐보다 지연을
# 택함).
_STARTED_TIMEOUT_SECONDS = 150
_POLL_INTERVAL_SECONDS = 5

# v15(03-system-design v4 §4.6 (3) "작업 감시도 작업 종류별로", unit-37 2차 검증에서
# 발견): 리포트 job은 턴 job보다 LLM 제한시간이 훨씬 길다(settings.
# llm_report_timeout_seconds, 기본 300초 vs 턴의 25초). 감시 타임아웃이 턴 기준
# 150초로 고정돼 있으면, 정상 진행 중인 리포트 job도 150초를 넘기는 순간 "유실"로
# 오판해 WS `error`를 잘못 보낸다(report_status는 여전히 queued인데 사용자에게는
# 실패로 보임) — 실측 없이 코드 리뷰로 발견해 즉시 수정.
_REPORT_TIMEOUT_MARGIN_SECONDS = 60


def _report_watch_timeout() -> int:
    return settings.llm_report_timeout_seconds + _REPORT_TIMEOUT_MARGIN_SECONDS


def register_job(interview_id: uuid.UUID | str, job_id: str, *, timeout_seconds: int | None = None) -> None:
    """`job_queue.py`가 enqueue 직후 호출한다. `timeout_seconds`를 생략하면 턴/오프닝
    기준 기본값(`_STARTED_TIMEOUT_SECONDS`)을 쓴다 — 리포트 job은
    `enqueue_report_generation_job`이 `_report_watch_timeout()`을 명시적으로 넘긴다.
    """
    client = redis.Redis.from_url(settings.redis_url)
    try:
        client.set(
            f"{_WATCH_KEY_PREFIX}{job_id}",
            json.dumps({
                "interview_id": str(interview_id),
                "started_seen_at": None,
                "timeout_seconds": timeout_seconds if timeout_seconds is not None else _STARTED_TIMEOUT_SECONDS,
            }),
            ex=max(_WATCH_KEY_TTL_SECONDS, (timeout_seconds or 0) + _POLL_INTERVAL_SECONDS * 2),
        )
    finally:
        client.close()


async def _check_job(client: aioredis.Redis, key: bytes | str) -> None:
    key_str = key.decode() if isinstance(key, bytes) else key
    job_id = key_str[len(_WATCH_KEY_PREFIX):]

    raw = await client.get(key_str)
    if raw is None:
        return
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        await client.delete(key_str)
        return

    state = AsyncResult(job_id, app=celery_app).state

    if state in ("SUCCESS", "FAILURE"):
        await client.delete(key_str)
        return

    if state != "STARTED":
        # PENDING/RETRY 등 — 아직 워커가 못 받았거나 대기 중(AC5). 타임아웃 미적용.
        return

    timeout_seconds = data.get("timeout_seconds", _STARTED_TIMEOUT_SECONDS)

    now = time.time()
    if data.get("started_seen_at") is None:
        data["started_seen_at"] = now
        await client.set(
            key_str, json.dumps(data), ex=max(_WATCH_KEY_TTL_SECONDS, timeout_seconds + _POLL_INTERVAL_SECONDS * 2)
        )
        return

    if now - data["started_seen_at"] > timeout_seconds:
        logger.warning(
            "job 처리 중 유실 감지(STARTED 후 %.0fs 무응답, 기준 %ds) — 실패 통지: job_id=%s",
            now - data["started_seen_at"],
            timeout_seconds,
            job_id,
        )
        publish_ws_event(
            data["interview_id"],
            {
                "type": "error",
                "job_id": job_id,
                "code": "AI_SERVICE_TIMEOUT",
                "message": "AI 응답 처리가 중단되어 완료되지 못했습니다. 다시 시도해 주세요.",
            },
        )
        await client.delete(key_str)


async def job_watchdog_loop() -> None:
    """`app/main.py` startup에서 백그라운드 태스크로 기동, shutdown에서 취소된다.

    이 루프 자체의 예외(Redis 순간 단절 등)가 API 서버 전체를 죽이지 않도록
    바깥에서 재시도한다(`redis_relay_loop`과 동일 원칙, §1.2 장애격리).
    """
    while True:
        try:
            client = aioredis.from_url(settings.redis_url)
            try:
                async for key in client.scan_iter(match=f"{_WATCH_KEY_PREFIX}*"):
                    await _check_job(client, key)
            finally:
                await client.close()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — Redis 순간 단절 등, 서버 전체를 죽이지 않고 재시도
            logger.warning("job_watchdog_loop 예외 발생, 재시도", exc_info=True)
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
