"""REQ-011: 채용담당자 대시보드 — 리포트 열람(최소 뷰어) (03-system-design.md §4.2
`/recruiter/reports`, §6.1 RBAC).

범위(unit-12, Feature F): `GET /api/v1/recruiter/reports`(지원자 면접 목록),
`GET /api/v1/recruiter/reports/{interview_id}`(리포트 상세, 최소 뷰어).

**설계서 대비 편차 (오케스트레이터 지시에 따른 병렬 개발 파일충돌 회피, 규칙 A 대상 아님
— 정책적 모호함이 아니라 동시성 제약에 의한 결정)**: 03-design §4.2는 리포트 상세를
지원자 화면([C-11])과 recruiter 화면([R-02])이 `GET /interviews/{id}/report` 하나의
엔드포인트를 RBAC으로 공유하도록 설계했다. unit-12 당시에는 병렬 개발 파일충돌 회피를
위해 `interviews.py`를 건드리지 않고 recruiter 전용 엔드포인트로 신설했으나(아래
`get_report_detail`), **Feature E(REQ-009/010/012)가 캐노니컬 `GET /interviews/{id}/report`
(`app/api/v1/interviews.py::get_report`)를 실제로 구현하면서, 이 함수는 그 규칙 F
정리(인수인계 원문 그대로) 그 캐노니컬 로직의 얇은 래퍼로 축소됐다** — recruiter
전용 URL(`/recruiter/reports/{interview_id}`)은 프런트 하위호환을 위해 유지하되,
데이터 조회는 `interviews.py`의 `_report_to_out`/`EVALUATION_REPORTS` 조회를
그대로 재사용한다(중복 구현 금지).
"""
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.interviews import _report_to_out
from app.core.errors import AppError
from app.db.session import get_db
from app.models.evaluation_report import EvaluationReport
from app.models.interview import Interview, ReportStatus
from app.models.rubric_template import RubricTemplate
from app.models.user import User, UserRole
from app.schemas.recruiter import RecruiterInterviewListItemOut, RecruiterReportDetailOut
from app.schemas.rubric_template import (
    RubricTemplateAssignIn,
    RubricTemplateAssignOut,
    RubricTemplateCreateIn,
    RubricTemplateOut,
    RubricTemplateUpdateIn,
)
from app.services.job_queue import MAX_QUEUE_LENGTH, enqueue_report_generation_job, queue_length

router = APIRouter(prefix="/recruiter", tags=["recruiter"])


def _require_recruiter(current_user: User) -> None:
    # 03-design §6.1 MVP 기본값: 단일 조직 내 모든 recruiter가 모든 리포트 열람 가능
    # (organization_id 기반 세분화 없음 — §8 트레이드오프 #10, 멀티테넌시는 범위 밖).
    if current_user.role != UserRole.recruiter:
        raise AppError(403, "AUTH_FORBIDDEN", "Forbidden", "채용담당자(recruiter)만 접근할 수 있습니다.")


def _report_state_message(report_status: ReportStatus) -> str:
    if report_status == ReportStatus.none:
        return "아직 리포트 생성이 요청되지 않았습니다."
    if report_status == ReportStatus.queued:
        return "리포트를 생성하는 중입니다. 잠시 후 다시 확인해주세요."
    if report_status == ReportStatus.failed:
        return "리포트 생성에 실패했습니다. 지원자가 재시도할 수 있습니다."
    return "리포트가 준비되었습니다."


@router.get("/reports", response_model=list[RecruiterInterviewListItemOut])
def list_reports(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RecruiterInterviewListItemOut]:
    """REQ-011/[R-01]: 지원자 면접 목록(모든 지원자, MVP 단일조직 정책, §6.1)."""
    _require_recruiter(current_user)

    stmt = (
        select(Interview, User)
        .join(User, Interview.candidate_id == User.id)
        .order_by(Interview.created_at.desc())
    )
    rows = db.execute(stmt).all()
    return [
        RecruiterInterviewListItemOut(
            interview_id=interview.id,
            candidate_name=candidate.name,
            candidate_email=candidate.email,
            status=interview.status.value,
            report_status=interview.report_status.value,
            started_at=interview.started_at,
            ended_at=interview.ended_at,
            overall_score=interview.overall_score,
        )
        for interview, candidate in rows
    ]


