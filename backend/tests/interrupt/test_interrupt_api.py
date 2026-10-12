"""REQ-F-003 API 통합 테스트 — 실제 PostgreSQL(마이그레이션 적용) + FastAPI TestClient.
STT·prosody·큐 전송·레이트리밋·동의 조회만 가짜로 바꾼다(Redis·모델 불필요).
사전 조건: `alembic upgrade head` 완료된 DB, DATABASE_URL, JWT_SECRET_KEY."""
import io
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.turn_graph import stubs

stubs.install()

from app.api.deps import get_current_user  # noqa: E402
from app.api.v1 import interviews as iv  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.transcript import Transcript  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import interruption_policy as ip  # noqa: E402

Q = "분산 트랜잭션 정합성은 어떻게 보장했나요?"
LONG = " ".join(["단어"] * 30)


def embed_by_text(t: str) -> list[float]:
    return [1.0, 0.0] if t == Q else [0.0, 1.0]


def embed_same(_t: str) -> list[float]:
    return [1.0, 0.0]


@pytest.fixture
def env(monkeypatch):
    uid, iid = uuid.uuid4(), uuid.uuid4()
    with SessionLocal() as db:
        db.execute(
            text("INSERT INTO users (id,email,password_hash,role,name) VALUES (:i,:e,'x','candidate','테스트')"),
            {"i": uid, "e": f"ir-{uid}@example.com"},
        )
        db.execute(
            text("INSERT INTO interviews (id,candidate_id,status,report_status) VALUES (:i,:c,'live','none')"),
            {"i": iid, "c": uid},
        )
        db.add(
            Transcript(interview_id=iid, turn_index=1, speaker="ai", input_mode="text", content_text=Q)
        )
        db.commit()
        user = db.get(User, uid)
        db.expunge(user)

    enqueued: list[tuple] = []
    state = {"text": LONG, "duration": 130.0}
    monkeypatch.setattr(iv, "_has_active_consent", lambda *a, **k: True)
    monkeypatch.setattr(iv, "check_and_increment_preview_rate_limit", lambda *_: None)
    monkeypatch.setattr(iv, "check_and_increment_turn_rate_limit", lambda *_: None)
    monkeypatch.setattr(iv, "_ensure_queue_not_full", lambda: None)
    monkeypatch.setattr(iv, "transcribe_audio_smart", lambda b, ct=None: state["text"])
    monkeypatch.setattr(iv, "analyze_prosody", lambda b: {"duration_sec": state["duration"]})
    monkeypatch.setattr(iv, "attach_speech_rate", lambda p, t: p)
    monkeypatch.setattr(iv, "enqueue_turn_job", lambda *a: enqueued.append(a) or "job-1")
    monkeypatch.setattr(ip, "_default_embed", embed_by_text)
    app.dependency_overrides[get_current_user] = lambda: user
    client = TestClient(app)
    yield {"c": client, "iid": iid, "enq": enqueued, "state": state}
    app.dependency_overrides.pop(get_current_user, None)
    with SessionLocal() as db:
        db.execute(text("DELETE FROM transcripts WHERE interview_id=:i"), {"i": iid})
        db.execute(text("DELETE FROM interviews WHERE id=:i"), {"i": iid})
        db.execute(text("DELETE FROM users WHERE id=:u"), {"u": uid})
        db.commit()


def _audio():
    return {"audio": ("a.webm", io.BytesIO(b"fake-audio"), "audio/webm")}


def preview(env, **data):
    return env["c"].post(f"/api/v1/interviews/{env['iid']}/turns/preview", files=_audio(), data=data)


def turn(env, **data):
    return env["c"].post(f"/api/v1/interviews/{env['iid']}/turns", files=_audio(), data=data)


def test_a01_preview_without_fields_keeps_old_shape(env):
    r = preview(env)
    assert r.status_code == 200
    assert r.json()["text"] == LONG and r.json()["interrupt"]["should_interrupt"] is False


def test_a02_preview_too_long(env):
    j = preview(env, elapsed_seconds="130", answer_so_far="앞부분").json()
    assert j["interrupt"] == {"should_interrupt": True, "reason": "too_long"}


def test_a03_preview_off_topic_needs_two_consecutive(env):
    j1 = preview(env, elapsed_seconds="40", low_streak="0").json()
    assert j1["interrupt"]["should_interrupt"] is False and j1["low_streak"] == 1
    j2 = preview(env, elapsed_seconds="45", low_streak=str(j1["low_streak"])).json()
    assert j2["interrupt"] == {"should_interrupt": True, "reason": "off_topic"}


def test_a04_preview_on_topic_never_interrupts(env, monkeypatch):
    monkeypatch.setattr(ip, "_default_embed", embed_same)
    j = preview(env, elapsed_seconds="40", low_streak="1").json()
    assert j["interrupt"]["should_interrupt"] is False and j["low_streak"] == 0


def test_a05_preview_disabled_setting(env, monkeypatch):
    monkeypatch.setattr(ip.settings, "interruption_enabled", False)
    assert preview(env, elapsed_seconds="999").json()["interrupt"]["should_interrupt"] is False


@pytest.mark.parametrize("elapsed", ["abc", "nan", "inf", "-5", "1e999"])
def test_a06_preview_bad_numbers_do_not_crash(env, elapsed):
    r = preview(env, elapsed_seconds=elapsed, low_streak="zz", answer_so_far="가" * 100000)
    assert r.status_code == 200


def test_a07_turn_invalid_reason_422(env):
    r = turn(env, interrupt_reason="hack")
    assert r.status_code == 422 and env["enq"] == []


def test_a08_turn_forged_too_long_ignored(env):
    env["state"]["duration"] = 20.0  # 실제로는 20초만 말함
    r = turn(env, interrupt_reason="too_long")
    assert r.status_code == 202 and len(env["enq"]) == 1 and len(env["enq"][0]) == 2  # 개입 인자 없음


def test_a09_turn_valid_too_long_accepted(env):
    env["state"]["duration"] = 125.0
    r = turn(env, interrupt_reason="too_long")
    assert r.status_code == 202 and env["enq"][0][2] == "too_long"


def test_a10_turn_off_topic_claim_verified_by_server(env, monkeypatch):
    env["state"]["duration"] = 40.0
    assert turn(env, interrupt_reason="off_topic").status_code == 202
    assert env["enq"][-1][2] == "off_topic"
    monkeypatch.setattr(ip, "_default_embed", embed_same)  # 사실은 주제에 맞는 답
    assert turn(env, interrupt_reason="off_topic").status_code == 202
    assert len(env["enq"][-1]) == 2


def test_a11_turn_without_field_is_unchanged(env):
    assert turn(env).status_code == 202
    assert len(env["enq"][0]) == 2
