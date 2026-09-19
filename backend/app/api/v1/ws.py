"""WebSocket 게이트웨이 `/ws/interviews/{interview_id}` (REQ-003, 03-system-design.md §4.3).

**설계서가 명시한 채널 역할 분리**: 턴 제출(요청)은 항상 REST
`POST /interviews/{id}/turns`(§4.2) 하나의 경로로만 이루어진다. 이 WebSocket은
오직 서버→클라이언트 단방향 진행상황 push 전용 채널이며, 턴 제출에는 사용하지
않는다. 클라이언트→서버로는 `cancel_queue_wait` 제어 신호 하나만 화이트리스트로
허용한다(§4.3).

**이 유닛(unit-4)의 스텁 경계**: 이 모듈은 연결 수립/인증/구독 관리와 메시지
스키마(§4.3 JSON 그대로)를 실제로 구현한다 — 즉 클라이언트가 실제로 연결하고,
`cancel_queue_wait`를 보내고, 연결이 유지되는 것은 전부 동작한다. 다만 실제로
`queue_status`/`stage_update`/`turn_result`를 이 채널로 push하는 주체(Redis
큐 소비자, AI Worker)는 아직 존재하지 않는다(unit-7 이후 범위, `job_queue.py`
참고) — 따라서 이 유닛에서는 어떤 이벤트도 실제로 도착하지 않는다. `manager.broadcast()`가
그 미래 워커가 호출할 유일한 진입점이며, 시그니처를 이미 고정해 두었다.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.core.security import JWTError, decode_token
from app.db.session import SessionLocal
from app.models.interview import Interview
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()

# 03-design §4.3 클라이언트→서버 화이트리스트 메시지 타입. 이 목록에 없는 타입은
# 무시한다(REQ-037과 동일한 화이트리스트 원칙 — 정의되지 않은 제어 신호를 임의
# 실행하지 않음).
_ALLOWED_CLIENT_MESSAGE_TYPES = {"cancel_queue_wait"}


class ConnectionManager:
    """단일 프로세스 전제(DEC-006/007)의 인메모리 연결 레지스트리.

    interview_id별로 연결된 WebSocket 집합을 보관한다. 여러 탭/기기에서 동시에
    같은 세션을 열람할 수 있으므로 다대다가 아닌 1(interview) : N(connection)으로
    관리한다.
    """

    def __init__(self) -> None:
        self._connections: dict[UUID, set[WebSocket]] = {}

    def add(self, interview_id: UUID, ws: WebSocket) -> None:
        self._connections.setdefault(interview_id, set()).add(ws)

    def remove(self, interview_id: UUID, ws: WebSocket) -> None:
        conns = self._connections.get(interview_id)
        if conns is None:
            return
        conns.discard(ws)
        if not conns:
            self._connections.pop(interview_id, None)

    async def broadcast(self, interview_id: UUID, message: dict) -> None:
        """§4.3 서버→클라이언트 이벤트 push. 미래의 AI Worker/큐 소비자가 호출할 진입점.

        이 유닛에서는 어떤 호출부도 이 메서드를 호출하지 않는다(스텁 경계, 모듈
        docstring 참고) — 인터페이스만 미리 고정해둔다.
        """
        for ws in list(self._connections.get(interview_id, ())):
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001 — 죽은 연결 하나가 나머지 push를 막지 않게 함
                logger.warning("WS broadcast 실패, 연결 제거: interview_id=%s", interview_id)
                self.remove(interview_id, ws)


manager = ConnectionManager()


def _authenticate(token: str, interview_id: UUID) -> bool:
    """토큰 검증 + 본인 소유 세션인지 확인. WS는 헤더 대신 쿼리 파라미터로 토큰을 받는다
    (브라우저 WebSocket API가 커스텀 Authorization 헤더를 지원하지 않으므로 §6.1 JWT를
    그대로 재사용하되 전달 방식만 REST와 다르게 함, 04-ux-design [C-06] WS 연결 전제).
    """
    try:
        payload = decode_token(token)
    except JWTError:
        return False
    if payload.get("type") != "access":
        return False
    user_id = payload.get("sub")
    if user_id is None:
        return False

    db = SessionLocal()
    try:
        user = db.get(User, UUID(user_id))
        if user is None or user.deleted_at is not None:
            return False
        interview = db.get(Interview, interview_id)
        if interview is None or interview.candidate_id != user.id:
            return False
        return True
    finally:
        db.close()


@router.websocket("/ws/interviews/{interview_id}")
async def interview_ws(websocket: WebSocket, interview_id: UUID, token: str = Query(...)) -> None:
    if not _authenticate(token, interview_id):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    manager.add(interview_id, websocket)
    try:
        while True:
            try:
                data = await websocket.receive_json()
            except ValueError:
                # 시스템 경계(클라이언트 입력) 검증 — JSON이 아닌 프레임은 연결을
                # 끊지 않고 무시한다(악의적/오동작 클라이언트가 세션을 강제 종료시키지
                # 못하게 함).
                continue
            msg_type = data.get("type") if isinstance(data, dict) else None
            if msg_type not in _ALLOWED_CLIENT_MESSAGE_TYPES:
                # 화이트리스트 외 메시지는 조용히 무시(연결은 유지) — §4.3 계약 위반이지만
                # 클라이언트 오동작으로 세션 전체가 끊기지 않게 함.
                continue
            # cancel_queue_wait: 실제 큐가 없어(스텁) 취소할 대상 job이 없다. 이 유닛은
            # 메시지 수신 자체만 구현하고 아무 동작도 하지 않는다(모듈 docstring 참고).
    except WebSocketDisconnect:
        pass
    finally:
        manager.remove(interview_id, websocket)
