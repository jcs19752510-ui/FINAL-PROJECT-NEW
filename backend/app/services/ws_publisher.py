"""AI Worker(Celery, 별도 OS 프로세스)가 WebSocket 이벤트(§4.3)를 API 프로세스에
전달하는 통로 (03-system-design.md §1.2 "AI Worker는 API 서버와 완전히 별도의
OS 프로세스로 분리한다").

`app/api/v1/ws.py`의 `ConnectionManager`는 API 프로세스의 인메모리 상태라 Worker
프로세스가 직접 호출할 수 없다. 대신 이미 도입된 Redis(Celery 브로커, DEC-019)의
Pub/Sub 채널(`ws:{interview_id}`)에 이벤트를 발행하고, API 프로세스가 시작 시
이 채널들을 구독해 자신의 `ConnectionManager.broadcast()`로 중계한다
(`app/main.py`의 시작 이벤트, `app/api/v1/ws.py`의 `redis_relay_loop` 참고).
"""
import json
import uuid

import redis

from app.core.config import settings

WS_CHANNEL_PREFIX = "ws:"


def publish_ws_event(interview_id: uuid.UUID | str, message: dict) -> None:
    """Redis 연결을 매 호출마다 새로 열고 닫는다 — Celery 태스크 호출 빈도(턴당
    수 회)에서는 연결 재사용 최적화가 필요할 만큼 빈번하지 않고(과설계 방지),
    워커 프로세스 하나가 장수명 커넥션을 계속 들고 있다가 Redis 재시작 시
    끊기는 경우를 대비하지 않아도 된다는 장점이 있다.
    """
    client = redis.Redis.from_url(settings.redis_url)
    try:
        client.publish(f"{WS_CHANNEL_PREFIX}{interview_id}", json.dumps(message, ensure_ascii=False))
    finally:
        client.close()
