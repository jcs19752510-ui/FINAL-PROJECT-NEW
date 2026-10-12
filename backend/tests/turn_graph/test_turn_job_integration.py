"""`process_turn_job`(Celery 태스크) 통합 테스트 — 실제 PostgreSQL(전체 마이그레이션 적용) + 그래프/기존 경로 양쪽.
LLM 서버·TTS·Redis 발행만 가짜로 바꾼다. 사전 조건: `alembic upgrade head` 완료된 DB, DATABASE_URL, JWT_SECRET_KEY."""
import uuid

import pytest
from sqlalchemy import text

from tests.turn_graph import stubs

stubs.install()

from app.db.session import SessionLocal  # noqa: E402
from app.models.question import Question, QuestionCategory, QuestionSource  # noqa: E402
from app.models.transcript import Transcript  # noqa: E402
from app.services import langchain_orchestrator, rag_engine  # noqa: E402
from app.services.llm_engine import LlmGenerationError, TurnLLMOutput  # noqa: E402
from app.worker import tasks  # noqa: E402
from tests.turn_graph.test_rag_db import fake_embed  # noqa: E402

GOOD = "그 방식을 선택한 이유는 무엇이었나요?"
FALLBACK = tasks._TURN_FALLBACK_TEXT


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(rag_engine, "embed_text", fake_embed)
    events = []
    monkeypatch.setattr(tasks, "publish_ws_event", lambda iid, ev: events.append(ev))
    monkeypatch.setattr(tasks, "synthesize_speech_file", lambda t: None)
    uid, iid = uuid.uuid4(), uuid.uuid4()
    with SessionLocal() as db:
        db.execute(text("DELETE FROM questions"))
        db.execute(text("INSERT INTO users (id,email,password_hash,role,name) VALUES (:i,:e,'x','candidate','테스트')"),
                   {"i": uid, "e": f"tg-{uid}@example.com"})
        db.execute(text("INSERT INTO interviews (id,candidate_id,status,report_status) "
                        "VALUES (:i,:c,'live','none')"), {"i": iid, "c": uid})
        q = Question(content="분산 트랜잭션 정합성은 어떻게 보장했나요?", category=QuestionCategory.technical,
                     difficulty="hard", rubric_json={}, embedding=fake_embed("트랜잭션"), source=QuestionSource.bank)
        db.add(q)
        db.flush()
        user_t = Transcript(interview_id=iid, turn_index=1, speaker="user", input_mode="text",
                            content_text="트랜잭션 정합성 문제를 겪었습니다")
        db.add(user_t)
        db.commit()
        ctx = {"iid": iid, "tid": user_t.id, "qid": q.id, "events": events}
    yield ctx
    with SessionLocal() as db:
        db.execute(text("DELETE FROM transcripts WHERE interview_id=:i"), {"i": iid})
        db.execute(text("DELETE FROM interviews WHERE id=:i"), {"i": iid})
        db.execute(text("DELETE FROM users WHERE id=:u"), {"u": uid})
        db.execute(text("DELETE FROM questions"))
        db.commit()


def _ai_row(iid):
    """ORM 으로 읽는다 — content_text 는 저장 시 암호화(v16)되어 raw SQL 로는 암호문이 보인다."""
    from app.models.transcript import Speaker

    with SessionLocal() as db:
        rows = db.query(Transcript).filter(Transcript.interview_id == iid, Transcript.speaker == Speaker.ai).all()
        return [(r.content_text, r.question_id) for r in rows]


def _run(env):
    tasks.process_turn_job.apply(args=(str(env["iid"]), str(env["tid"]))).get()


def _result_event(env):
    return [e for e in env["events"] if e["type"] == "turn_result"]


@pytest.mark.parametrize("mode", ["graph", "legacy"])
def test_job01_success_links_question_and_publishes(env, monkeypatch, mode):
    monkeypatch.setattr(tasks.settings, "llm_orchestration", mode)
    gen = lambda s, u: TurnLLMOutput(speak_text=GOOD)  # noqa: E731
    monkeypatch.setattr(langchain_orchestrator, "generate_turn_via_langchain", gen)
    monkeypatch.setattr(tasks, "generate_turn_response", gen)
    _run(env)
    rows = _ai_row(env["iid"])
    assert rows == [(GOOD, env["qid"])]
    ev = _result_event(env)
    assert len(ev) == 1 and ev[0]["ai_text"] == GOOD and not [e for e in env["events"] if e["type"] == "error"]


@pytest.mark.parametrize("mode", ["graph", "legacy"])
def test_job02_llm_failure_safe_default_keeps_question_link(env, monkeypatch, mode):
    monkeypatch.setattr(tasks.settings, "llm_orchestration", mode)

    def boom(s, u):
        raise LlmGenerationError("서버 다운")

    monkeypatch.setattr(langchain_orchestrator, "generate_turn_via_langchain", boom)
    monkeypatch.setattr(tasks, "generate_turn_response", boom)
    _run(env)
    assert _ai_row(env["iid"]) == [(FALLBACK, env["qid"])]
    assert _result_event(env)[0]["control"] == {"action": "next_question"}


@pytest.mark.parametrize("mode", ["graph", "legacy"])
def test_job03_quality_guard_exhausted_uses_bank_question(env, monkeypatch, mode):
    monkeypatch.setattr(tasks.settings, "llm_orchestration", mode)
    gen = lambda s, u: TurnLLMOutput(speak_text="알겠습니다 감사합니다")  # noqa: E731
    monkeypatch.setattr(langchain_orchestrator, "generate_turn_via_langchain", gen)
    monkeypatch.setattr(tasks, "generate_turn_response", gen)
    _run(env)
    assert _ai_row(env["iid"]) == [("분산 트랜잭션 정합성은 어떻게 보장했나요?", env["qid"])]


def test_job04_graph_mode_is_default_and_session_state_skip(env, monkeypatch):
    assert tasks.settings.llm_orchestration == "graph"
    with SessionLocal() as db:
        db.execute(text("UPDATE interviews SET status='completed' WHERE id=:i"), {"i": env["iid"]})
        db.commit()
    monkeypatch.setattr(langchain_orchestrator, "generate_turn_via_langchain", lambda s, u: TurnLLMOutput(speak_text=GOOD))
    _run(env)
    assert _ai_row(env["iid"]) == [] and env["events"] == []   # 종료된 세션은 처리 스킵(기존 동작)
