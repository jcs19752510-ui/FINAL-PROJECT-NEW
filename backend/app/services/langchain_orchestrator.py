"""LangChain 기반 LLM 오케스트레이션 — 원안(§4.2 "LangChain을 이용한 면접관
페르소나 구현, 대화 상태 관리") 검증용 모듈, 2026-09-22 사용자 승인(unit-26).

**중요 — 이 모듈은 운영 중인 턴 처리 파이프라인(`app/worker/tasks.py` →
`app/services/llm_engine.py`)을 대체하지 않는다.** `llm_engine.py`는 오늘
(2026-09-22) 실제 음성 제출 장애가 있었던 코드와 같은 파일 내에서 이미 11건의
실측 결함(unit-7-test.md DEF-001~011)을 거쳐 안정화됐다 — 검증 안 된 프레임워크
전환으로 그 안정성을 걸 이유가 없다고 판단해(③ 매트릭스 근거란 "실익 낮음"과
동일 결론), **동등 기능을 내는 별도 모듈**로 LangChain을 실제로 사용해 검증만
하고, 운영 파이프라인은 그대로 둔다. 실제 전환 여부는 별도 결정 필요(인수인계,
`unit-26-note.md` 참고).

**재사용 원칙**: llama-server 기동/헬스체크/GPU→CPU 폴백이라는 까다로운 로직
(`llm_engine._ensure_server_running`)을 다시 구현하지 않고 그대로 재사용한다 —
그 로직 자체가 실측 결함(DEF-009 이중바인드 등)을 거쳐 다듬어진 코드라 복제하면
같은 결함을 다시 만들 위험이 있다.
"""
import json
import logging
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, ValidationError

from app.services.llm_engine import (
    _SERVER_PORT,
    _ensure_server_running,  # 의도적 재사용, 모듈 docstring 참고
)

logger = logging.getLogger(__name__)

_GENERATION_TIMEOUT_SECONDS = 25  # llm_engine.py와 동일 예산(§5.4)
_MAX_RETRIES = 1  # llm_engine.py의 "구조화 출력 파싱 실패 시 1회 재시도"와 동일 원칙


class LangChainOrchestrationError(Exception):
    """서버 연결 실패, 구조화 출력 파싱 재시도 소진 등을 단일 계약으로 승격한다
    (llm_engine.LlmGenerationError와 동일 원칙)."""


class LangChainTurnOutput(BaseModel):
    """`llm_engine.TurnLLMOutput`과 동일한 최소 계약(§4.4) — 이 모듈이 실제로
    llm_engine.py와 동등한 구조화 출력을 낼 수 있음을 증명하는 것이 목적이라
    필드 이름/제약을 의도적으로 맞췄다.
    """

    speak_text: str = Field(min_length=1)
    control: Literal["next_question", "end_interview", "switch_to_coding", "none"] = "none"


def _get_chat_model() -> ChatOpenAI:
    """llama-server의 OpenAI 호환 엔드포인트를 LangChain의 `ChatOpenAI`로 감싼다.

    `with_structured_output()`(도구 호출 기반)은 llama-server의 OpenAI 호환 계층이
    함수 호출을 완전히 지원하지 않을 수 있어(미검증 리스크) 쓰지 않는다. 대신
    llm_engine.py가 이미 실측으로 검증한 것과 동일한 방식(JSON 모드 +
    수동 Pydantic 파싱)을 그대로 따른다 — 검증된 패턴 재사용.
    """
    _ensure_server_running()
    return ChatOpenAI(
        base_url=f"http://127.0.0.1:{_SERVER_PORT}/v1",
        api_key="local-llama-server-no-auth-required",  # 로컬 서버는 인증 불필요, SDK 필수 필드라 더미 채움
        model="local-gguf",  # llama-server는 이 값을 무시하지만 OpenAI 클라이언트 스펙상 필수
        temperature=0.6,
        max_tokens=300,
        timeout=_GENERATION_TIMEOUT_SECONDS,
        model_kwargs={"response_format": {"type": "json_object"}},
    )


def _parse_output(raw_content: str) -> LangChainTurnOutput:
    data = json.loads(raw_content)
    return LangChainTurnOutput(**data)


def generate_followup_via_langchain(system_prompt: str, user_message: str) -> LangChainTurnOutput:
    """`llm_engine.generate_turn_response()`와 동일한 입출력 계약을 LangChain으로
    구현한다. 실패 시 1회 재시도 후 `LangChainOrchestrationError`를 낸다(llm_engine.py
    의 재시도 원칙과 동일 — 검증된 패턴이라 그대로 따름).
    """
    llm = _get_chat_model()
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_message)]

    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = llm.invoke(messages)
            return _parse_output(response.content)
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = exc
            logger.warning("LangChain 구조화 출력 파싱 실패(%d/%d회) — 재시도", attempt + 1, _MAX_RETRIES + 1)
        except Exception as exc:  # noqa: BLE001 — langchain_openai/httpx의 다양한 하위 예외를 단일 계약으로 승격
            raise LangChainOrchestrationError("LangChain 오케스트레이션 호출에 실패했습니다.") from exc

    raise LangChainOrchestrationError("구조화 출력 파싱에 반복 실패했습니다.") from last_error
