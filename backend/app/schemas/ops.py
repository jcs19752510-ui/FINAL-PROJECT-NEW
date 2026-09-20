"""REQ-016: `GET /api/v1/ops/health` 응답 스키마 (03-system-design.md §4.2, §7.2)."""
from datetime import datetime

from pydantic import BaseModel


class OpsHealthOut(BaseModel):
    queue_length: int
    gpu_memory_used_bytes: int
    error_rate: float
    active_sessions: int
    checked_at: datetime
    # 각 지표가 실측값인지, 하위 시스템 미구축으로 인한 정직한 0/빈 값인지를
    # 화면([O-01])이 그대로 노출할 수 있도록 필드별 설명을 함께 내려준다.
    notes: dict[str, str]
