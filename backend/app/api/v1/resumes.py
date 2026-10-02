"""Feature J(REQ-040/041, 2026-09-29 사용자 요청) — 지원자(candidate)용 이력서
제출/상태 조회 (`이력서제출_합격통보_신규기능_요청프롬프트.md` §4-1/§4-4).

이 파일은 `/apply/*` 프런트엔드 경로가 호출하는 백엔드 표면이지만, 프롬프트
§2 결정#1에 따라 백엔드 자체는 별도 앱/포트로 분리하지 않는다 — 기존
`/api/v1`(현재 8001 포트) 그대로 새 라우트만 추가한다.
"""
import os
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_user
from app.api.v1.interviews import _has_active_consent
from app.core.errors import AppError
from app.db.session import get_db
from app.models.consent import ConsentType
from app.models.resume_application import ResumeApplication, ResumeApplicationStatus
from app.models.user import User, UserRole
from app.schemas.resume import MyResumeStatusOut

router = APIRouter(tags=["resumes"])

# unit-5(interviews.py MAX_VOICE_UPLOAD_BYTES=25MB)와 별개로, 이력서는 문서
# 파일이라 그보다 작은 상한을 둔다(구현 세부값, 비가역성 낮음 — 필요시 조정).
MAX_RESUME_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"application/pdf"}

_RESUME_STORAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "var", "resumes")


def _resume_storage_dir() -> str:
    os.makedirs(_RESUME_STORAGE_DIR, exist_ok=True)
    return _RESUME_STORAGE_DIR


def _write_resume_file(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)


@router.post("/resumes", response_model=MyResumeStatusOut, status_code=status.HTTP_201_CREATED)
async def submit_resume(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResumeApplication:
    """이력서(PDF) 제출. `POST /apply` 프런트 화면이 호출한다.

    - candidate role 전용(403).
    - 사전에 `resume_submission` 동의가 없으면 거부(403) — unit-14/15가 확립한
      "새 개인정보 수집은 신규 ConsentType 사전동의 필수" 패턴을 그대로 따른다.
    - 2026-09-30(사용자 지시, DEC-118): 이미 제출 기록이 있으면(상태 무관 —
      pending/accepted/rejected 전부) 재제출을 막는다(409). 예전에는 재제출
      시 기존 지원서를 덮어쓰고 상태를 `pending`으로 되돌리는 정책이었으나,
      "이력서를 제출한 이후에는 상태만 확인 가능해야 한다"는 새 요구로
      대체됐다 — 화면(프런트) 차단만으로는 API를 직접 호출하는 우회를 막지
      못해 백엔드도 함께 막기로 사용자가 명시 확인.
    """
    if current_user.role != UserRole.candidate:
        raise AppError(403, "AUTH_FORBIDDEN", "Forbidden", "지원자(candidate)만 이력서를 제출할 수 있습니다.")

    if not _has_active_consent(db, current_user.id, ConsentType.resume_submission):
        raise AppError(
            403,
            "CONSENT_REQUIRED_RESUME",
            "Forbidden",
            "이력서 제출 전 개인정보 수집 동의가 필요합니다.",
        )

    existing = db.scalar(select(ResumeApplication).where(ResumeApplication.candidate_id == current_user.id))
    if existing is not None:
        raise AppError(
            409,
            "RESUME_ALREADY_SUBMITTED",
            "Conflict",
            "이미 이력서를 제출했습니다. 재제출은 지원하지 않으며, 제출 상태만 확인할 수 있습니다.",
        )

    try:
        form = await request.form()
    except Exception as exc:  # noqa: BLE001 — 잘못된 multipart 인코딩 등 클라이언트 입력 오류
        raise AppError(422, "VALIDATION_ERROR", "Validation Error", "multipart 형식이 올바르지 않습니다.") from exc

    file = form.get("file")
    if file is None or not hasattr(file, "read"):
        raise AppError(422, "VALIDATION_ERROR", "Validation Error", "이력서 파일(`file` 필드)이 필요합니다.")

    content_type = file.content_type or ""
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "Validation Error",
            "PDF 파일만 업로드할 수 있습니다.",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise AppError(422, "VALIDATION_ERROR", "Validation Error", "빈 파일입니다.")
    if len(file_bytes) > MAX_RESUME_UPLOAD_BYTES:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "Validation Error",
            f"이력서 파일이 너무 큽니다 (최대 {MAX_RESUME_UPLOAD_BYTES // (1024 * 1024)}MB).",
        )

    file_name = f"{uuid.uuid4()}.pdf"
    dest_path = os.path.join(_resume_storage_dir(), file_name)
    await run_in_threadpool(_write_resume_file, dest_path, file_bytes)

    application = ResumeApplication(
        candidate_id=current_user.id,
        file_path=dest_path,
        original_filename=file.filename or "resume.pdf",
        content_type=content_type,
        file_size_bytes=len(file_bytes),
        status=ResumeApplicationStatus.pending,
        submitted_at=datetime.now(UTC),
    )
    db.add(application)
    db.commit()
    db.refresh(application)
    return application


@router.get("/users/me/resume-status", response_model=MyResumeStatusOut | None, status_code=status.HTTP_200_OK)
def get_my_resume_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResumeApplication | None:
    """모의면접 홈([C-03] `CandidateHome`)이 게이트 판단에 쓰는 엔드포인트
    (요청 프롬프트 §4-5) — 지원서 기록이 없으면(`null`) 하위호환 정책에 따라
    프런트가 게이트하지 않는다(2026-09-29 사용자 확인).
    """
    return db.scalar(select(ResumeApplication).where(ResumeApplication.candidate_id == current_user.id))
