"""AI 파이프라인 큐 경계 인터페이스 (03-system-design.md §1.3/§4.2/§4.3).

**이 모듈은 아직 존재하지 않는 하위 컴포넌트(Celery+Redis 큐, AI Worker)에 대한
"정당한 순서상 스텁"이다.** 큐/워커 자체는 unit-4(WebSocket Gateway) 이후,
opening_question의 실제 LLM 처리는 unit-7(LLM), report_generation의 실제 처리는
unit-10(STAR 리포트)이 구축한다 — 이 유닛(unit-2)의 책임이 아니다.

unit-2가 지금 보장하는 것은 **API 응답 계약**뿐이다: `/start`와 `/end`는 설계서가
명시한 대로 즉시 `202 {job_id, ...}`를 반환해야 하므로(§1.3 "202 Accepted + job_id"
패턴), 이 함수들은 job_id를 즉시 발급해 그 계약을 충족시킨다. 실제 큐 연동을 구현할
때는 아래 두 함수의 **시그니처(입력 타입/반환 타입)를 유지한 채 내부 구현만 교체**하면
호출부(app/api/v1/interviews.py)를 변경할 필요가 없다.

이후 유닛이 실제로 구현해야 할 것 (인터페이스 경계):
- Redis에 job을 enqueue하고 Celery task id를 반환 (지금은 `uuid4()`로 대체)
- 큐 최대 길이(50, §1.3) 초과 시 `429 QUEUE_FULL`을 여기서 발생시켜야 함
- opening_question: AI Worker가 STT 단계 없이 LLM→TTS만 수행, 완료 후
  `TRANSCRIPTS(speaker=ai, turn_index=0)` 저장 + WS `turn_result` push (§4.3)
- report_generation: AI Worker가 전체 TRANSCRIPTS를 컨텍스트로 리포트 LLM 호출,
  완료 후 `EVALUATION_REPORTS` 생성 + `INTERVIEWS.report_status`를 ready/failed로
  갱신 + WS `report_ready` push (§4.2/§4.4/§5.4)
"""
import uuid


def enqueue_opening_question_job(interview_id: uuid.UUID) -> str:
    """`POST /interviews/{id}/start` 성공 직후 호출 (DEC-024 갭8, §4.3).

    스텁: 실제 큐/워커가 없으므로 job_id만 발급한다. 실제 연동 전까지는 이 job이
    처리되어 WS `turn_result`가 도착하는 일은 없다 — 이는 unit-2가 아니라
    unit-4/unit-7 범위임을 unit-2-note.md에 명시한다.
    """
    return str(uuid.uuid4())


def enqueue_report_generation_job(interview_id: uuid.UUID) -> str:
    """`POST /interviews/{id}/end` 성공 직후 호출 (§4.2, §4.4).

    스텁: 실제 큐/워커가 없으므로 job_id만 발급한다. `INTERVIEWS.report_status`는
    호출부가 `queued`로 설정하지만, 이를 `ready`/`failed`로 전이시키는 실제 워커
    로직은 unit-10 범위다.
    """
    return str(uuid.uuid4())


def enqueue_turn_job(interview_id: uuid.UUID, transcript_id: uuid.UUID) -> str:
    """`POST /interviews/{id}/turns` 텍스트 제출 성공 직후 호출 (unit-4, REQ-003, §4.2/§4.3).

    **스텁 경계(unit-4가 실제로 보장하는 것과 보장하지 않는 것)**: 사용자의 텍스트
    답변은 이 함수 호출 전에 이미 `TRANSCRIPTS`(speaker=user)에 커밋되어 영구
    저장된다 — 이는 실제로 동작한다. 이 함수는 그 뒤 `202 {job_id}` 계약을 충족시키기
    위해 job_id만 발급하며, 실제 Redis enqueue/큐 길이(50) 초과 시 `429 QUEUE_FULL`
    발생/AI Worker의 LLM 꼬리질문 생성은 전혀 수행하지 않는다.

    따라서 이 job에 대해 WebSocket(`/ws/interviews/{id}`)으로 `queue_status`→
    `stage_update`→`turn_result`가 순서대로 push되는 일은 **이 유닛에서는 발생하지
    않는다** — 그 파이프라인은 unit-7(LLM)이 실제 AI Worker를 구현해야 채워지는
    부분이다. `app/api/v1/ws.py`의 `ConnectionManager.broadcast()`가 그 워커가 호출할
    푸시 인터페이스이며, 시그니처(`interview_id, message: dict`)는 이미 §4.3 이벤트
    스키마 그대로 고정해두었으니 워커 구현 시 호출부만 추가하면 된다.
    """
    return str(uuid.uuid4())
