"""REQ-008 (Feature D, unit-9): 라이브 코딩 환경 — 코드 제출/저장(+ unit-29 후속 실행).

03-system-design.md §4.2 `/interviews/{id}/code-submissions`(POST 원 계획, GET은 v2
DEC-024 갭3 신규) + §3.1 ERD `CODE_SUBMISSIONS` + 04-ux-design.md [C-07] 코드 에디터
패널. DEC-008이 코드 "실행" 기능을 Out-of-Scope로 확정했었으나, unit-29가 격리 코드를
작성하고 사용자가 2026-09-24 실행 엔드포인트 배선을 명시 승인해 DEC-008을 이 파일
안에서 부분적으로 뒤집는다 — 저장/조회(POST·GET, 실행 없음)와 실행(POST .../execute,
`code_sandbox.py` 격리 호출)을 같은 라우터에 함께 둔다.

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
from app.schemas.code_submission import (
    CodeExecutionCreate,
    CodeExecutionOut,
    CodeSubmissionCreate,
    CodeSubmissionOut,
)
from app.services.code_sandbox import UnsupportedSandboxLanguage, execute_code_sandboxed
from app.services.prompt_safety import RateLimitExceeded, check_and_increment_sandbox_rate_limit

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


@router.post(
    "/{interview_id}/code-submissions/execute",
    response_model=CodeExecutionOut,
    status_code=status.HTTP_200_OK,
)
def execute_code_submission(
    interview_id: UUID,
    payload: CodeExecutionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CodeExecutionOut:
    """(unit-29 후속, 2026-09-24 사용자 승인) 제출된 코드를 `code_sandbox.py`의
    9중 격리 Docker 컨테이너 안에서 실제로 실행한다. 실행 결과는 DB에 저장하지
    않는다(`code_submission.py`가 "이 모델은 실행과 관련된 어떤 필드도 갖지
    않는다"고 명시한 원칙을 그대로 유지 — 저장은 기존 POST가, 실행은 이 엔드포인트가
    각각 독립적으로 담당하며 서로의 데이터를 공유하지 않는다).

    신뢰할 수 없는 제3자(면접 지원자) 코드를 실행하는 기능이라 (1) 소유권 검사
    (2) 전용 분당 5회 레이트리밋(다른 두 한도보다 보수적) (3) 언어 화이트리스트
    (저장 11종보다 훨씬 좁은 실행 지원 2종만) 순서로 방어한 뒤에만 실제 실행에
    도달한다.
    """
    _get_own_interview(interview_id, current_user, db)

    try:
        check_and_increment_sandbox_rate_limit(str(current_user.id))
    except RateLimitExceeded as exc:
        raise AppError(429, "RATE_LIMIT_EXCEEDED", "Too Many Requests", str(exc)) from exc

    try:
        result = execute_code_sandboxed(payload.language, payload.content)
    except UnsupportedSandboxLanguage as exc:
        raise AppError(422, "VALIDATION_ERROR", "Validation Error", str(exc)) from exc

    return CodeExecutionOut(
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
        timed_out=result.timed_out,
    )
