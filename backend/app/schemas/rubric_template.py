"""REQ-014: 채용담당자 질문지/루브릭 최소 커스터마이징 응답/요청 스키마 (unit-13,
Feature F). 03-system-design.md §4.2 `/recruiter/rubric-templates`, §3.1
RUBRIC_TEMPLATES(name, criteria_json)와 1:1 대응.
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RubricCriterionIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    weight: int = Field(ge=0, le=100)
    description: str = Field(default="", max_length=500)


class RubricTemplateCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    criteria: list[RubricCriterionIn] = Field(min_length=1, max_length=20)


class RubricTemplateUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    criteria: list[RubricCriterionIn] | None = Field(default=None, min_length=1, max_length=20)


class RubricTemplateOut(BaseModel):
    id: UUID
    recruiter_id: UUID | None
    name: str
    criteria: list[RubricCriterionIn]
    is_system_default: bool
    created_at: datetime


class RubricTemplateAssignIn(BaseModel):
    """v15(03-system-design v4 §4.6 (2), unit-37) —
    `PUT /recruiter/interviews/{id}/rubric-template` 요청 바디.
    """

    rubric_template_id: UUID


class RubricTemplateAssignOut(BaseModel):
    interview_id: UUID
    rubric_template_id: UUID
    # 재채점 job이 새로 투입됐을 때만 값이 있다(§4.6 (2) 202 응답).
    job_id: str | None = None