@router.get("/reports/{interview_id}", response_model=RecruiterReportDetailOut)
def get_report_detail(
    interview_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecruiterReportDetailOut:
    """REQ-011/[R-02]: 리포트 상세(열람 전용). `report_status`에 따른 빈 상태/처리중
    안내만 반환하며, 실제 리포트 본문(STAR/루브릭/근거)은 Feature E 미구현으로 항상
    없음(모듈 docstring 참고).
    """
    _require_recruiter(current_user)

    row = db.execute(
        select(Interview, User).join(User, Interview.candidate_id == User.id).where(Interview.id == interview_id)
    ).first()
    if row is None:
        raise AppError(404, "NOT_FOUND", "Not Found", "면접 세션을 찾을 수 없습니다.")
    interview, candidate = row

    report_available = interview.report_status == ReportStatus.ready
    report = None
    if report_available:
        report = db.scalar(select(EvaluationReport).where(EvaluationReport.interview_id == interview_id))
    canonical = _report_to_out(interview, report, db) if report_available else None

    return RecruiterReportDetailOut(
        interview_id=interview.id,
        candidate_name=candidate.name,
        candidate_email=candidate.email,
        status=interview.status.value,
        report_status=interview.report_status.value,
        started_at=interview.started_at,
        ended_at=interview.ended_at,
        overall_score=interview.overall_score,
        report_available=report_available,
        message=_report_state_message(interview.report_status),
        technical_score=canonical.technical_score if canonical else None,
        communication_score=canonical.communication_score if canonical else None,
        cultural_fit_score=canonical.cultural_fit_score if canonical else None,
        overall_recommendation=canonical.overall_recommendation if canonical else None,
        pass_fail_recommendation=canonical.pass_fail_recommendation if canonical else None,
        star=canonical.star if canonical else None,
        summary_text=canonical.summary_text if canonical else None,
        details=canonical.details if canonical else None,
        rubric=canonical.rubric if canonical else None,
    )


def _rubric_template_to_out(template: RubricTemplate) -> RubricTemplateOut:
    return RubricTemplateOut(
        id=template.id,
        recruiter_id=template.recruiter_id,
        name=template.name,
        criteria=template.criteria_json,
        is_system_default=template.recruiter_id is None,
        created_at=template.created_at,
    )


@router.get("/rubric-templates", response_model=list[RubricTemplateOut])
def list_rubric_templates(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RubricTemplateOut]:
    """REQ-014/[R-03]: 내 템플릿 + 시스템 기본 템플릿(`recruiter_id IS NULL`, §3.1) 목록.

    04-ux-design v2 [R-03] 빈 상태 명세("기본 템플릿을 복사해 시작하세요")를 위해
    시스템 기본 템플릿을 항상 함께 내려준다.
    """
    _require_recruiter(current_user)

    stmt = (
        select(RubricTemplate)
        .where((RubricTemplate.recruiter_id == current_user.id) | (RubricTemplate.recruiter_id.is_(None)))
        .order_by(RubricTemplate.created_at.desc())
    )
    templates = db.execute(stmt).scalars().all()
    return [_rubric_template_to_out(t) for t in templates]


@router.post("/rubric-templates", response_model=RubricTemplateOut, status_code=201)
def create_rubric_template(
    payload: RubricTemplateCreateIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RubricTemplateOut:
    """REQ-014/[R-03]: 신규 템플릿 생성(항상 `recruiter_id=current_user.id`로 소유).

    시스템 기본 템플릿을 "복사해 시작"하는 것도 클라이언트가 기존 템플릿의
    name/criteria를 이 엔드포인트의 입력값으로 그대로 채워 넣는 방식으로 이 API
    하나로 처리한다(03-design에 별도 "복제" 엔드포인트가 정의되어 있지 않음).
    """
    _require_recruiter(current_user)

    template = RubricTemplate(
        recruiter_id=current_user.id,
        name=payload.name,
        criteria_json=[c.model_dump() for c in payload.criteria],
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return _rubric_template_to_out(template)


@router.patch("/rubric-templates/{template_id}", response_model=RubricTemplateOut)
def update_rubric_template(
    template_id: UUID,
    payload: RubricTemplateUpdateIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RubricTemplateOut:
    """REQ-014/[R-03]: 내가 만든 템플릿의 이름/평가기준 최소 수정.

    시스템 기본 템플릿(`recruiter_id IS NULL`)이나 다른 recruiter가 만든 템플릿은
    수정할 수 없다 — [R-03] 명세가 "복사해 시작"을 전제하므로, 기본 템플릿은
    직접 수정 대상이 아니라 원본으로만 유지한다.
    """
    _require_recruiter(current_user)

    template = db.get(RubricTemplate, template_id)
    if template is None:
        raise AppError(404, "NOT_FOUND", "Not Found", "템플릿을 찾을 수 없습니다.")
    if template.recruiter_id != current_user.id:
        raise AppError(
            403,
            "AUTH_FORBIDDEN",
            "Forbidden",
            "본인이 만든 템플릿만 수정할 수 있습니다. 기본 템플릿은 복사해 새 템플릿을 만들어주세요.",
        )

    if payload.name is not None:
        template.name = payload.name
    if payload.criteria is not None:
        template.criteria_json = [c.model_dump() for c in payload.criteria]

    db.commit()
    db.refresh(template)
    return _rubric_template_to_out(template)


@router.put("/interviews/{interview_id}/rubric-template", response_model=RubricTemplateAssignOut)
def assign_rubric_template(
    interview_id: UUID,
    payload: RubricTemplateAssignIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RubricTemplateAssignOut:
    """v15(03-system-design v4 §4.6 (2), unit-37, REQ-010/014, DEC-054/055): 면접에
    채점용 루브릭 템플릿을 지정한다. 리포트가 이미 `ready`/`failed`면 새 템플릿으로
    재채점 job을 투입한다(202에 준하는 의미로 `job_id`를 채워 반환, 응답 status 자체는
    200 — 04-ux-design [R-02]가 `job_id` 유무로 "채점 중" 전환 여부를 판단).
    """
    _require_recruiter(current_user)

    interview = db.get(Interview, interview_id)
    if interview is None:
        raise AppError(404, "NOT_FOUND", "Not Found", "면접 세션을 찾을 수 없습니다.")

    template = db.get(RubricTemplate, payload.rubric_template_id)
    if template is None:
        raise AppError(404, "NOT_FOUND", "Not Found", "템플릿을 찾을 수 없습니다.")
    if template.recruiter_id is not None and template.recruiter_id != current_user.id:
        raise AppError(
            403, "AUTH_FORBIDDEN", "Forbidden", "본인이 만든 템플릿 또는 기본 템플릿만 지정할 수 있습니다."
        )

    if interview.rubric_template_id == template.id:
        return RubricTemplateAssignOut(interview_id=interview.id, rubric_template_id=template.id, job_id=None)

    if interview.report_status == ReportStatus.queued:
        raise AppError(
            409, "VALIDATION_ERROR", "Conflict", "이미 채점이 진행 중입니다. 완료된 뒤 다시 시도해 주세요."
        )

    job_id: str | None = None
    if interview.report_status in (ReportStatus.ready, ReportStatus.failed):
        # §4.6 (2) "남용 제한" — 재채점은 새로 만드는 경로이므로 여기서만 큐 상한을
        # 직접 확인한다(job_queue.py 모듈 docstring, 기존 턴/종료 경로는 범위 밖).
        try:
            if queue_length() >= MAX_QUEUE_LENGTH:
                raise AppError(
                    503,
                    "QUEUE_FULL",
                    "Service Unavailable",
                    "지금 처리 대기 중인 작업이 많습니다. 잠시 후 다시 시도해 주세요.",
                )
        except AppError:
            raise
        except Exception:  # noqa: BLE001 — Redis 순간 오류는 "확인 불가 → 허용"(job_queue.py queue_length 참고)
            pass
        interview.rubric_template_id = template.id
        interview.report_status = ReportStatus.queued
        db.commit()
        job_id = enqueue_report_generation_job(interview.id)
    else:
        interview.rubric_template_id = template.id
        db.commit()

    return RubricTemplateAssignOut(interview_id=interview.id, rubric_template_id=template.id, job_id=job_id)
