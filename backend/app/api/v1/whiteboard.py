"""REQ-017 (Feature H, unit-17): 화이트보드 캔버스 스냅샷 저장/조회
(03-system-design.md v2 §3, §4.2, 04-ux-design.md v2 [C-08]).

DEC-008: AI가 화이트보드를 시각적으로 분석하는 기능은 원래 Out-of-Scope(REQ-021)
였으나, 2026-09-23 사용자 승인으로 unit-35가 이를 뒤집어 `POST
.../whiteboard/analyze`를 추가했다(로컬 SmolVLM, 무료 — 유료 GPT-4V는 계속
미사용). 저장/조회(PUT/GET) 두 엔드포인트는 여전히 순수 드로잉 데이터만 다룬다.

`interviews.py`(면접 세션 상태머신, unit-2/3/4 소유)는 건드리지 않는다 — 소유권
검증(`_get_own_interview`와 동일한 로직)을 이 파일 안에 그대로 재구현해 다른
유닛의 파일을 import/수정하지 않고 독립적으로 유지한다(unit-14 `consents.py`의
선례를 그대로 따름).
"""
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.errors import AppError
from app.db.session import get_db
from app.models.interview import Interview
from app.models.user import User
from app.models.whiteboard import WhiteboardSnapshot
from app.schemas.whiteboard import WhiteboardAnalysisOut, WhiteboardSaveRequest, WhiteboardSnapshotOut
from app.services.whiteboard_vision import (
    LOW_CONFIDENCE_DISCLAIMER,
    VisionAnalysisError,
    WhiteboardRenderError,
    analyze_diagram_local,
    render_strokes_to_png,
)

router = APIRouter(prefix="/interviews", tags=["whiteboard"])


def _get_own_interview(interview_id: UUID, current_user: User, db: Session) -> Interview:
    """`interviews.py`의 동명 헬퍼와 동일한 규칙(본인 소유 세션만 접근 가능)을
    독립적으로 재구현한다 — 파일 경계를 넘는 import로 인한 병렬 작업 충돌을 피하기
    위함(위 모듈 docstring 참고)."""
    interview = db.get(Interview, interview_id)
    if interview is None:
        raise AppError(404, "NOT_FOUND", "Not Found", "면접 세션을 찾을 수 없습니다.")
    if interview.candidate_id != current_user.id:
        raise AppError(403, "AUTH_FORBIDDEN", "Forbidden", "본인의 면접 세션만 조작할 수 있습니다.")
    return interview


def _to_out(snapshot: WhiteboardSnapshot) -> WhiteboardSnapshotOut:
    strokes = snapshot.canvas_json.get("strokes", []) if isinstance(snapshot.canvas_json, dict) else []
    return WhiteboardSnapshotOut(
        id=snapshot.id,
        interview_id=snapshot.interview_id,
        strokes=strokes,
        created_at=snapshot.created_at,
    )


@router.put("/{interview_id}/whiteboard", response_model=WhiteboardSnapshotOut, status_code=status.HTTP_200_OK)
def save_whiteboard(
    interview_id: UUID,
    payload: WhiteboardSaveRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WhiteboardSnapshotOut:
    """화이트보드 캔버스 스냅샷 저장 (03-design §4.2 `PUT /interviews/{id}/whiteboard`).

    WHITEBOARD_SNAPSHOTS는 03-design ERD상 단일행 UPDATE 대상이 아니라 이력 테이블로
    설계되어 있으므로(모델 docstring 참고), 매 저장 요청마다 새 스냅샷 행을 추가하고
    그 행을 응답으로 반환한다. 조회(GET)는 항상 가장 최근 행을 "현재 캔버스"로 취급한다.
    """
    interview = _get_own_interview(interview_id, current_user, db)

    snapshot = WhiteboardSnapshot(
        interview_id=interview.id,
        canvas_json={"strokes": [stroke.model_dump() for stroke in payload.strokes]},
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return _to_out(snapshot)


@router.get("/{interview_id}/whiteboard", response_model=WhiteboardSnapshotOut | None, status_code=status.HTTP_200_OK)
def get_whiteboard(
    interview_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WhiteboardSnapshotOut | None:
    """(03-design v2 §4.2 신규, DEC-024 갭4) 화이트보드 최신 스냅샷 재조회 —
    세션 재개([C-12]/[C-08]) 시 이전 캔버스를 복원하는 데 사용한다.

    아직 한 번도 저장한 적이 없으면(빈 캔버스) 200과 함께 `null`을 반환한다 — 404로
    취급하지 않는다(04-ux-design [C-08] "빈 상태"는 정상 상태이지 에러가 아님).
    """
    interview = _get_own_interview(interview_id, current_user, db)

    stmt = (
        select(WhiteboardSnapshot)
        .where(WhiteboardSnapshot.interview_id == interview.id)
        .order_by(WhiteboardSnapshot.created_at.desc())
        .limit(1)
    )
    snapshot = db.scalar(stmt)
    if snapshot is None:
        return None
    return _to_out(snapshot)


@router.post(
    "/{interview_id}/whiteboard/analyze", response_model=WhiteboardAnalysisOut, status_code=status.HTTP_200_OK
)
def analyze_whiteboard(
    interview_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WhiteboardAnalysisOut:
    """unit-35(REQ-021 부분 재도입, 2026-09-23 사용자 승인): 최신 저장 스냅샷을
    PNG로 렌더링한 뒤 로컬 SmolVLM(무료)에 보내 설명을 받는다.

    저장된 스냅샷이 없으면 404(빈 캔버스는 "저장 안 됨"과 구분되는 별개 상태 —
    GET과 달리 분석할 대상 자체가 없으므로 여기서는 null이 아니라 에러가 맞다).
    렌더링/모델 호출 실패는 04-design §5.4 관례대로 504(AI_SERVICE_TIMEOUT)로
    매핑한다(stt_engine.py 등과 동일 원칙).
    """
    interview = _get_own_interview(interview_id, current_user, db)

    stmt = (
        select(WhiteboardSnapshot)
        .where(WhiteboardSnapshot.interview_id == interview.id)
        .order_by(WhiteboardSnapshot.created_at.desc())
        .limit(1)
    )
    snapshot = db.scalar(stmt)
    if snapshot is None:
        raise AppError(404, "NOT_FOUND", "Not Found", "분석할 화이트보드 캔버스가 아직 저장되지 않았습니다.")

    strokes = snapshot.canvas_json.get("strokes", []) if isinstance(snapshot.canvas_json, dict) else []
    try:
        png_bytes = render_strokes_to_png(strokes)
        analysis = analyze_diagram_local(png_bytes)
    except (WhiteboardRenderError, VisionAnalysisError) as exc:
        raise AppError(504, "AI_SERVICE_TIMEOUT", "AI Service Timeout", "화이트보드 분석에 실패했습니다.") from exc

    return WhiteboardAnalysisOut(analysis=analysis, disclaimer=LOW_CONFIDENCE_DISCLAIMER)
