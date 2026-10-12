"""원본 REQ-F-003 개입 판정(순수 로직) 테스트 — 결정적 가짜 임베더 사용, DB·모델 불필요."""
import math

import pytest

from app.services import interruption_policy as ip

CFG = ip.InterruptConfig()
Q = "분산 트랜잭션 정합성은 어떻게 보장했나요?"
LONG_ANSWER = " ".join(["단어"] * 30)  # 30 어절


def embed_same(_t: str) -> list[float]:
    return [1.0, 0.0]


_calls: list[str] = []


def embed_by_text(t: str) -> list[float]:
    # 질문은 [1,0], 답변은 질문과 직교 → 유사도 0 (주제 이탈)
    return [1.0, 0.0] if t == Q else [0.0, 1.0]


def embed_boom(_t: str) -> list[float]:
    raise RuntimeError("모델 없음")


def ev(elapsed, text=LONG_ANSWER, streak=0, cfg=CFG, embed=embed_by_text, q=Q):
    return ip.evaluate_preview(
        elapsed_seconds=elapsed, answer_text=text, question_text=q, low_streak=streak, cfg=cfg, embed=embed
    )


def test_p01_too_long_boundary():
    assert ev(119.0, embed=embed_same)[0].should_interrupt is False
    assert ev(120.0, embed=embed_same)[0].should_interrupt is False  # '초과'만 개입
    d, s = ev(120.5, embed=embed_same)
    assert d.should_interrupt and d.reason == "too_long" and s == 0


def test_p02_off_topic_needs_consecutive_hysteresis():
    d1, s1 = ev(40, streak=0)
    assert not d1.should_interrupt and s1 == 1
    d2, s2 = ev(45, streak=s1)
    assert d2.should_interrupt and d2.reason == "off_topic" and s2 == 2


def test_p03_on_topic_resets_streak():
    d, s = ev(40, streak=1, embed=embed_same)
    assert not d.should_interrupt and s == 0


def test_p04_short_or_early_answers_never_interrupt():
    assert ev(10, streak=5)[0].should_interrupt is False  # 30초 미만
    assert ev(40, text="짧은 답", streak=5)[0].should_interrupt is False  # 어절 부족
    assert ev(40, streak=5, q=None)[0].should_interrupt is False  # 질문 없음


def test_p05_disabled_never_interrupts():
    off = ip.InterruptConfig(enabled=False)
    assert ev(999, cfg=off, embed=embed_same)[0].should_interrupt is False
    assert ip.verify_claim("too_long", duration_sec=999, answer_text=LONG_ANSWER, question_text=Q, cfg=off) is False


def test_p06_embedding_failure_is_safe():
    d, s = ev(40, streak=1, embed=embed_boom)
    assert d.should_interrupt is False and s == 1


@pytest.mark.parametrize("bad", [None, "abc", float("nan"), float("inf"), -5, "", [], "x"])
def test_p07_sanitize_elapsed_bad_inputs(bad):
    v = ip.sanitize_elapsed(bad)
    assert v == 0.0 or (math.isfinite(v) and 0 <= v <= ip.MAX_ELAPSED_SECONDS)


def test_p08_sanitize_caps_and_streak():
    assert ip.sanitize_elapsed(10**9) == ip.MAX_ELAPSED_SECONDS
    assert ip.sanitize_elapsed("42.5") == 42.5
    assert ip.sanitize_streak("3") == 3
    assert ip.sanitize_streak(-4) == 0
    assert ip.sanitize_streak(10**6) == ip.MAX_LOW_STREAK
    assert ip.sanitize_streak("x") == 0


def test_p09_verify_claim_too_long():
    kw = dict(answer_text=LONG_ANSWER, question_text=Q, cfg=CFG, embed=embed_same)
    assert ip.verify_claim("too_long", duration_sec=125, **kw) is True
    assert ip.verify_claim("too_long", duration_sec=107, **kw) is False  # 120*0.9=108 미만 → 조작 의심
    assert ip.verify_claim("too_long", duration_sec=None, **kw) is False
    assert ip.verify_claim("too_long", duration_sec=True, **kw) is False
    assert ip.verify_claim("too_long", duration_sec=float("nan"), **kw) is False


def test_p10_verify_claim_off_topic_and_invalid_reason():
    base = dict(duration_sec=40, answer_text=LONG_ANSWER, question_text=Q, cfg=CFG)
    assert ip.verify_claim("off_topic", embed=embed_by_text, **base) is True
    assert ip.verify_claim("off_topic", embed=embed_same, **base) is False  # 주제에 맞는 답
    assert ip.verify_claim("off_topic", embed=embed_boom, **base) is False
    assert ip.verify_claim("off_topic", embed=embed_by_text, **{**base, "duration_sec": 5}) is False
    assert ip.verify_claim("off_topic", embed=embed_by_text, **{**base, "answer_text": "짧음"}) is False
    assert ip.verify_claim("hack", embed=embed_by_text, **base) is False


def test_p11_apply_polite_interruption():
    fb = "답변 감사합니다. 다음 질문으로 넘어가겠습니다."
    out = ip.apply_polite_interruption("그 방식을 선택한 이유는요?", "too_long", fb)
    assert out.startswith(ip.POLITE_INTERRUPTION["too_long"]) and out.endswith("선택한 이유는요?")
    assert ip.apply_polite_interruption(fb, "off_topic", fb) == ip.POLITE_INTERRUPTION["off_topic"]
    assert ip.apply_polite_interruption("원문", None, fb) == "원문"
    assert ip.apply_polite_interruption("원문", "bogus", fb) == "원문"


def test_p12_cosine_edge():
    assert ip.cosine_similarity([0, 0], [1, 0]) == 0.0
    assert ip.cosine_similarity([1, 0], [1, 0]) == pytest.approx(1.0)
