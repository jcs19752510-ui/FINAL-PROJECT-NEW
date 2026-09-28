"""AI 안전장치 (REQ-035~039, unit-27) — 2026-09-22 사용자 승인.

원 계획서에는 없고 개발 하네스 자체 보안 규칙(규칙 J)이 요구하는 항목이다.
`docs/harness/traceability.md`가 unit-8(미착수)에 배정해뒀던 5개 요구사항 중
일부를 이 유닛에서 실제로 구현한다.

**이미 충족되어 이 모듈에서 재구현하지 않는 항목(실측 확인)**:
- REQ-036(LLM 출력 새니타이즈, XSS 방지): 프론트(`frontend/app/interviews/[id]/
  page.tsx`, `.../report/page.tsx`)가 `dangerouslySetInnerHTML`을 전혀 쓰지
  않고 JSX 텍스트 보간만 사용 — React의 자동 이스케이프로 이미 충족(grep으로
  실측 확인, unit-27-note.md 참고).
- REQ-037(함수 호출 최소 권한): `app/services/llm_engine.py`의
  `TurnLLMOutput.control: Literal["next_question","end_interview",
  "switch_to_coding","none"]`이 화이트리스트 밖 값을 pydantic 검증 단계에서
  자동 거부 — 이미 충족.

**이 모듈이 실제로 새로 구현하는 것**: REQ-035(입력 측 프롬프트 인젝션 1차
탐지), REQ-038(레이트리밋). REQ-039(시스템 프롬프트 유출 방지)는 핵심 탐지
로직(`interview_prompts._PERSONA_LEAK_MARKERS`)이 이미 있어 감사 로그 기록
기능만 이 모듈에서 추가한다(`log_persona_leak_detected`).
"""
import logging
import re

import redis as redis_lib

logger = logging.getLogger(__name__)

# --- REQ-035: 프롬프트 인젝션 1차 탐지 ---------------------------------------
#
# 핵심 방어(role 분리, system/user 템플릿 렌더링)는 이미 `llm_engine.
# _call_chat_completions`가 담당한다(03-design §6.3 본문 그대로 인용됨). 이
# 패턴은 그 위에 얹는 "1차 패턴 필터링"(§6.3, "잔여 리스크" 명시된 바로 그
# 계층)이다 — 완전한 방어를 주장하지 않는다. 오탐으로 정상 답변을 막지 않도록
# 차단이 아니라 감사 로그만 남긴다(호출부가 정책을 정한다).
_INJECTION_PATTERNS = re.compile(
    r"(이전\s*(지시|명령|프롬프트)\s*(무시|잊어)"
    r"|시스템\s*프롬프트\s*(보여|알려|공개)"
    r"|지금부터\s*너는|당신은\s*이제부터"
    r"|ignore\s+(previous|above|all)\s+instructions"
    r"|reveal\s+(your\s+)?system\s+prompt"
    r"|you\s+are\s+now\s+|act\s+as\s+(a\s+)?)",
    re.IGNORECASE,
)


def detect_injection_attempt(text: str) -> bool:
    """알려진 인젝션 시도 패턴이 있으면 True. 오탐 가능성이 있으므로 이 함수의
    결과로 사용자 입력 자체를 거부하지 않는다 — 감사 로그/모니터링 용도.
    """
    return bool(_INJECTION_PATTERNS.search(text))


def log_injection_attempt(user_id: str, interview_id: str, text: str) -> None:
    if detect_injection_attempt(text):
        logger.warning(
            "프롬프트 인젝션 의심 패턴 탐지(REQ-035): user_id=%s interview_id=%s", user_id, interview_id
        )


def log_persona_leak_detected(interview_id: str, speak_text: str) -> None:
    """REQ-039 감사 로그. 실제 탐지 로직은 `interview_prompts.
    validate_followup_speak_text()`가 이미 수행한다 — 이 함수는 그 결과가
    False(품질 가드 실패, 유출 마커 포함 포함)일 때 호출부가 감사 목적으로
    남기는 로그다.
    """
    logger.warning("시스템 프롬프트 유출 의심 출력 차단(REQ-039): interview_id=%s", interview_id)


# --- REQ-038: 레이트리밋 -----------------------------------------------------
#
# 03-design §1.3 "큐 최대길이 50"과는 별개로, 이 모듈은 "세션/사용자당 분당
# LLM 호출 상한"(§6.3 "세션당/일일 상한")을 담당한다. 고정 윈도우 카운터
# (Redis INCR+EXPIRE) — 슬라이딩 윈도우보다 정확도는 낮지만 구현이 단순하고
# 원자적(INCR은 Redis에서 원자 연산)이라 동시 요청 경쟁 상태가 없다.
#
# **키를 interview_id가 아닌 user_id로 둔 이유(2026-09-22 실측 재검토)**:
# `app/api/v1/interviews.py`에 이미 "인터뷰 세션당 지원자 턴 최대 5회"라는
# 별개의 비즈니스 규칙(`MAX_CANDIDATE_TURNS`, 2026-09-21 사용자 요청)이 있다.
# interview_id 단위로 분당 상한을 걸면 그 5회 제한이 항상 먼저 걸려 이 레이트
# 리밋이 사실상 절대 발동하지 않는다(실측으로 확인). user_id 단위로 두면
# "새 세션을 계속 만들어 5턴씩 반복 제출"하는 우회를 실제로 막을 수 있어
# 원안(§6.3 "세션당/일일 상한")의 취지에 더 부합한다.
_RATE_LIMIT_WINDOW_SECONDS = 60
_RATE_LIMIT_MAX_REQUESTS = 10  # 사용자당 분당 LLM 트리거 턴 상한(구현 세부값, 비가역성 낮음)

