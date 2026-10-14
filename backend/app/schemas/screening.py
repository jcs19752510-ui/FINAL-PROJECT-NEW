"""이력서 AI 판정용 면접기준 스키마."""
import re
from datetime import datetime

from pydantic import BaseModel, field_validator

from app.models.screening_criteria import DEFAULT_PASS_THRESHOLD, MAX_CRITERIA_CHARS

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")  # \t(0x09), \n(0x0a) 유지


class ScreeningCriteriaOut(BaseModel):
    criteria_text: str = ""
    pass_threshold: int = DEFAULT_PASS_THRESHOLD
    version: int = 0
    updated_at: datetime | None = None
    updated_by_name: str | None = None


class ScreeningCriteriaIn(BaseModel):
    criteria_text: str
    pass_threshold: int

    @field_validator("criteria_text")
    @classmethod
    def _clean_text(cls, v: str) -> str:
        v = _CONTROL_CHARS.sub("", v).strip()
        if not v:
            raise ValueError("면접기준을 입력해주세요.")
        if len(v) > MAX_CRITERIA_CHARS:
            raise ValueError(f"면접기준은 최대 {MAX_CRITERIA_CHARS}자까지 입력할 수 있습니다.")
        return v

    @field_validator("pass_threshold")
    @classmethod
    def _check_threshold(cls, v: int) -> int:
        if not 1 <= v <= 100:
            raise ValueError("합격선은 1~100 사이여야 합니다.")
        return v
