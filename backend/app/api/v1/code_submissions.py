"""REQ-008 (Feature D, unit-9): 라이브 코딩 환경 — 코드 제출/저장(실행 없음).

03-system-design.md §4.2 `/interviews/{id}/code-submissions`(POST 원 계획, GET은 v2
DEC-024 갭3 신규) + §3.1 ERD `CODE_SUBMISSIONS` + 04-ux-design.md [C-07] 코드 에디터
패널. DEC-008에 따라 코드 "실행" 기능은 범위 밖이며, 이 라우터는 순수 저장/조회만
다룬다.

`interviews.py`(면접 세션 상태머신, unit-2~4 소유)는 이번 유닛의 지시 범위 밖이라
건드리지 않는다 — 소유권 검사(`_get_own_interview`류 로직)는 이 파일 안에 독립적으로
다시 구현한다(consents.py가 세운 "별도 라우터 파일 + main.py에만 등록" 선례를 그대로
따름).
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.errors import AppError
from app.db.session import get_db
from app.models.code_submission import CodeSubmission
from app.models.interview import Interview
from app.models.user import User
from app.schemas.code_submission import CodeSubmissionCreate, CodeSubmissionOut

router = APIRouter(prefix="/interviews", tags=["code-submissions"])


def _get_own_interview(interview_id: UUID, current_user: User, db: Session) -> Interview:
    """본인 소유 세션만 조회/조작 가능하게 한다 (수평 권한 상승 방지).

    `app/api/v1/interviews.py`의 동명 헬퍼와 로직이 같다 — 그 파일은 이번 유닛의
    수정 범위 밖(오케스트레이터 지시)이라 공유 모듈로 추출하지 않고 이 파일 안에
    독립적으로 둔다(consents.py도 동일 원칙으로 자기 파일 안에서 검사 로직을 완결함).
    """
    interview = db.get(Interview, interview_id)
    if interview is None:
        raise AppError(404, "NOT_FOUND", "Not Found", "면접 세션을 찾을 수 없습니다.")
    if interview.candidate_id != current_user.id:
        raise AppError(403, "AUTH_FORBIDDEN", "Forbidden", "본인의 면접 세션만 조작할 수 있습니다.")
    return interview


@router.post(
    "/{interview_id}/code-submissions",
    response_model=CodeSubmissionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_code_submission(
    interview_id: UUID,
    payload: CodeSubmissionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CodeSubmission:
    """코드 제출/저장(REQ-008, 실행 없음). 매 저장을 새 이력 행으로 남긴다(TRANSCRIPTS와
    동일한 append-only 패턴) — [C-07] "저장 상태 표시(저장됨/저장 중/미저장)"가 반복
    저장을 전제하고, GET이 "최신본 또는 이력"을 조회해야 하기 때문이다.
    """
    interview = _get_own_interview(interview_id, current_user, db)

    submission = CodeSubmission(
        interview_id=interview.id,
        language=payload.language,
        content=payload.content,
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return submission


@router.get(
    "/{interview_id}/code-submissions",
    response_model=list[CodeSubmissionOut],
    status_code=status.HTTP_200_OK,
)
def list_code_submissions(
    interview_id: UUID,
    language: str | None = Query(default=None, max_length=32),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CodeSubmission]:
    """(03-design v2 §4.2 신규, DEC-024 갭3) 코드 제출물 재조회(최신본 또는 이력,
    언어별). 세션 재개([C-12]/[C-07]) 시 최신 항목(`submitted_at desc` 첫 번째)으로
    에디터를 복원하는 데 쓰인다. `language` 쿼리로 특정 언어만 필터링할 수 있다.
    """
    interview = _get_own_interview(interview_id, current_user, db)

    stmt = select(CodeSubmission).where(CodeSubmission.interview_id == interview.id)
    if language is not None:
        stmt = stmt.where(CodeSubmission.language == language.strip().lower())
    stmt = stmt.order_by(CodeSubmission.submitted_at.desc())

    return list(db.scalars(stmt).all())
