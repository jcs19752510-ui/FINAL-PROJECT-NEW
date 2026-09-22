"""AI 파이프라인 큐 경계 인터페이스 (03-system-design.md §1.3/§4.2/§4.3).

**unit-7(REQ-007)에서 실제 큐/워커 연동으로 전환됨.** `enqueue_opening_question_job`/
`enqueue_turn_job`은 이제 Celery(Redis 브로커, DEC-019)에 실제 태스크를 전송하고,
반환값은 uuid4 더미가 아니라 **실제 Celery task id**다. 처리 주체는
`app/worker/tasks.py`(`celery -A app.services.celery_app worker --concurrency=1
--pool=solo -Q ai_pipeline`로 기동되는 별도 프로세스)이며, 진행상황/결과는 Redis
Pub/Sub(`app/services/ws_publisher.py`) → `app/api/v1/ws.py`의 `redis_relay_loop`을
거쳐 WebSocket으로 push된다(§4.3 `stage_update`/`turn_result`).

**Feature E(리포트 생성, REQ-009/010/012) 추가로 `enqueue_report_generation_job`도
실제 Celery 전송으로 전환됨** — `app/worker/tasks.py::process_report_generation_job`
참고.

**큐 최대 길이(50, §1.3) 초과 시 `429 QUEUE_FULL`을 반환하는 로직은 아직 없다** —
이는 REQ-038(레이트리밋, unit-8)과 겹치는 영역이라 이번 유닛에서 임의로 구현하지
않고 그대로 인수인계한다(범위 외 확장 금지).

**unit-7 재작업(DEF-008/DEC-035 Q3)**: job을 enqueue한 직후 `job_watchdog.register_job()`으로
Redis에 감시 항목을 남긴다 — 처리 중 워커가 죽어 job이 영구 유실돼도(TC-014) 클라이언트가
`app/services/job_watchdog.py`가 대신 발행하는 `error` 이벤트를 받게 하기 위함이다.
"""
import uuid

from app.services.celery_app import celery_app
from app.services.job_watchdog import register_job


def enqueue_opening_question_job(interview_id: uuid.UUID) -> str:
    """`POST /interviews/{id}/start` 성공 직후 호출 (DEC-024 갭8, §4.3).

    `app.worker.tasks.process_opening_question_job`을 Celery로 실제 전송한다.
    """
    result = celery_app.send_task(
        "app.worker.tasks.process_opening_question_job",
        args=[str(interview_id)],
    )
    register_job(interview_id, result.id)
    return result.id


def enqueue_report_generation_job(interview_id: uuid.UUID) -> str:
    """`POST /interviews/{id}/end`(및 `/report/regenerate`) 성공 직후 호출 (§4.2, §4.4).

    Feature E(리포트 생성): `app.worker.tasks.process_report_generation_job`을
    Celery로 실제 전송한다 — 전체 대화 맥락 요약 LLM 호출 → `EVALUATION_REPORTS`
    저장 → `INTERVIEWS.report_status` ready/failed 전이까지 그 태스크가 수행한다.
    """
    result = celery_app.send_task(
        "app.worker.tasks.process_report_generation_job",
        args=[str(interview_id)],
    )
    register_job(interview_id, result.id)
    return result.id


def enqueue_turn_job(interview_id: uuid.UUID, transcript_id: uuid.UUID) -> str:
    """`POST /interviews/{id}/turns` 제출(텍스트/음성 공통) 성공 직후 호출
    (unit-4/5, REQ-003/004/005, §4.2/§4.3).

    사용자 답변은 이 함수 호출 전에 이미 `TRANSCRIPTS`(speaker=user)에 커밋되어
    있다. `app.worker.tasks.process_turn_job`을 Celery로 실제 전송하며, 그
    태스크가 RAG 검색 → LLM 꼬리질문 생성 → TTS 합성 → `TRANSCRIPTS`(speaker=ai)
    저장 → WS `stage_update`/`turn_result` push를 전부 실제로 수행한다(unit-7).
    """
    result = celery_app.send_task(
        "app.worker.tasks.process_turn_job",
        args=[str(interview_id), str(transcript_id)],
    )
    register_job(interview_id, result.id)
    return result.id
