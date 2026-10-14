"""이력서 AI 판정 상태 계산 (순수 함수 — DB 접근 없음)."""
import json
from typing import Any

from app.models.resume_application import ResumeApplication
from app.models.screening_criteria import MAX_AI_ATTEMPTS


def _parse_reasons(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def compute_ai_view(app: ResumeApplication, current_version: int) -> dict[str, Any]:
    status = app.ai_status
    stale = status == "done" and app.ai_criteria_version != current_version
    if current_version == 0:
        state = "no_criteria"
    elif status == "done" and not stale:
        state = "done"
    elif status == "failed" and (app.ai_attempts or 0) >= MAX_AI_ATTEMPTS:
        state = "failed"
    else:
        state = "pending"
    return {
        "ai_state": state,
        "ai_verdict": app.ai_verdict,
        "ai_score": app.ai_score,
        "ai_threshold": app.ai_threshold,
        "ai_analyzed_at": app.ai_analyzed_at,
        "ai_criteria_version": app.ai_criteria_version,
        "ai_stale": stale,
        "ai_error": app.ai_error,
        "ai_reasons": _parse_reasons(app.ai_reasons_json),
    }
