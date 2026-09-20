"""(interview_id, turn_index) 원자적 채번 (unit-7 재작업, DEF-002/DEC-035 Q5).

오프닝 AI 턴(과거 `turn_index=0` 하드코딩)과 사용자/AI 턴(건수 기반 채번, `COUNT(*)`)이
서로 다른 방식으로 번호를 매겨, 오프닝 완료 전 사용자가 답변을 제출하면 turn_index가
중복되는 결함이 실측으로 확인됐다(unit-7-test.md TC-030). 이제 API 프로세스
(`app/api/v1/interviews.py`)와 Celery 워커 프로세스(`app/worker/tasks.py`) 양쪽 모두
이 모듈의 `insert_transcript_with_retry()`를 거쳐서만 `Transcript`를 생성한다.

**"완전한 분산 락" 대신 "MAX+1 계산 + DB 유니크 제약(Alembic f2a9c4d81e36) +
IntegrityError 재시도"를 택한 이유**: 사용자 턴(API 프로세스)과 AI 턴(워커 프로세스)이
서로 다른 DB 세션/트랜잭션을 쓰기 때문에, 아직 존재하지 않는 미래의 turn_index 값에
대한 경쟁은 `SELECT ... FOR UPDATE`(행이 없으면 잠글 대상이 없음)나 애플리케이션
레벨 락만으로 막을 수 없다. DB 유니크 제약이 최종 방어선이고, 이 재시도 로직은 그
방어선에 걸렸을 때 사용자에게 에러를 노출하는 대신 번호를 다시 계산해 자연스럽게
이어가기 위한 것이다.
"""
import logging
import uuid
from collections.abc import Callable

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.transcript import Transcript

logger = logging.getLogger(__name__)

_MAX_RETRIES = 5


def _next_turn_index(db: Session, interview_id: uuid.UUID) -> int:
    current_max = db.scalar(
        select(func.max(Transcript.turn_index)).where(Transcript.interview_id == interview_id)
    )
    return 0 if current_max is None else current_max + 1


def insert_transcript_with_retry(
    db: Session, interview_id: uuid.UUID, build: Callable[[int], Transcript]
) -> Transcript:
    """`build(turn_index)`가 만든 `Transcript`를 삽입한다.

    유니크 제약(`interview_id`, `turn_index`) 위반 시(동시 요청 경쟁) 다음 번호를
    다시 계산해 최대 `_MAX_RETRIES`회 재시도한다. 호출부는 이미 `db.add`/`db.commit`을
    직접 호출하지 않아야 한다 — 이 함수가 그 책임을 갖는다.
    """
    last_error: IntegrityError | None = None
    for attempt in range(_MAX_RETRIES):
        turn_index = _next_turn_index(db, interview_id)
        transcript = build(turn_index)
        db.add(transcript)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            last_error = exc
            logger.warning(
                "turn_index 충돌(시도 %d/%d) interview_id=%s turn_index=%d — 재시도",
                attempt + 1,
                _MAX_RETRIES,
                interview_id,
                turn_index,
            )
            continue
        db.refresh(transcript)
        return transcript
    raise RuntimeError(
        f"turn_index 배정에 반복적으로 실패했습니다: interview_id={interview_id}"
    ) from last_error
