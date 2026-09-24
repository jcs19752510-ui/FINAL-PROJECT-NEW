"""REQ-018(Feature H 확장, unit-31 재후속): 표정 기반 감정분석 — 개인 PC 임시 테스트 전용.

2026-09-24 사용자가 "법무 자문 없이 개인 PC에서만 임시 테스트"로 범위를 명시적으로
좁혀 API 배선을 승인 — `emotion_engine.py` 모듈 docstring이 요구하던 "실제 채용
프로세스 연결 전 법무 검토 필수" 원칙은 그대로 유지한다. 이 엔드포인트는 면접
평가/리포트 파이프라인 어디에도 연결되지 않은 완전히 독립된 진단용 엔드포인트다
— 이미지를 받아 감정 분석 결과만 반환하고 DB에 아무것도 저장하지 않는다.

`interviews.py`(면접 세션 상태머신, unit-2~4 소유)는 건드리지 않는다 — 소유권
검사는 whiteboard.py/code_submissions.py 선례를 그대로 따라 이 파일 안에서 독립
재구현한다.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.errors import AppError
from app.db.session import get_db
from app.models.interview import Interview
from app.models.user import User
from app.schemas.emotion import EmotionAnalysisOut
from app.services.emotion_engine import LOCAL_TEST_ONLY_DISCLAIMER, EmotionAnalysisError, analyze_face_emotion

router = APIRouter(prefix="/interviews", tags=["webcam-emotion"])

_MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 웹캠 정지 프레임 1장 기준 넉넉한 상한(구현 세부값)


def _get_own_interview(interview_id: UUID, current_user: User, db: Session) -> Interview:
    interview = db.get(Interview, interview_id)
    if interview is None:
        raise AppError(404, "NOT_FOUND", "Not Found", "면접 세션을 찾을 수 없습니다.")
    if interview.candidate_id != current_user.id:
        raise AppError(403, "AUTH_FORBIDDEN", "Forbidden", "본인의 면접 세션만 조작할 수 있습니다.")
    return interview


@router.post(
    "/{interview_id}/webcam-emotion",
    response_model=EmotionAnalysisOut,
    status_code=status.HTTP_200_OK,
)
async def analyze_webcam_emotion(
    interview_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmotionAnalysisOut:
    """정지 이미지 1장(webcam 프레임)을 받아 DeepFace로 7종 감정 확률 분포를
    반환한다. 이미지는 응답 생성에만 쓰이고 어디에도 저장하지 않는다(§ 모듈
    docstring 원칙).
    """
    _get_own_interview(interview_id, current_user, db)

    try:
        form = await request.form()
    except Exception as exc:  # noqa: BLE001 — 잘못된 multipart 인코딩 등 클라이언트 입력 오류
        raise AppError(422, "VALIDATION_ERROR", "Validation Error", "multipart 형식이 올바르지 않습니다.") from exc

    image = form.get("image")
    if image is None or not hasattr(image, "read"):
        raise AppError(422, "VALIDATION_ERROR", "Validation Error", "이미지 파일(`image` 필드)이 필요합니다.")

    image_bytes = await image.read()
    if not image_bytes:
        raise AppError(422, "VALIDATION_ERROR", "Validation Error", "빈 이미지 파일입니다.")
    if len(image_bytes) > _MAX_IMAGE_BYTES:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "Validation Error",
            f"이미지 파일이 너무 큽니다 (최대 {_MAX_IMAGE_BYTES // (1024 * 1024)}MB).",
        )

    try:
        result = analyze_face_emotion(image_bytes)
    except EmotionAnalysisError as exc:
        raise AppError(422, "VALIDATION_ERROR", "Validation Error", str(exc)) from exc

    return EmotionAnalysisOut(
        dominant_emotion=result.dominant_emotion,
        scores=result.scores,
        face_confidence=result.face_confidence,
        disclaimer=LOCAL_TEST_ONLY_DISCLAIMER,
    )
