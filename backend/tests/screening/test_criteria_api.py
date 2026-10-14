# ruff: noqa
"""이력서 AI 판정 — 면접기준 API/상태/지원자 비노출 테스트 (실제 PostgreSQL + TestClient)."""
import io
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.turn_graph import stubs

stubs.install()

from app.api.deps import get_current_user  # noqa: E402
from app.api.v1 import resumes as rs  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import job_queue  # noqa: E402
from tests.resume_personalization.pdfmaker import SAMPLE, make_pdf  # noqa: E402

BASE = "/api/v1/recruiter"
REASONS = {
    "summary": "요약",
    "criteria": [{"name": "경력", "score": 80, "evidence": "근거"}],
    "strengths": ["a"],
    "concerns": ["b"],
}


def _mk_user(db, role):
    uid = uuid.uuid4()
    db.execute(
        text("INSERT INTO users (id,email,password_hash,role,name) VALUES (:i,:e,'x',:r,:n)"),
        {"i": uid, "e": f"sc-{uid}@example.com", "r": role, "n": f"{role}-이름"},
    )
    return uid


def _detach(db, uid):
    u = db.get(User, uid)
    db.expunge(u)
    return u


@pytest.fixture
def env(monkeypatch, tmp_path):
    with SessionLocal() as db:
        db.execute(text("DELETE FROM screening_criteria"))
        rid, cid = _mk_user(db, "recruiter"), _mk_user(db, "candidate")
        db.commit()
        recruiter, cand = _detach(db, rid), _detach(db, cid)
    enq = []
    monkeypatch.setattr(job_queue, "enqueue_screening_job", lambda i: enq.append(i), raising=False)
    monkeypatch.setattr(rs, "_has_active_consent", lambda *a, **k: True)
    monkeypatch.setattr(rs, "_resume_storage_dir", lambda: str(tmp_path))
    cur = {"u": recruiter}
    app.dependency_overrides[get_current_user] = lambda: cur["u"]
    yield {
        "c": TestClient(app), "enq": enq, "rid": rid, "cid": cid,
        "as_recruiter": lambda: cur.update(u=recruiter),
        "as_candidate": lambda: cur.update(u=cand),
    }
    app.dependency_overrides.pop(get_current_user, None)
    with SessionLocal() as db:
        db.execute(text("DELETE FROM resume_applications WHERE candidate_id=:u"), {"u": cid})
        db.execute(text("DELETE FROM screening_criteria"))
        db.execute(text("DELETE FROM users WHERE id IN (:a,:b)"), {"a": rid, "b": cid})
        db.commit()


def put(env, text_="기준", th=70):
    return env["c"].put(f"{BASE}/screening-criteria", json={"criteria_text": text_, "pass_threshold": th})


def add_app(env, **cols):
    aid = uuid.uuid4()
    base = {"id": aid, "c": env["cid"]}
    names = ["id", "candidate_id", "file_path", "original_filename", "content_type", "file_size_bytes"]
    vals = [":id", ":c", "'/x.pdf'", "'r.pdf'", "'application/pdf'", "10"]
    for k, v in cols.items():
        names.append(k)
        vals.append(f":{k}")
        base[k] = v
    with SessionLocal() as db:
        db.execute(text(f"INSERT INTO resume_applications ({','.join(names)}) VALUES ({','.join(vals)})"), base)
        db.commit()
    return aid


def set_reasons(aid, raw):
    """EncryptedText 컬럼이라 ORM 으로 저장해야 암호화된다."""
    from app.models.resume_application import ResumeApplication
    with SessionLocal() as db:
        db.get(ResumeApplication, aid).ai_reasons_json = raw
        db.commit()


def detail(env, aid):
    r = env["c"].get(f"{BASE}/resumes/{aid}")
    assert r.status_code == 200, r.text
    return r.json()


def test_get_empty(env):
    r = env["c"].get(f"{BASE}/screening-criteria")
    assert r.status_code == 200
    assert r.json() == {"criteria_text": "", "pass_threshold": 70, "version": 0, "updated_at": None, "updated_by_name": None}


