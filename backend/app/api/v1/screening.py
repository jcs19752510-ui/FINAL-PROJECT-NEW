"""이력서 AI 판정용 면접기준 조회/저장 (recruiter 전용)."""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.recruiter import _require_recruiter
from app.db.session import get_db
from app.models.resume_application import ResumeApplication
from app.models.screening_criteria import DEFAULT_PASS_THRESHOLD, ScreeningCriteria
from app.models.user import User
from app.schemas.screening import ScreeningCriteriaIn, ScreeningCriteriaOut

router = APIRouter(prefix="/recruiter", tags=["recruiter-screening"])


def get_criteria_row(db: Session) -> ScreeningCriteria | None:
    return db.scalars(select(ScreeningCriteria).limit(1)).first()


def current_criteria_version(db: Session) -> int:
    row = get_criteria_row(db)
    return row.version if row is not None else 0


def _to_out(db: Session, row: ScreeningCriteria | None) -> ScreeningCriteriaOut:
    if row is None:
        return ScreeningCriteriaOut(criteria_text="", pass_threshold=DEFAULT_PASS_THRESHOLD, version=0)
    name = db.scalar(select(User.name).where(User.id == row.updated_by)) if row.updated_by else None
    return ScreeningCriteriaOut(
        criteria_text=row.criteria_text,
        pass_threshold=row.pass_threshold,
        version=row.version,
        updated_at=row.updated_at,
        updated_by_name=name,
    )


@router.get("/screening-criteria", response_model=ScreeningCriteriaOut)
def get_screening_criteria(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScreeningCriteriaOut:
    _require_recruiter(current_user)
    return _to_out(db, get_criteria_row(db))


@router.put("/screening-criteria", response_model=ScreeningCriteriaOut)
def put_screening_criteria(
    payload: ScreeningCriteriaIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScreeningCriteriaOut:
    _require_recruiter(current_user)
    row = get_criteria_row(db)
    if row is None:
        row = ScreeningCriteria(
            criteria_text=payload.criteria_text,
            pass_threshold=payload.pass_threshold,
            version=1,
            updated_by=current_user.id,
            updated_at=datetime.now(UTC),
        )
        db.add(row)
        changed = True
    else:
        changed = row.criteria_text != payload.criteria_text or row.pass_threshold != payload.pass_threshold
        if changed:
            row.criteria_text = payload.criteria_text
            row.pass_threshold = payload.pass_threshold
            row.version += 1
            row.updated_by = current_user.id
            row.updated_at = datetime.now(UTC)
    if changed:
        # 실패 건도 새 기준 버전에서 다시 시도되도록 재시도 횟수 초기화
        db.execute(update(ResumeApplication).values(ai_attempts=0))
    db.commit()
    db.refresh(row)
    return _to_out(db, row)
