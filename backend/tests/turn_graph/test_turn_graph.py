"""면접장 꼬리질문 그래프(app/services/turn_graph.py) 내부 테스트 — DB/LLM 서버 없이 분기 전체를 검증한다.
실행: DATABASE_URL, JWT_SECRET_KEY 환경변수 필요(설정 객체 로딩용, 실제 접속은 하지 않음)."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

import pytest

from tests.turn_graph import stubs

stubs.install()

from app.models.question import QuestionCategory  # noqa: E402
from app.services import interview_prompts, langchain_orchestrator, turn_graph  # noqa: E402
from app.services.llm_engine import LlmGenerationError, TurnLLMOutput  # noqa: E402
from app.worker import tasks  # noqa: E402

GOOD = "그 경험에서 가장 어려웠던 점은 무엇이었나요?"
GOOD2 = "그 문제를 팀과 어떻게 해결하셨는지 설명해 주세요."
BAD_NOT_QUESTION = "알겠습니다 감사합니다"  # 질문형 아님
BAD_PLACEHOLDER = "[이름]님은 어떤 경험이 있나요?"  # 플레이스홀더
BAD_LEAK = "저는 시니어 기술 면접관입니다 어떻게 생각하나요?"  # 시스템 프롬프트 유출 마커
FALLBACK_TEXT = "답변 감사합니다. 다음 질문으로 넘어가겠습니다."


def _q(content: str):
    return SimpleNamespace(id="q-" + content[:3], content=content, category=QuestionCategory.technical)


class FakeRetriever(turn_graph.QuestionBankRetriever):
    """DB 없이 후보를 고정 반환한다(Retriever 인터페이스 자체는 진짜)."""

    fixed: list = []

    def _get_relevant_documents(self, query, *, run_manager=None):
        self.last_questions = list(self.fixed)
        return []


def _run(outputs, candidates=None, leak_sink=None):
    """outputs: 생성 호출마다 순서대로 반환할 값(문자열=TurnLLMOutput, 예외=발생)."""
    seq = list(outputs)
    calls = []

    def generate(system_prompt, user_message):
        calls.append((system_prompt, user_message))
        item = seq.pop(0)
        if isinstance(item, Exception):
            raise item
        return TurnLLMOutput(speak_text=item, control="none")

    retriever = FakeRetriever(db=None)
    retriever.fixed = candidates if candidates is not None else [_q("MSA 전환 시 어려움은?")]
    graph = turn_graph.build_followup_graph(
        retriever=retriever,
        generate=generate,
        on_persona_leak=(leak_sink.append if leak_sink is not None else (lambda t: None)),
        turn_fallback_text=FALLBACK_TEXT,
    )
    final = graph.invoke({"query_text": "답변", "user_message": "[대화 이력]\n...", "trace": []})
    return final, calls


def test_tc01_pass_first_try():
    final, calls = _run([GOOD])
    assert final["output"].speak_text == GOOD
    assert final["trace"] == ["retrieve", "generate", "validate"]
    assert final["generations"] == 1 and not final.get("used_bank_fallback")
    assert len(calls) == 1


def test_tc02_retry_then_pass():
    final, _ = _run([BAD_NOT_QUESTION, GOOD2])
    assert final["output"].speak_text == GOOD2
    assert final["trace"] == ["retrieve", "generate", "validate", "generate", "validate"]
    assert final["generations"] == 2 and not final.get("used_bank_fallback")


@pytest.mark.parametrize("bad", [BAD_NOT_QUESTION, BAD_PLACEHOLDER, BAD_LEAK])
def test_tc03_retry_exhausted_bank_fallback(bad):
    cand = [_q("분산 트랜잭션 정합성은 어떻게 보장했나요?")]
    final, calls = _run([bad, bad], candidates=cand)
    assert final["output"].speak_text == cand[0].content
    assert final["output"].control == "next_question"
    assert final["used_bank_fallback"] is True and final["generations"] == 2
    assert final["trace"][-1] == "bank_fallback"
    assert len(calls) == 2  # 3번째 생성은 절대 일어나지 않는다


def test_tc04_retry_exhausted_no_candidates_uses_fixed_text():
    final, _ = _run([BAD_NOT_QUESTION, BAD_NOT_QUESTION], candidates=[])
    assert final["output"].speak_text == FALLBACK_TEXT
    assert final["output"].control == "next_question"


def test_tc05_llm_failure_safe_default_keeps_candidates():
    cand = [_q("CI/CD 개선 경험을 설명해 주세요.")]
    final, calls = _run([LlmGenerationError("서버 다운")], candidates=cand)
    assert final["output"].speak_text == FALLBACK_TEXT
    assert final["llm_failed"] is True
    assert final["candidates"] == cand  # question_id 기록용 후보 유지(기존 동작과 동일)
    assert "validate" not in final["trace"] and len(calls) == 1


def test_tc06_llm_failure_on_retry_goes_safe_default():
    final, _ = _run([BAD_NOT_QUESTION, LlmGenerationError("타임아웃")])
    assert final["output"].speak_text == FALLBACK_TEXT and final["llm_failed"] is True


def test_tc07_persona_leak_audit_each_failed_attempt():
    sink: list[str] = []
    _run([BAD_LEAK, BAD_LEAK], leak_sink=sink)
    assert sink == [BAD_LEAK, BAD_LEAK]
    sink2: list[str] = []
    _run([BAD_NOT_QUESTION, GOOD], leak_sink=sink2)
    assert sink2 == []  # 유출 마커가 아닌 실패는 감사 로그 대상 아님(기존 동작)


def test_tc08_prompt_gets_candidates_read_only():
    cand = [_q("테스트 커버리지 기준은 무엇인가요?")]
    _, calls = _run([GOOD], candidates=cand)
    system_prompt, user_message = calls[0]
    assert cand[0].content in system_prompt
    assert system_prompt == interview_prompts.build_followup_system_prompt(cand)
    assert user_message.startswith("[대화 이력]")


# --- 기존 경로(_generate_validated_followup)와 분기 동등성 ---------------------------------
SCENARIOS = {
    "pass": [GOOD],
    "retry_pass": [BAD_NOT_QUESTION, GOOD2],
    "exhausted": [BAD_PLACEHOLDER, BAD_LEAK],
}


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_tc09_equivalent_to_legacy(name, monkeypatch):
    import uuid

    cand = [_q("장애 원인 파악에 쓴 모니터링 체계는 무엇인가요?")]
    legacy_seq = list(SCENARIOS[name])

    def legacy_generate(system_prompt, user_message):
        return TurnLLMOutput(speak_text=legacy_seq.pop(0), control="none")

    monkeypatch.setattr(tasks, "generate_turn_response", legacy_generate)
    legacy = tasks._generate_validated_followup(uuid.uuid4(), "sys", "usr", cand)
    graph_final, _ = _run(SCENARIOS[name], candidates=cand)
    assert graph_final["output"].speak_text == legacy.speak_text
    assert graph_final["output"].control == legacy.control


def test_tc10_legacy_llm_failure_equivalent(monkeypatch):
    """LLM 실패 시: 기존은 tasks 의 except 가 고정 문구를 쓴다 — 그래프도 같은 문구/컨트롤."""
    final, _ = _run([LlmGenerationError("x")])
    assert (final["output"].speak_text, final["output"].control) == (FALLBACK_TEXT, "next_question")
    assert tasks._TURN_FALLBACK_TEXT == FALLBACK_TEXT


# --- LangChain 생성 함수 ----------------------------------------------------------------
class _FakeLLM:
    def __init__(self, items):
        self.items = list(items)
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(content=item)


def _patch_llm(monkeypatch, items):
    llm = _FakeLLM(items)
    monkeypatch.setattr(langchain_orchestrator, "_get_chat_model", lambda: llm)
    return llm


def test_tc11_langchain_ok(monkeypatch):
    llm = _patch_llm(monkeypatch, [json.dumps({"speak_text": GOOD, "control": "none"}, ensure_ascii=False)])
    out = langchain_orchestrator.generate_turn_via_langchain("s", "u")
    assert out.speak_text == GOOD and llm.calls == 1


def test_tc12_langchain_parse_retry_then_ok(monkeypatch):
    llm = _patch_llm(monkeypatch, ["이건 JSON 이 아님", json.dumps({"speak_text": GOOD})])
    assert langchain_orchestrator.generate_turn_via_langchain("s", "u").speak_text == GOOD
    assert llm.calls == 2


def test_tc13_langchain_parse_exhausted_raises_llm_error(monkeypatch):
    llm = _patch_llm(monkeypatch, ["{}", '{"speak_text": "   "}'])
    with pytest.raises(LlmGenerationError):
        langchain_orchestrator.generate_turn_via_langchain("s", "u")
    assert llm.calls == 2


def test_tc14_langchain_call_error_raises_llm_error_without_retry(monkeypatch):
    llm = _patch_llm(monkeypatch, [RuntimeError("연결 거부")])
    with pytest.raises(LlmGenerationError):
        langchain_orchestrator.generate_turn_via_langchain("s", "u")
    assert llm.calls == 1


def test_tc15_langchain_non_str_content_is_parse_failure(monkeypatch):
    _patch_llm(monkeypatch, [[{"type": "text"}], json.dumps({"speak_text": GOOD})])
    assert langchain_orchestrator.generate_turn_via_langchain("s", "u").speak_text == GOOD


# --- 실제 HTTP: 가짜 llama-server 를 띄워 ChatOpenAI 의 실제 요청 형식을 검증 -----------------
class _Handler(BaseHTTPRequestHandler):
    received: list = []
    replies: list = []

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Handler.received.append((self.path, body))
        content = _Handler.replies.pop(0)
        payload = json.dumps(
            {
                "id": "x",
                "object": "chat.completion",
                "created": 0,
                "model": "local-gguf",
                "choices": [
                    {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
            ensure_ascii=False,
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *a):  # 조용히
        pass


@pytest.fixture
def fake_llama_server(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _Handler.received, _Handler.replies = [], []
    monkeypatch.setattr(langchain_orchestrator, "_SERVER_PORT", server.server_address[1])
    monkeypatch.setattr(langchain_orchestrator, "_ensure_server_running", lambda: None)
    yield _Handler
    server.shutdown()


def test_tc16_langchain_real_http_wire_format(fake_llama_server):
    fake_llama_server.replies = [json.dumps({"speak_text": GOOD, "control": "none"}, ensure_ascii=False)]
    out = langchain_orchestrator.generate_turn_via_langchain("시스템 프롬프트", "사용자 메시지")
    assert out.speak_text == GOOD
    path, body = fake_llama_server.received[0]
    assert path == "/v1/chat/completions"
    assert body["messages"][0] == {"role": "system", "content": "시스템 프롬프트"}  # role 분리 유지(인젝션 방어)
    assert body["messages"][1] == {"role": "user", "content": "사용자 메시지"}
    assert body["response_format"] == {"type": "json_object"}
    assert body["max_tokens"] == 300 and body["temperature"] == 0.6
    assert "max_completion_tokens" not in body  # llama-server 가 무시할 수 있는 키는 보내지 않는다


def test_tc17_graph_with_real_http_end_to_end(fake_llama_server):
    """그래프 + LangChain + (가짜 llama-server HTTP) 전 구간: 1차 무효 → 재시도 유효."""
    fake_llama_server.replies = [
        json.dumps({"speak_text": BAD_NOT_QUESTION}, ensure_ascii=False),
        json.dumps({"speak_text": GOOD2}, ensure_ascii=False),
    ]
    retriever = FakeRetriever(db=None)
    retriever.fixed = [_q("협업 중 갈등 해결 경험은?")]
    graph = turn_graph.build_followup_graph(
        retriever=retriever,
        generate=langchain_orchestrator.generate_turn_via_langchain,
        on_persona_leak=lambda t: None,
        turn_fallback_text=FALLBACK_TEXT,
    )
    final = graph.invoke({"query_text": "q", "user_message": "u", "trace": []})
    assert final["output"].speak_text == GOOD2 and len(fake_llama_server.received) == 2


# --- 설정 스위치 --------------------------------------------------------------------------
def test_tc18_settings_switch_validation(monkeypatch):
    from pydantic import ValidationError

    from app.core.config import Settings

    monkeypatch.setenv("LLM_ORCHESTRATION", "legacy")
    assert Settings().llm_orchestration == "legacy"
    monkeypatch.setenv("LLM_ORCHESTRATION", "banana")
    with pytest.raises(ValidationError):
        Settings()
    monkeypatch.delenv("LLM_ORCHESTRATION")
    assert Settings().llm_orchestration == "graph"
