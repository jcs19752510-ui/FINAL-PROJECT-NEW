"""REQ-011: 채용담당자 대시보드 — 리포트 열람(최소 뷰어) (03-system-design.md §4.2
`/recruiter/reports`, §6.1 RBAC).

범위(unit-12, Feature F): `GET /api/v1/recruiter/reports`(지원자 면접 목록),
`GET /api/v1/recruiter/reports/{interview_id}`(리포트 상세, 최소 뷰어).

**설계서 대비 편차 (오케스트레이터 지시에 따른 병렬 개발 파일충돌 회피, 규칙 A 대상 아님
— 정책적 모호함이 아니라 동시성 제약에 의한 결정)**: 03-design §4.2는 리포트 상세를
지원자 화면([C-11])과 recruiter 화면([R-02])이 `GET /interviews/{id}/report` 하나의
엔드포인트를 RBAC으로 공유하도록 설계했다. 그러나 이 유닛은 병렬로 개발 중인 다른
유닛과의 파일 충돌을 피하기 위해 `interviews.py`(및 그 파일을 다루는 다른 진행 중
작업)를 건드리지 않고 recruiter 전용 신규 파일/엔드포인트로 한정하라는 명시적 지시를
받았다. 따라서 recruiter 전용 `GET /recruiter/reports/{interview_id}`를 별도로
신설한다. Feature E(unit-10/11)가 `/interviews/{id}/report`를 구현할 때 이 엔드포인트와의
중복(리포트 상세 조회 경로가 2개 존재)을 규칙 F로 재확인해 정리(예: 이 엔드포인트를
canonical 엔드포인트의 recruiter 전용 얇은 래퍼로 축소하거나 프론트를 canonical
엔드포인트로 전환)할 것을 후속 유닛에 인수인계한다.

**리포트 실측 데이터 부재 (Feature E, unit-10/11 미착수)**: `EVALUATION_REPORTS` 테이블/
모델이 아직 존재하지 않는다. `INTERVIEWS.report_status`가 `ready`가 되는 실제 경로
자체도 아직 없다(unit-4/7/10의 `job_queue.py`는 job_id만 발급하는 스텁). 따라서 이
유닛은 `report_status` 값과 무관하게 리포트 본문 데이터를 반환하지 않고, 상태별로
정직한 안내 메시지만 반환한다(`report_available=false` 고정 — unit-18의 "가짜 데이터
금지" 선례를 그대로 따름). `ready` 상태에서도 예외 없이 동일 원칙을 적용한다.
"""
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.errors import AppError
from app.db.session import get_db
from app.models.interview import Interview, ReportStatus
from app.models.rubric_template import RubricTemplate
from app.models.user import User, UserRole
from app.schemas.recruiter import RecruiterInterviewListItemOut, RecruiterReportDetailOut
from app.schemas.rubric_template import (
    RubricTemplateCreateIn,
    RubricTemplateOut,
    RubricTemplateUpdateIn,
)

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
        return "리포트 생성에 실패했습니다."
    # ready: EVALUATION_REPORTS 모델이 없어(Feature E 미구현) 실제 데이터를 조회할
    # 방법이 없다 — 있는 것처럼 꾸미지 않고 명시적으로 안내한다.
    return "리포트 상세 데이터 조회 기능은 아직 준비 중입니다(평가 리포트 생성 기능 개발 예정, Feature E)."


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

    return RecruiterReportDetailOut(
        interview_id=interview.id,
        candidate_name=candidate.name,
        candidate_email=candidate.email,
        status=interview.status.value,
        report_status=interview.report_status.value,
        started_at=interview.started_at,
        ended_at=interview.ended_at,
        overall_score=interview.overall_score,
        report_available=False,
        message=_report_state_message(interview.report_status),
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
