"""AI 면접관의 정중한 개입(끼어들기) 판정 — 원본 계획서 REQ-F-003 (2026-10-12).

"지원자의 답변이 너무 길어지거나 주제를 벗어날 경우 AI 면접관이 정중하게 개입하여 다음 질문으로 넘어간다."

두 가지 사유를 판정한다.
- `too_long`: 답변 경과 시간이 최대 답변 시간을 넘음.
- `off_topic`: 답변이 충분히 길어진 뒤에도 **질문과의 임베딩 코사인 유사도가 임계치 미만인 상태가
  연속 N회 미리보기**에서 지속됨(히스테리시스로 한 번의 일시적 하락에 개입하지 않는다).
  유사도는 근사치이며 임계치는 기본값이다 — 실제 면접
  데이터로 보정해야 한다(설정: INTERRUPT_* 환경변수).

설계 원칙
- 판정은 **서버가 한다.** 클라이언트가 보낸 개입 주장은 최종 제출 때 서버가 길이·텍스트로
  다시 검증하고, 맞지 않으면 무시한다.
- 서버는 상태를 저장하지 않는다(연속 횟수는 클라이언트가 되돌려 보내는 `low_streak`, 최종 제출은 단독 재검증).
- 임베딩 실패 시 개입하지 않는다(안전한 쪽으로 실패). 기능 전체를 `INTERRUPTION_ENABLED=false`로 끌 수 있다.
- 개입 문구는 모델이 아니라 **서버가 붙이는 고정 문구**다(1.5B 모델의 말투에 의존하지 않음).
"""
import logging
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from app.core.config import settings
from app.services.speech_rate import count_words

logger = logging.getLogger(__name__)

InterruptReason = Literal["too_long", "off_topic"]
VALID_REASONS: tuple[str, ...] = ("too_long", "off_topic")

MAX_ELAPSED_SECONDS = 3600.0
MAX_ANSWER_CHARS = 4000
MAX_LOW_STREAK = 10
_EMBED_TAIL_CHARS = 1500  # 긴 답변은 최근 부분만 임베딩해 비용을 제한한다
_CLAIM_TOLERANCE = 0.9  # 최종 재검증 시 클라이언트 시계 오차를 허용하는 비율

POLITE_INTERRUPTION = {
    "too_long": "잠시 말씀을 끊어 죄송합니다. 답변이 충분히 전달되었으니 다음 질문으로 넘어가겠습니다.",
    "off_topic": "잠시 말씀을 끊어 죄송합니다. 질문의 핵심에 맞춰 이어가기 위해 다음 질문으로 넘어가겠습니다.",
}
# LLM에 덧붙이는 고정 진행 지시(사용자 입력이 아님)
INTERRUPT_INSTRUCTION = (
    "[진행 지시] 지원자의 답변이 길어졌거나 주제에서 벗어나 면접관이 정중히 끊었습니다. "
    "새로운 주제의 질문 하나만 하세요."
)


@dataclass(frozen=True)
class InterruptConfig:
    enabled: bool = True
    max_answer_seconds: float = 120.0
    off_topic_min_seconds: float = 30.0
    off_topic_min_words: int = 25
    off_topic_similarity: float = 0.15
    off_topic_consecutive: int = 2


@dataclass(frozen=True)
class InterruptDecision:
    should_interrupt: bool
    reason: str | None = None
    similarity: float | None = None


NO_INTERRUPT = InterruptDecision(False)


def config_from_settings() -> InterruptConfig:
    return InterruptConfig(
        enabled=settings.interruption_enabled,
        max_answer_seconds=settings.interrupt_max_answer_seconds,
        off_topic_min_seconds=settings.interrupt_off_topic_min_seconds,
        off_topic_min_words=settings.interrupt_off_topic_min_words,
        off_topic_similarity=settings.interrupt_off_topic_similarity,
        off_topic_consecutive=settings.interrupt_off_topic_consecutive,
    )


