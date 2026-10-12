# ruff: noqa: E501, E741
"""REQ-F-004 API 통합 — 실제 PostgreSQL + FastAPI TestClient. 샌드박스 실행기만 로컬 실행기로 대체(Docker 데몬 없음)."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.turn_graph import stubs

stubs.install()

from app.api.deps import get_current_user  # noqa: E402
from app.api.v1 import code_submissions as cs  # noqa: E402
from app.api.v1 import recruiter as rec  # noqa: E402,F401
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.code_submission import CodeSubmission  # noqa: E402
from app.models.coding_problem import CodingProblem  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import code_analysis as ca  # noqa: E402
from app.services import coding_problem_seed as seed  # noqa: E402
from tests.code_analysis.runner import local_runner  # noqa: E402

SUM = "a, b = map(int, input().split())\nprint(a + b)\n"


@pytest.fixture
def env(monkeypatch):
    uid, other, iid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with SessionLocal() as db:
        for u, role in ((uid, "candidate"), (other, "candidate")):
            db.execute(
                text("INSERT INTO users (id,email,password_hash,role,name) VALUES (:i,:e,'x',:r,'테스트')"),
                {"i": u, "e": f"ca-{u}@example.com", "r": role},
            )
        db.execute(
            text("INSERT INTO interviews (id,candidate_id,status,report_status) VALUES (:i,:c,'live','none')"),
            {"i": iid, "c": uid},
        )
        db.execute(text("DELETE FROM code_submissions WHERE problem_id IN (SELECT id FROM coding_problems)"))
        db.execute(text("DELETE FROM coding_problems"))
        db.commit()
        seed.seed_if_empty(db)
        subs = {}
        for lang, code in (("python", SUM), ("java", "class A {}"), ("javascript", "console.log(1)")):
            sub = CodeSubmission(interview_id=iid, language=lang, content=code)
            db.add(sub)
            db.flush()
            subs[lang] = sub.id
        problem_id = db.query(CodingProblem).filter_by(slug="sum-two").one().id
        db.commit()
        user = db.get(User, uid)
        other_user = db.get(User, other)
        db.refresh(user)
        db.refresh(other_user)
        db.expunge(user)
        db.expunge(other_user)
    limit_calls = []
    monkeypatch.setattr(cs, "check_and_increment_sandbox_rate_limit", lambda uid_: limit_calls.append(uid_))
    monkeypatch.setattr(cs, "execute_code_sandboxed", local_runner)
    state = {"user": user}
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    yield {
        "c": TestClient(app),
        "iid": iid,
        "subs": subs,
        "pid": problem_id,
        "state": state,
        "other": other_user,
        "limits": limit_calls,
    }
    app.dependency_overrides.pop(get_current_user, None)
    with SessionLocal() as db:
        db.execute(text("DELETE FROM evaluation_reports WHERE interview_id=:i"), {"i": iid})
        db.execute(text("DELETE FROM code_submissions WHERE interview_id=:i"), {"i": iid})
        db.execute(text("DELETE FROM interviews WHERE id=:i"), {"i": iid})
        db.execute(text("DELETE FROM users WHERE id IN (:a,:b)"), {"a": uid, "b": other})
        db.execute(text("DELETE FROM coding_problems"))
        db.commit()


def analyze(env, lang="python", pid="default"):
    body = {"problem_id": str(env["pid"] if pid == "default" else pid) if pid else None}
    return env["c"].post(f"/api/v1/interviews/{env['iid']}/code-submissions/{env['subs'][lang]}/analysis", json=body)


def test_a01_problem_list_hides_hidden_tests(env):
    r = env["c"].get("/api/v1/coding-problems")
    assert r.status_code == 200 and len(r.json()) == 12
    one = next(p for p in r.json() if p["title"] == "두 수의 합")
    assert len(one["sample_tests"]) == 2 and set(one["sample_tests"][0]) == {"input", "expected"}
    assert all(len(p["sample_tests"]) <= 2 for p in r.json())
    assert len(next(p for p in r.json() if p["title"] == "피보나치 수")["sample_tests"]) == 2  # 공개 3개 중 2개만
    assert "100000 99999" not in r.text and "199999" not in r.text  # 숨김 테스트 값은 어디에도 없다


def test_a02_analysis_happy_path_and_persisted(env):
    r = analyze(env)
    assert r.status_code == 200
    j = r.json()
    assert j["correctness"]["passed"] == j["correctness"]["total"] == 4 and j["correctness"]["pass_rate"] == 1.0
    assert j["complexity"]["estimate"] == "O(1)" and j["style"]["score"] >= 0 and "disclaimer" in j
    with SessionLocal() as db:
        row = db.get(CodeSubmission, env["subs"]["python"])
        assert row.analysis_json["correctness"]["passed"] == 4 and row.problem_id == env["pid"]
    assert len(env["limits"]) == 1


def test_a03_wrong_solution_reports_failures_with_masking(env, monkeypatch):
    with SessionLocal() as db:
        db.get(CodeSubmission, env["subs"]["python"]).content = "print(0)"
        db.commit()
    j = analyze(env).json()
    assert (
        j["correctness"]["passed"] == 2 and len(j["correctness"]["failures"]) == 2
    )  # 기대값이 0인 두 케이스만 우연히 맞음
    assert any(f["input"] == "(비공개 테스트)" for f in j["correctness"]["failures"])


def test_a04_without_problem_and_unsupported_language(env):
    j = analyze(env, pid=None).json()
    assert j["correctness"] is None and j["complexity"]["estimate"]
    jj = analyze(env, lang="java").json()
    assert jj["correctness"] is None and jj["complexity"]["estimate"] == "unknown"


def test_a05_errors_404_and_ownership_and_rate_limit(env, monkeypatch):
    assert analyze(env, pid=str(uuid.uuid4())).status_code == 404
    bad = env["c"].post(f"/api/v1/interviews/{env['iid']}/code-submissions/{uuid.uuid4()}/analysis", json={})
    assert bad.status_code == 404
    owner = env["state"]["user"]
    env["state"]["user"] = env["other"]  # 남의 면접
    assert analyze(env).status_code in (403, 404)
    env["state"]["user"] = owner

    def limited(_):
        raise cs.RateLimitExceeded("한도 초과")

    monkeypatch.setattr(cs, "check_and_increment_sandbox_rate_limit", limited)
    assert analyze(env).status_code == 429


def test_a06_report_input_gets_summary_after_analysis(env):
    analyze(env)
    with SessionLocal() as db:
        from sqlalchemy import select

        sub = db.scalar(
            select(CodeSubmission).where(
                CodeSubmission.interview_id == env["iid"], CodeSubmission.analysis_json.is_not(None)
            )
        )
    s = ca.summarize_for_report(sub.analysis_json)
    assert "테스트 4개 중 4개 통과(100%)" in s


def test_a07_report_job_prompt_includes_code_analysis(env, monkeypatch):
    """process_report_generation_job 이 분석된 제출물이 있을 때 LLM 입력에 도구 계산 요약을 덧붙이는지(실제 작업 함수 실행)."""
    from app.services.llm_engine import ReportParsingFailed
    from app.worker import tasks

    analyze(env)
    with SessionLocal() as db:
        db.execute(text("UPDATE interviews SET status='completed' WHERE id=:i"), {"i": env["iid"]})
        db.commit()
    seen = []

    def fake(system_prompt, user_message, max_tokens=None):
        seen.append(user_message)
        raise ReportParsingFailed("원문")

    monkeypatch.setattr(tasks, "generate_report_response", fake)
    monkeypatch.setattr(tasks, "publish_ws_event", lambda *a, **k: None)
    tasks.process_report_generation_job.apply(args=(str(env["iid"]),)).get()
    assert seen and "[코드 분석 결과(도구 계산값)]" in seen[0] and "4개 통과" in seen[0]