def test_put_create_update_and_version(env):
    r = put(env, "  기준 A  ", 60)
    assert r.status_code == 200
    j = r.json()
    assert j["criteria_text"] == "기준 A" and j["pass_threshold"] == 60 and j["version"] == 1
    assert j["updated_by_name"] == "recruiter-이름" and j["updated_at"]
    assert env["c"].get(f"{BASE}/screening-criteria").json() == j
    # 동일 내용 => 버전 유지
    assert put(env, "기준 A", 60).json()["version"] == 1
    # 텍스트 변경
    assert put(env, "기준 B", 60).json()["version"] == 2
    # 합격선만 변경
    assert put(env, "기준 B", 80).json()["version"] == 3
    with SessionLocal() as db:
        assert db.execute(text("SELECT count(*) FROM screening_criteria")).scalar() == 1


@pytest.mark.parametrize("t,th", [("", 70), ("   \n ", 70), ("x" * 4001, 70), ("ok", 0), ("ok", 101)])
def test_put_422(env, t, th):
    assert put(env, t, th).status_code == 422


def test_put_4000_ok_and_control_chars(env):
    assert put(env, "x" * 4000, 70).status_code == 200
    r = put(env, "a\x00b\x07c\nd\te", 70)
    assert r.json()["criteria_text"] == "abc\nd\te"
    assert put(env, "\x00\x01", 70).status_code == 422


def test_candidate_forbidden(env):
    env["as_candidate"]()
    aid = add_app(env)
    for r in (
        env["c"].get(f"{BASE}/screening-criteria"),
        env["c"].put(f"{BASE}/screening-criteria", json={"criteria_text": "a", "pass_threshold": 70}),
        env["c"].post(f"{BASE}/resumes/{aid}/ai-reanalyze"),
    ):
        assert r.status_code == 403 and r.json()["code"] == "AUTH_FORBIDDEN"


def test_put_resets_attempts(env):
    aid = add_app(env, ai_status="failed", ai_attempts=3)
    put(env, "a", 70)
    with SessionLocal() as db:
        assert db.execute(text("SELECT ai_attempts FROM resume_applications WHERE id=:i"), {"i": aid}).scalar() == 0
        db.execute(text("UPDATE resume_applications SET ai_attempts=2 WHERE id=:i"), {"i": aid})
        db.commit()
    put(env, "a", 70)  # 변경 없음 => 초기화 안 함
    with SessionLocal() as db:
        assert db.execute(text("SELECT ai_attempts FROM resume_applications WHERE id=:i"), {"i": aid}).scalar() == 2


def test_list_shows_threshold_used_at_analysis(env):
    """목록의 합격선은 '현재 기준'이 아니라 그 이력서를 분석할 당시의 합격선이다."""
    aid = add_app(env, ai_status="done", ai_verdict="pass", ai_score=68, ai_threshold=65, ai_criteria_version=1)
    put(env, "기준", 70)  # 현재 합격선은 70이지만 이 행은 65로 판정됨
    row = [x for x in env["c"].get(f"{BASE}/resumes").json() if x["id"] == str(aid)][0]
    assert row["ai_threshold"] == 65 and row["ai_score"] == 68 and row["ai_verdict"] == "pass"
    assert env["c"].get(f"{BASE}/resumes/{aid}").json()["ai_threshold"] == 65  # 상세와 일치
    with SessionLocal() as db:  # 미분석 상태
        db.execute(text("UPDATE resume_applications SET ai_status=NULL, ai_verdict=NULL, ai_score=NULL, ai_threshold=NULL WHERE id=:i"), {"i": aid})
        db.commit()
    row = [x for x in env["c"].get(f"{BASE}/resumes").json() if x["id"] == str(aid)][0]
    assert row["ai_threshold"] is None


