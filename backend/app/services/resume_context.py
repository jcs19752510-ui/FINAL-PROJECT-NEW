"""이력서 프로필 DB 접근 — 제출 시 추출 저장, 기존(레거시) 행은 첫 사용 시 한 번 추출(lazy)."""
from __future__ import annotations

import logging
import os
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.resume_application import ResumeApplication
from app.services import resume_profile as rp

logger = logging.getLogger(__name__)


def apply_analysis(app_: ResumeApplication, pdf_bytes: bytes) -> None:
    """PDF 바이트를 분석해 행에 상태와 암호화 요약을 채운다(커밋은 호출부)."""
    status, profile = rp.analyze_resume_pdf(pdf_bytes)
    app_.profile_status = status
    app_.profile_json = rp.dumps_profile(profile) if profile else None


def ensure_profile(db: Session, candidate_id: uuid.UUID) -> tuple[str | None, dict | None]:
    """(상태, 프로필). 이력서 행이 없으면 (None, None).

    `pending`(마이그레이션 이전에 제출된 행)이면 디스크의 PDF를 읽어 한 번 추출·저장한다.
    파일이 없거나 읽을 수 없으면 `unreadable`로 확정한다."""
    app_ = db.scalar(select(ResumeApplication).where(ResumeApplication.candidate_id == candidate_id))
    if app_ is None:
        return None, None
    if app_.profile_status == rp.PROFILE_PENDING:
        try:
            if os.path.isfile(app_.file_path):
                with open(app_.file_path, "rb") as f:
                    apply_analysis(app_, f.read())
            else:
                app_.profile_status = rp.PROFILE_UNREADABLE
                app_.profile_json = None
            db.commit()
        except Exception:  # noqa: BLE001 — 추출 실패는 면접 시작 차단(unreadable)로 귀결
            logger.warning("이력서 lazy 추출 실패", exc_info=True)
            db.rollback()
            return rp.PROFILE_UNREADABLE, None
    if app_.profile_status != rp.PROFILE_READY:
        return app_.profile_status, None
    return rp.PROFILE_READY, rp.loads_profile(app_.profile_json)


def load_profile_for_interview(db: Session, candidate_id: uuid.UUID) -> dict | None:
    """질문 생성용 프로필. 기능이 꺼졌거나 이력서가 없으면 None(기존 동작)."""
    from app.core.config import settings

    if not settings.resume_personalization_enabled:
        return None
    try:
        status, profile = ensure_profile(db, candidate_id)
    except Exception:  # noqa: BLE001 — 개인화 실패가 면접 진행을 막지 않게
        logger.warning("이력서 프로필 로드 실패", exc_info=True)
        return None
    return profile if status == rp.PROFILE_READY else None
