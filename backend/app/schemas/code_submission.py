from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

# 04-ux-design.md [C-07] "언어 선택 드롭다운"이 유한 목록을 전제하므로, 시스템 경계에서
# 화이트리스트로 제한한다(게이트2 입력값 검증). 목록 확정은 05단계 구현 세부값(비가역성
# 낮음 — 이후 유닛이 필요 시 추가 가능, unit-9-note.md 참고).
ALLOWED_LANGUAGES = frozenset(
    {
        "python",
        "javascript",
        "typescript",
        "java",
        "c",
        "cpp",
        "csharp",
        "go",
        "rust",
        "sql",
        "plaintext",
    }
)


class CodeSubmissionCreate(BaseModel):
    """POST /interviews/{id}/code-submissions 요청 바디 (03-system-design.md §4.2).

    `content` 최대 길이(20000자)는 설계서에 명시되지 않은 구현 세부값 — 시스템 경계
    입력 검증(게이트2)을 위해 이 유닛에서 보수적으로 확정했다(unit-4의 `TurnCreate`
    선례와 동일한 근거/비가역성 판단).
    """

    language: str = Field(min_length=1, max_length=32)
    content: str = Field(min_length=0, max_length=20000)

    @field_validator("language")
    @classmethod
    def _validate_language(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in ALLOWED_LANGUAGES:
            allowed = ", ".join(sorted(ALLOWED_LANGUAGES))
            raise ValueError(f"지원하지 않는 언어입니다. 허용 목록: {allowed}")
        return normalized


class CodeSubmissionOut(BaseModel):
    id: UUID
    interview_id: UUID
    language: str
    content: str
    submitted_at: datetime

    model_config = {"from_attributes": True}


class CodeExecutionCreate(BaseModel):
    """POST /interviews/{id}/code-submissions/execute 요청 바디 (unit-29 후속,
    2026-09-24 사용자 승인). `ALLOWED_LANGUAGES`(11개, 저장용)보다 훨씬 좁은
    `code_sandbox.py`의 실행 지원 언어(python/javascript 2종)만 허용 — 나머지는
    저장은 되지만 "실행"은 422로 거부된다.
    """

    language: str = Field(min_length=1, max_length=32)
    content: str = Field(min_length=1, max_length=20000)

    @field_validator("language")
    @classmethod
    def _validate_language(cls, value: str) -> str:
        return value.strip().lower()


class CodeExecutionOut(BaseModel):
    stdout: str
    stderr: str
    exit_code: int | None
    timed_out: bool