_redis_client: "redis_lib.Redis | None" = None


def _get_redis() -> "redis_lib.Redis":
    global _redis_client
    if _redis_client is None:
        from app.core.config import settings  # 지연 임포트 — 순환 임포트 방지

        _redis_client = redis_lib.Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


class RateLimitExceeded(Exception):
    """호출부(app/api/v1/interviews.py)가 429 RATE_LIMIT_EXCEEDED로 매핑한다."""


def check_and_increment_turn_rate_limit(user_id: str) -> None:
    """사용자(user_id) 단위로 분당 턴 제출 횟수를 센다. 한도 초과 시
    `RateLimitExceeded`를 낸다 — 카운터 증가 자체는 항상 수행된다(요청이
    막히더라도 그 시도 자체는 카운트에 반영되어야 우회를 못 함).
    """
    key = f"rate_limit:llm_turn:{user_id}"
    redis = _get_redis()
    count = redis.incr(key)
    if count == 1:
        redis.expire(key, _RATE_LIMIT_WINDOW_SECONDS)
    if count > _RATE_LIMIT_MAX_REQUESTS:
        raise RateLimitExceeded(
            f"분당 {_RATE_LIMIT_MAX_REQUESTS}회 제한을 초과했습니다. 잠시 후 다시 시도해주세요."
        )


# unit-36(STT 실시간 스트리밍 미리보기, 2026-09-23 사용자 승인): 위 `_RATE_LIMIT_
# MAX_REQUESTS`(분당 10회)는 LLM을 트리거하는 "정식 턴"용이다. 미리보기는 클라이언트가
# 약 4초 간격(§ 프런트 구현)으로 짧은 오디오 조각을 계속 보내므로, 정식 턴과 같은
# 한도를 쓰면 답변 1개(약 30~60초) 도중에 바로 429가 난다. LLM을 부르지 않고
# STT(faster-whisper, CPU)만 도는 더 가벼운 작업이라 상한을 넉넉히 두되, 무제한은
# 아니다(자원 고갈 방지) — 최소 4초 간격을 전제로 여유를 더한 값.
_PREVIEW_RATE_LIMIT_MAX_REQUESTS = 20


def check_and_increment_preview_rate_limit(user_id: str) -> None:
    """STT 미리보기 전용 분당 상한 — `check_and_increment_turn_rate_limit`과
    독립된 별도 Redis 키를 쓴다(정식 턴 한도를 갉아먹지 않기 위함)."""
    key = f"rate_limit:stt_preview:{user_id}"
    redis = _get_redis()
    count = redis.incr(key)
    if count == 1:
        redis.expire(key, _RATE_LIMIT_WINDOW_SECONDS)
    if count > _PREVIEW_RATE_LIMIT_MAX_REQUESTS:
        raise RateLimitExceeded(
            f"실시간 인식 요청이 분당 {_PREVIEW_RATE_LIMIT_MAX_REQUESTS}회 상한을 초과했습니다."
        )


# unit-29 후속(2026-09-24, 사용자 승인 — 신뢰할 수 없는 코드를 실제로 실행하는
# 기능이라 다른 두 한도보다 훨씬 보수적으로 잡는다): 매 요청이 Docker 컨테이너
# 기동(수백ms~수초)을 유발해 LLM 턴(10/분)보다 훨씬 무겁고, 격리가 뚫렸을 때의
# 피해 반경도 더 크다 — fork bomb류 자원고갈 시도를 반복 제출로 우회하지 못하게
# 분당 5회로 제한한다(구현 세부값, 필요 시 09단계 보안감사에서 재조정).
_SANDBOX_RATE_LIMIT_MAX_REQUESTS = 5


def check_and_increment_sandbox_rate_limit(user_id: str) -> None:
    """코드 샌드박스 실행 전용 분당 상한 — 다른 두 한도와 독립된 Redis 키."""
    key = f"rate_limit:code_sandbox:{user_id}"
    redis = _get_redis()
    count = redis.incr(key)
    if count == 1:
        redis.expire(key, _RATE_LIMIT_WINDOW_SECONDS)
    if count > _SANDBOX_RATE_LIMIT_MAX_REQUESTS:
        raise RateLimitExceeded(
            f"코드 실행 요청이 분당 {_SANDBOX_RATE_LIMIT_MAX_REQUESTS}회 상한을 초과했습니다."
        )
