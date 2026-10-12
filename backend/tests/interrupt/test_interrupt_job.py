# ruff: noqa: F811
"""REQ-F-003: process_turn_job 이 개입 턴에 고정 정중 문구를 붙이는지 — 실제 PostgreSQL, LLM·TTS·발행만 가짜."""
import pytest

from tests.turn_graph import stubs

stubs.install()

from app.services import interruption_policy as ip  # noqa: E402
from app.services import langchain_orchestrator  # noqa: E402
from app.services.llm_engine import LlmGenerationError, TurnLLMOutput  # noqa: E402
from app.worker import tasks  # noqa: E402
from tests.turn_graph.test_turn_job_integration import GOOD, _ai_row, env  # noqa: E402,F401


def _run(env, reason=None):
    args = (str(env["iid"]), str(env["tid"])) + ((reason,) if reason else ())
    tasks.process_turn_job.apply(args=args).get()


@pytest.mark.parametrize("mode", ["graph", "legacy"])
@pytest.mark.parametrize("reason", ["too_long", "off_topic"])
def test_j01_prefix_and_next_question(env, monkeypatch, mode, reason):
    monkeypatch.setattr(tasks.settings, "llm_orchestration", mode)
    seen = []

    def gen(s, u):
        seen.append(u)
        return TurnLLMOutput(speak_text=GOOD)

    monkeypatch.setattr(langchain_orchestrator, "generate_turn_via_langchain", gen)
    monkeypatch.setattr(tasks, "generate_turn_response", gen)
    _run(env, reason)
    text = _ai_row(env["iid"])[0][0]
    assert text == f"{ip.POLITE_INTERRUPTION[reason]} {GOOD}"
    assert any(ip.INTERRUPT_INSTRUCTION in u for u in seen)
    ev = [e for e in env["events"] if e["type"] == "turn_result"][0]
    assert ev["control"] == {"action": "next_question"} and ev["ai_text"] == text


def test_j02_without_reason_unchanged(env, monkeypatch):
    seen = []
    gen = lambda s, u: (seen.append(u), TurnLLMOutput(speak_text=GOOD))[1]  # noqa: E731
    monkeypatch.setattr(langchain_orchestrator, "generate_turn_via_langchain", gen)
    _run(env)
    assert _ai_row(env["iid"])[0][0] == GOOD
    assert not any(ip.INTERRUPT_INSTRUCTION in u for u in seen)


def test_j03_llm_failure_fallback_not_duplicated(env, monkeypatch):
    def boom(s, u):
        raise LlmGenerationError("다운")

    monkeypatch.setattr(langchain_orchestrator, "generate_turn_via_langchain", boom)
    _run(env, "too_long")
    assert _ai_row(env["iid"])[0][0] == ip.POLITE_INTERRUPTION["too_long"]


def test_j04_unknown_reason_ignored(env, monkeypatch):
    monkeypatch.setattr(
        langchain_orchestrator, "generate_turn_via_langchain", lambda s, u: TurnLLMOutput(speak_text=GOOD)
    )
    _run(env, "hack")
    assert _ai_row(env["iid"])[0][0] == GOOD