def _default_embed(text: str) -> list[float]:
    from app.services.rag_engine import embed_text  # 지연 import: 임베딩 모델은 처음 쓸 때만 적재

    return embed_text(text)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na > 0 and nb > 0 else 0.0


def sanitize_elapsed(value: object) -> float:
    """클라이언트가 보낸 경과 시간을 안전한 값으로 만든다(숫자 아님·NaN·음수·과대는 0 또는 상한)."""
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(v) or v < 0:
        return 0.0
    return min(v, MAX_ELAPSED_SECONDS)


def sanitize_streak(value: object) -> int:
    try:
        v = int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, min(v, MAX_LOW_STREAK))


def _similarity(question: str, answer: str, embed: Callable[[str], list[float]]) -> float | None:
    try:
        return cosine_similarity(embed(question), embed(answer[-_EMBED_TAIL_CHARS:]))
    except Exception:  # noqa: BLE001 — 임베딩 실패는 개입하지 않는 쪽으로 처리
        logger.warning("개입 판정용 임베딩 실패 — 개입하지 않음", exc_info=True)
        return None


def evaluate_preview(
    *,
    elapsed_seconds: float,
    answer_text: str,
    question_text: str | None,
    low_streak: int,
    cfg: InterruptConfig,
    embed: Callable[[str], list[float]] | None = None,
) -> tuple[InterruptDecision, int]:
    """미리보기 한 번에 대한 판정과 갱신된 연속 하락 횟수를 돌려준다."""
    if not cfg.enabled:
        return NO_INTERRUPT, 0
    if elapsed_seconds > cfg.max_answer_seconds:
        return InterruptDecision(True, "too_long"), 0
    if (
        elapsed_seconds >= cfg.off_topic_min_seconds
        and count_words(answer_text) >= cfg.off_topic_min_words
        and question_text
    ):
        sim = _similarity(question_text, answer_text, embed or _default_embed)
        if sim is None:
            return NO_INTERRUPT, low_streak
        streak = low_streak + 1 if sim < cfg.off_topic_similarity else 0
        if streak >= cfg.off_topic_consecutive:
            return InterruptDecision(True, "off_topic", sim), streak
        return InterruptDecision(False, None, sim), streak
    return NO_INTERRUPT, 0


def verify_claim(
    reason: str,
    *,
    duration_sec: object,
    answer_text: str,
    question_text: str | None,
    cfg: InterruptConfig,
    embed: Callable[[str], list[float]] | None = None,
) -> bool:
    """최종 제출 때 클라이언트의 개입 주장을 서버가 단독으로 재검증한다. 검증할 수 없으면 False."""
    if not cfg.enabled or reason not in VALID_REASONS:
        return False
    if isinstance(duration_sec, bool) or not isinstance(duration_sec, (int, float)) or not math.isfinite(duration_sec):
        return False
    if reason == "too_long":
        return duration_sec >= cfg.max_answer_seconds * _CLAIM_TOLERANCE
    # off_topic
    if duration_sec < cfg.off_topic_min_seconds * _CLAIM_TOLERANCE or not question_text:
        return False
    if count_words(answer_text) < cfg.off_topic_min_words:
        return False
    sim = _similarity(question_text, answer_text, embed or _default_embed)
    return sim is not None and sim < cfg.off_topic_similarity


def apply_polite_interruption(speak_text: str, reason: str | None, fallback_text: str) -> str:
    """개입이 확정된 턴의 AI 발화 앞에 고정 정중 문구를 붙인다. 모델 출력이 고정 폴백 문구면 중복을 피해 문구만 쓴다."""
    if reason not in POLITE_INTERRUPTION:
        return speak_text
    prefix = POLITE_INTERRUPTION[reason]
    if speak_text.strip() == fallback_text.strip():
        return prefix
    return f"{prefix} {speak_text}"
