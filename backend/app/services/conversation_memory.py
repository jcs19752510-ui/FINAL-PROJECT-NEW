"""면접 대화 이력을 LangChain 메모리(`InMemoryChatMessageHistory`)로 관리한다 (원본 계획서 REQ-F-001의
"LangChain 메모리", 2026-10-12).

DB의 TRANSCRIPTS(정본)에서 최근 N턴을 읽어 LangChain 메시지(면접관=AIMessage, 지원자=HumanMessage)로
적재하고, LLM 프롬프트의 `[대화 이력]` 줄을 만든다. **출력 문자열은 기존 방식과 동일**하다(줄 형식·길이
자르기 규칙 불변) — 따라서 프롬프트와 모델 입력이 바뀌지 않아 기존 품질 가드·재시도·폴백 동작에 영향이 없다.
정본은 계속 DB이며, 이 메모리 객체는 요청마다 새로 만들어지고 프로세스 상태를 갖지 않는다.

요약 메모리(오래된 대화를 LLM으로 요약)는 쓰지 않는다 — 1.5B 모델의 요약 품질과 추가 지연이 위험이라
창(window) 방식만 적용한다.
"""

from collections.abc import Callable, Sequence

from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.models.transcript import Speaker

_ROLE_LABEL = {AIMessage: "면접관", HumanMessage: "지원자"}


def build_memory(
    transcripts: Sequence,
    *,
    truncate: Callable[[str, int], str],
    max_chars: int,
    window: int,
) -> InMemoryChatMessageHistory:
    """오래된 순서의 transcripts에서 최근 `window`개만 메모리에 적재한다(각 줄은 `max_chars`로 자름)."""
    memory = InMemoryChatMessageHistory()
    recent = list(transcripts)[-window:] if window > 0 else []
    for t in recent:
        content = truncate(t.content_text, max_chars)
        memory.add_message(AIMessage(content=content) if t.speaker == Speaker.ai else HumanMessage(content=content))
    return memory


def render_lines(messages: Sequence[BaseMessage]) -> list[str]:
    return [f"{_ROLE_LABEL[type(m)]}: {m.content}" for m in messages]


def history_lines(
    transcripts: Sequence,
    max_chars: int,
    truncate: Callable[[str, int], str],
    *,
    window: int,
) -> list[str]:
    """프롬프트의 `[대화 이력]`에 들어갈 줄 목록(오래된 순)."""
    memory = build_memory(transcripts, truncate=truncate, max_chars=max_chars, window=window)
    return render_lines(memory.messages)
