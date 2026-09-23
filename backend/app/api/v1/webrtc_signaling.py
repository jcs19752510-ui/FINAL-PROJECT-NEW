"""WebRTC 시그널링 게이트웨이 `/ws/interviews/{interview_id}/signaling`
(원안 §2.2 Signaling Server, unit-28, 2026-09-22 사용자 승인).

**이 모듈의 정직한 범위**: SDP(offer/answer)와 ICE candidate를 두 피어(peer)
사이에서 그대로 중계(relay)하는 시그널링 서버만 구현한다. 실제 미디어(오디오/
비디오 RTP 스트림) 처리는 별도의 미디어 서버(원안 §4.1 "Media Server", aiortc/
GStreamer)가 담당해야 하며 **이 유닛은 그것을 구현하지 않는다** — 이 환경에
브라우저 테스트 도구가 없어 실제 카메라/마이크 스트림을 실측 검증할 방법이
없고, 미디어 서버는 그 자체로 별도의 "대" 규모 작업이다(③ 매트릭스 근거 그대로).
이 모듈이 증명하는 것은 "시그널링 교환 메커니즘 자체가 이 백엔드에서 실제로
동작한다"는 것뿐이다 — 두 WebSocket 피어 간 메시지 중계를 실측으로 검증한다
(unit-28-test.md 참고).

**기존 `app/api/v1/ws.py`와의 관계**: 그 모듈은 "서버→클라이언트 단방향 push
전용"이라는 §4.3 설계 결정을 명시적으로 고수한다. 시그널링은 본질적으로
양방향(피어 간 중계)이라 그 계약을 건드리지 않기 위해 **완전히 별도의 WS
경로**로 분리했다 — 기존 turn_result/stage_update 등 다른 유닛들이 의존하는
채널은 이 유닛으로 인해 전혀 변경되지 않는다.

**오늘(2026-09-22) 실측된 장애 패턴 재발 방지**: `ws.py`의 `_authenticate`
호출부 주석("장애 대응")이 남긴 교훈을 그대로 따른다 — 동기 DB 인증 호출을
`run_in_threadpool`로 위임하지 않으면 이벤트 루프가 멈춰 백엔드 전체가
응답불능이 된다. 이 모듈은 `ws.py`의 `_authenticate`를 재사용해 같은 결함을
다시 만들지 않는다(그 함수를 복제하지 않음).
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from starlette.concurrency import run_in_threadpool

from app.api.v1.ws import _authenticate  # 의도적 재사용, 모듈 docstring 참고

logger = logging.getLogger(__name__)

router = APIRouter()

# 시그널링 메시지 자체(SDP offer/answer, ICE candidate)의 내부 구조는 이 서버가
# 해석하지 않는다(불투명 릴레이) — WebRTC 표준 메시지 포맷을 서버가 파싱/검증할
# 필요가 없다는 것이 시그널링 서버의 일반적 설계(그대로 전달만). 다만 완전히
# 임의의 페이로드가 무한정 릴레이되는 것은 막기 위해 최상위 타입 필드만
# 화이트리스트로 제한한다(REQ-037과 동일한 최소권한 원칙).
_ALLOWED_SIGNAL_TYPES = {"offer", "answer", "ice-candidate", "bye"}

# interview_id당 최대 2피어(1:1 시그널링 — 그룹 통화 아님, 원안 범위와 일치).
_MAX_PEERS_PER_ROOM = 2


class SignalingRoomManager:
    """interview_id별로 최대 2개 WebSocket 연결을 묶어, 한쪽이 보낸 메시지를
    다른 쪽에게 그대로 전달한다(불투명 릴레이 — 메시지 내용을 이해하지 않음).
    """

    def __init__(self) -> None:
        self._rooms: dict[UUID, list[WebSocket]] = {}

    def join(self, interview_id: UUID, ws: WebSocket) -> bool:
        peers = self._rooms.setdefault(interview_id, [])
        if len(peers) >= _MAX_PEERS_PER_ROOM:
            return False
        peers.append(ws)
        return True

    def leave(self, interview_id: UUID, ws: WebSocket) -> None:
        peers = self._rooms.get(interview_id)
        if peers is None:
            return
        if ws in peers:
            peers.remove(ws)
        if not peers:
            self._rooms.pop(interview_id, None)

    async def relay(self, interview_id: UUID, sender: WebSocket, message: dict) -> None:
        peers = self._rooms.get(interview_id, [])
        for peer in peers:
            if peer is sender:
                continue
            try:
                await peer.send_json(message)
            except Exception:  # noqa: BLE001 — 상대 피어 전송 실패가 이 커넥션을 죽이지 않게 함
                logger.warning("시그널링 중계 실패: interview_id=%s", interview_id)


manager = SignalingRoomManager()


@router.websocket("/ws/interviews/{interview_id}/signaling")
async def webrtc_signaling(websocket: WebSocket, interview_id: UUID, token: str = Query(...)) -> None:
    if not await run_in_threadpool(_authenticate, token, interview_id):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    if not manager.join(interview_id, websocket):
        # 이미 2피어가 연결된 방 — 3번째 연결은 거부(1:1 시그널링 범위 밖).
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="signaling room full")
        return

    try:
        while True:
            try:
                data = await websocket.receive_json()
            except ValueError:
                continue
            if not isinstance(data, dict) or data.get("type") not in _ALLOWED_SIGNAL_TYPES:
                continue
            await manager.relay(interview_id, websocket, data)
    except WebSocketDisconnect:
        pass
    finally:
        manager.leave(interview_id, websocket)
