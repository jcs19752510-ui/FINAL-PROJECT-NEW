from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

# REQ-017 / DEC-008: 순수 드로잉 데이터(스트로크 좌표 배열)만 다룬다. AI 분석 대상이
# 아니므로 이미지 바이너리나 임의 blob이 아니라, 프론트 캔버스가 그대로 재생(replay)할
# 수 있는 구조화된 좌표 JSON을 계약으로 삼는다.
MAX_STROKES = 2000
MAX_POINTS_PER_STROKE = 5000


class WhiteboardPoint(BaseModel):
    x: float
    y: float


class WhiteboardStroke(BaseModel):
    points: list[WhiteboardPoint]
    color: str = Field(max_length=32)
    width: float = Field(gt=0, le=64)

    @field_validator("points")
    @classmethod
    def _points_bounds(cls, value: list[WhiteboardPoint]) -> list[WhiteboardPoint]:
        if len(value) == 0:
            raise ValueError("stroke는 최소 1개 이상의 점을 가져야 합니다.")
        if len(value) > MAX_POINTS_PER_STROKE:
            raise ValueError(f"stroke 하나의 점 개수는 {MAX_POINTS_PER_STROKE}개를 넘을 수 없습니다.")
        return value


class WhiteboardSaveRequest(BaseModel):
    strokes: list[WhiteboardStroke]

    @field_validator("strokes")
    @classmethod
    def _strokes_bounds(cls, value: list[WhiteboardStroke]) -> list[WhiteboardStroke]:
        if len(value) > MAX_STROKES:
            raise ValueError(f"strokes는 {MAX_STROKES}개를 넘을 수 없습니다.")
        return value


class WhiteboardSnapshotOut(BaseModel):
    id: UUID
    interview_id: UUID
    strokes: list[WhiteboardStroke]
    created_at: datetime

    model_config = {"from_attributes": True}
