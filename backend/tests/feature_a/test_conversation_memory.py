"""LangChain 메모리(app/services/conversation_memory.py) 내부 테스트.
핵심: 기존 `[대화 이력]` 줄 생성 방식과 **출력이 정확히 같다**(프롬프트 불변 → 품질 가드·폴백 영향 없음)."""

import random
from types import SimpleNamespace

import pytest
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import AIMessage, HumanMessage

from app.models.transcript import Speaker
from app.services import conversation_memory as cm

MAX_CHARS = 300


def truncate(text: str, max_chars: int) -> str:
    """tasks._truncate_for_llm 과 같은 규칙(길면 자르고 접미사)."""
    return text if len(text) <= max_chars else text[:max_chars] + "…(이하 생략)"


def legacy_lines(history):
    """변경 전 tasks.py의 구현을 그대로 복제한 기준."""
    return [
        f"{'면접관' if t.speaker == Speaker.ai else '지원자'}: {truncate(t.content_text, MAX_CHARS)}" for t in history
    ]


def turn(speaker, text):
    return SimpleNamespace(speaker=speaker, content_text=text)


def test_cm01_equivalent_to_legacy_formatting_basic():
    history = [
        turn(Speaker.ai, "자기소개 해주세요."),
        turn(Speaker.user, "저는 개발자입니다."),
        turn(Speaker.ai, "MSA 경험은요?"),
    ]
    assert cm.history_lines(history, MAX_CHARS, truncate, window=8) == legacy_lines(history)


def test_cm02_equivalent_with_long_text_truncation():
    history = [
        turn(Speaker.user, "가" * 1000),
        turn(Speaker.ai, "나" * MAX_CHARS),
        turn(Speaker.user, "다" * (MAX_CHARS + 1)),
    ]
    out = cm.history_lines(history, MAX_CHARS, truncate, window=8)
    assert out == legacy_lines(history)
    assert out[0].endswith("…(이하 생략)") and out[2].endswith("…(이하 생략)") and not out[1].endswith("…(이하 생략)")


def test_cm03_equivalent_on_randomized_conversations():
    rng = random.Random(7)
    for _ in range(50):
        history = [
            turn(
                rng.choice([Speaker.ai, Speaker.user]),
                "".join(rng.choice("가나다라 abc,.?\n") for _ in range(rng.randint(1, 500))),
            )
            for _ in range(rng.randint(0, 8))
        ]
        assert cm.history_lines(history, MAX_CHARS, truncate, window=8) == legacy_lines(history)


def test_cm04_window_keeps_only_most_recent_messages_in_order():
    history = [turn(Speaker.ai if i % 2 == 0 else Speaker.user, f"문장{i}") for i in range(12)]
    out = cm.history_lines(history, MAX_CHARS, truncate, window=8)
    assert len(out) == 8 and out[0].endswith("문장4") and out[-1].endswith("문장11")


def test_cm05_window_zero_or_empty_history_gives_no_lines():
    assert cm.history_lines([turn(Speaker.ai, "x")], MAX_CHARS, truncate, window=0) == []
    assert cm.history_lines([], MAX_CHARS, truncate, window=8) == []


def test_cm06_uses_real_langchain_message_types():
    memory = cm.build_memory(
        [turn(Speaker.ai, "질문"), turn(Speaker.user, "답변")], truncate=truncate, max_chars=MAX_CHARS, window=8
    )
    assert isinstance(memory, InMemoryChatMessageHistory)
    assert [type(m) for m in memory.messages] == [AIMessage, HumanMessage]
    assert [m.content for m in memory.messages] == ["질문", "답변"]


def test_cm07_each_call_builds_fresh_memory_no_shared_state():
    t = [turn(Speaker.user, "하나")]
    a = cm.build_memory(t, truncate=truncate, max_chars=MAX_CHARS, window=8)
    b = cm.build_memory(t, truncate=truncate, max_chars=MAX_CHARS, window=8)
    assert a is not b and len(a.messages) == 1 and len(b.messages) == 1


def test_cm08_unknown_message_type_would_fail_loudly_not_silently():
    with pytest.raises(KeyError):
        cm.render_lines([object.__new__(AIMessage.__mro__[1])])  # 라벨 없는 타입은 조용히 넘어가지 않는다