def test_states_list_and_detail(env):
    aid = add_app(env, ai_status="done", ai_verdict="pass", ai_score=88, ai_threshold=70, ai_criteria_version=1)
    set_reasons(aid, json.dumps(REASONS, ensure_ascii=False))
    # no_criteria: 이전 결과 필드는 그대로
    d = detail(env, aid)
    assert d["ai_state"] == "no_criteria" and d["ai_score"] == 88 and d["current_criteria_version"] == 0
    put(env, "기준", 70)  # version 1
    d = detail(env, aid)
    assert d["ai_state"] == "done" and d["ai_verdict"] == "pass" and d["ai_stale"] is False
    assert d["ai_threshold"] == 70 and d["ai_criteria_version"] == 1 and d["ai_reasons"] == REASONS
    row = [x for x in env["c"].get(f"{BASE}/resumes").json() if x["id"] == str(aid)][0]
    assert row["ai_state"] == "done" and row["ai_score"] == 88 and row["ai_verdict"] == "pass"
    # stale
    put(env, "기준2", 70)
    d = detail(env, aid)
    assert d["ai_state"] == "pending" and d["ai_stale"] is True and d["ai_score"] == 88
    # pending (never analyzed)
    with SessionLocal() as db:
        db.execute(text("UPDATE resume_applications SET ai_status=NULL, ai_score=NULL, ai_verdict=NULL WHERE id=:i"), {"i": aid})
        db.commit()
    d = detail(env, aid)
    assert d["ai_state"] == "pending" and d["ai_stale"] is False
    # failed still retrying
    with SessionLocal() as db:
        db.execute(text("UPDATE resume_applications SET ai_status='failed', ai_attempts=2, ai_error='e' WHERE id=:i"), {"i": aid})
        db.commit()
    assert detail(env, aid)["ai_state"] == "pending"
    with SessionLocal() as db:
        db.execute(text("UPDATE resume_applications SET ai_attempts=3 WHERE id=:i"), {"i": aid})
        db.commit()
    d = detail(env, aid)
    assert d["ai_state"] == "failed" and d["ai_error"] == "e"


def test_corrupt_reasons_none(env):
    put(env, "기준", 70)
    aid = add_app(env, ai_status="done", ai_verdict="fail", ai_score=10, ai_criteria_version=1)
    for bad in ("not-json{{", "[1,2]", json.dumps({"summary": "s", "criteria": "oops"})):
        set_reasons(aid, bad)
        d = detail(env, aid)
        assert d["ai_reasons"] is None and d["ai_state"] == "done"


def test_reanalyze(env):
    missing = uuid.uuid4()
    assert env["c"].post(f"{BASE}/resumes/{missing}/ai-reanalyze").status_code == 404
    aid = add_app(env, ai_status="failed", ai_attempts=3)
    assert env["c"].post(f"{BASE}/resumes/{aid}/ai-reanalyze").status_code == 409
    put(env, "기준", 70)
    r = env["c"].post(f"{BASE}/resumes/{aid}/ai-reanalyze")
    assert r.status_code == 200 and r.json()["ai_state"] == "pending"
    assert env["enq"] == [str(aid)]
    with SessionLocal() as db:
        row = db.execute(text("SELECT ai_status, ai_attempts FROM resume_applications WHERE id=:i"), {"i": aid}).one()
        assert row[0] is None and row[1] == 0


def test_reanalyze_enqueue_failure_still_ok(env, monkeypatch):
    put(env, "기준", 70)
    aid = add_app(env)
    def boom(i): raise RuntimeError("broker down")
    monkeypatch.setattr(job_queue, "enqueue_screening_job", boom, raising=False)
    assert env["c"].post(f"{BASE}/resumes/{aid}/ai-reanalyze").status_code == 200


def _submit(env):
    return env["c"].post("/api/v1/resumes", files={"file": ("r.pdf", io.BytesIO(make_pdf(SAMPLE)), "application/pdf")})


def test_submit_enqueues_and_ai_fields_empty(env):
    env["as_candidate"]()
    r = _submit(env)
    assert r.status_code == 201
    assert not [k for k in r.json() if k.startswith("ai_")]
    assert len(env["enq"]) == 1
    with SessionLocal() as db:
        row = db.execute(text("SELECT id, ai_status, ai_score, ai_attempts FROM resume_applications WHERE candidate_id=:c"), {"c": env["cid"]}).one()
        assert row[1] is None and row[2] is None and row[3] == 0
    assert env["enq"] == [str(row[0])]
    s = env["c"].get("/api/v1/users/me/resume-status")
    assert s.status_code == 200 and not [k for k in s.json() if k.startswith("ai_")]


def test_submit_enqueue_failure_still_201(env, monkeypatch):
    env["as_candidate"]()
    def boom(i): raise RuntimeError("broker down")
    monkeypatch.setattr(job_queue, "enqueue_screening_job", boom, raising=False)
    assert _submit(env).status_code == 201


def test_candidate_status_hides_ai_even_when_analyzed(env):
    put(env, "기준", 70)
    add_app(env, ai_status="done", ai_verdict="pass", ai_score=90, ai_criteria_version=1)
    env["as_candidate"]()
    j = env["c"].get("/api/v1/users/me/resume-status").json()
    assert not [k for k in j if k.startswith("ai_")]
