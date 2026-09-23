"""03-system-design.md §3.1 ERD의 EVALUATION_REPORTS 테이블 (REQ-009/010/012, Feature E).

`interview_id`는 UK(면접 1건당 리포트 1건, `POST /report/regenerate`는 기존 행을
갱신한다). `overall_recommendation`은 REQ-031(개인정보 보호법 제37조의2 자동화된
결정 거부권)에 따라 `recommend/neutral/not_recommend` 3단계 권고 등급만 허용한다.
`star_json`이 1차 데이터소스이고 `summary_text`는 LLM이 STAR 스키마 파싱에 실패했을
때만 채워지는 폴백 전용 필드다(§4.4). `star_json`/`summary_text`/`details_json`은
REQ-036 새니타이즈 대상 — 이 값들을 렌더링하는 화면(프런트)이 XSS 방어를 책임진다
(저장 시점에는 원문 그대로 보관, `app/models/code_submission.py`의 동일 원칙 참고).

**pass_fail_recommendation(2026-09-22 사용자 명시 승인)**: 원 계획서(REQ-F-006/007,
"웹 AI 모의면접 프로젝트 계획서.pdf" §3.1.3)가 요구한 "합격/불합격 추천 의견"을
복원한 필드다. 이 필드는 §3.2가 원래 "스키마 자체에 만들지 않는다"고 명시했던
바로 그 종류의 값이며(REQ-031 자동화된 결정 거부권과 정면으로 긴장 관계에 있음),
사용자가 이 법적 리스크를 명시적으로 인지한 상태에서 추가를 승인해 도입했다
(대화 기록 기준 결정, `docs/harness/decisions/` 정식 DEC 번호 미부여 — 후속 09단계
보안/컴플라이언스 감사에서 재검토 필요). 반드시 nullable + `overall_recommendation`
(3단계 권고)과 `REPORT_DISCLAIMER`("최종 채용 결정은 인간이 내립니다") 곁에서만
노출해 "자동 확정"이 아닌 "참고용 추가 의견"이라는 문맥을 유지한다. 실제 배포
전에는 법무 검토가 선행되어야 한다(자체 판단으로 법적 리스크를 해소한 것이 아님).
"""
import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class OverallRecommendation(StrEnum):
    recommend = "recommend"
    neutral = "neutral"
    not_recommend = "not_recommend"


class PassFailRecommendation(StrEnum):
    """원안 REQ-F-006/007 복원분. `pass`/`fail`은 파이썬 예약어가 아니라 값 자체는
    문제없으나, 멤버명을 `pass_`/`fail_`로 두는 대신 그대로 두면 `pass`는 예약어라
    멤버명으로 쓸 수 없어 `pass_`로 우회한다(직렬화되는 값은 "pass" 그대로).
    """

    pass_ = "pass"
    fail = "fail"
    borderline = "borderline"


class EvaluationReport(Base):
    __tablename__ = "evaluation_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interviews.id"), nullable=False, unique=True, index=True
    )
    technical_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    communication_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cultural_fit_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overall_recommendation: Mapped[OverallRecommendation | None] = mapped_column(
        Enum(OverallRecommendation, name="overall_recommendation"), nullable=True
    )
    # 원안 복원분(위 모듈 docstring "pass_fail_recommendation" 참고) — REPORT_DISCLAIMER
    # 없이 단독 노출 금지.
    #
    # 2026-09-22 실측 결함: SQLAlchemy `Enum(PythonEnum)`은 기본적으로 멤버 "이름"을
    # DB에 저장한다(OverallRecommendation처럼 이름==값이면 무해했으나, `pass_fail_
    # recommendation`은 멤버명이 `pass_`인데 값은 "pass"라 이름≠값 — 기본 설정으로
    # INSERT 시 "pass_"를 넣으려다 DB enum 라벨("pass")과 불일치해
    # `InvalidTextRepresentation`이 실제로 발생함을 확인). `values_callable`로 값
    # 기준 직렬화를 명시해 해결.
    pass_fail_recommendation: Mapped[PassFailRecommendation | None] = mapped_column(
        Enum(
            PassFailRecommendation,
            name="pass_fail_recommendation",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=True,
    )
    # {"situation": str, "task": str, "action": str, "result": str} — §4.4. 파싱
    # 성공 시에만 채워지고, 실패 시 null(그 경우 summary_text가 폴백으로 채워짐).
    star_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
