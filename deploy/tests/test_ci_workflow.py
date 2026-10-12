"""CI 워크플로(.github/workflows/ci.yml) 정적 검증 — GitHub 러너가 없어 실행은 못 하므로, 구조와 참조 경로를 검사한다.
(실제 명령은 개발 서버에서 같은 순서로 따로 실행해 확인했다 — 결과서 참고.)"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github/workflows/ci.yml"


def load():
    return yaml.safe_load(WF.read_text(encoding="utf-8"))


def all_steps(wf):
    for name, job in wf["jobs"].items():
        for step in job["steps"]:
            yield name, step


def test_ci01_has_three_jobs_and_triggers():
    wf = load()
    assert set(wf["jobs"]) == {"backend", "tooling", "frontend"}
    triggers = wf.get("on") or wf.get(True)  # PyYAML 은 'on' 을 True 로 읽는다
    assert "push" in triggers and "pull_request" in triggers


def test_ci02_no_deploy_and_least_privilege():
    # 'deploy/tests' 같은 폴더 경로는 배포 동작이 아니므로 제외하고 검사한다
    text = WF.read_text(encoding="utf-8").lower().replace("deploy/", "")
    assert load()["permissions"] == {"contents": "read"}
    for word in ("deploy", "kubectl", "docker push", "ssh ", "secrets."):
        assert word not in text.replace("배포", ""), f"CI 에 {word!r} 포함 — 배포는 승인 없이 자동 실행 금지"


def test_ci03_actions_are_pinned_to_major_versions():
    for _, step in all_steps(load()):
        if "uses" in step:
            assert re.fullmatch(r"[\w./-]+@v\d+", step["uses"]), step["uses"]


def test_ci04_referenced_paths_exist():
    wf = load()
    assert (ROOT / "backend/requirements-dev.txt").exists()
    runs = "\n".join(s.get("run", "") for _, s in all_steps(wf))
    for path in re.findall(r"\b((?:tests|scripts|deploy|loadtest)/[\w./-]+)", runs):
        target = path.rstrip("/")
        base = ROOT / "backend" if target.startswith("tests/") else ROOT
        assert (base / target).exists(), f"참조 경로 없음: {path}"
    for app in wf["jobs"]["frontend"]["strategy"]["matrix"]["app"]:
        assert (ROOT / app / "package-lock.json").exists()
    assert (ROOT / "frontend/lib/reportStats.test.mjs").exists()


def test_ci05_db_job_prepares_pgvector_before_migration():
    steps = [s.get("run", "") for s in load()["jobs"]["backend"]["steps"]]
    idx_ext = next(i for i, r in enumerate(steps) if "CREATE EXTENSION IF NOT EXISTS vector" in r)
    idx_mig = next(i for i, r in enumerate(steps) if "alembic upgrade head" in r)
    idx_db_tests = next(i for i, r in enumerate(steps) if "tests/turn_graph" in r)
    assert idx_ext <= idx_mig < idx_db_tests
    assert load()["jobs"]["backend"]["services"]["postgres"]["image"] == "pgvector/pgvector:pg16"


def test_ci06_conflicting_stub_suites_run_in_separate_processes():
    runs = [s.get("run", "") for s in load()["jobs"]["backend"]["steps"]]
    mail = [r for r in runs if "final_decision" in r]
    graph = [r for r in runs if "tests/turn_graph" in r]
    assert len(mail) == 1 and len(graph) == 1 and mail[0] != graph[0]  # 스텁 충돌 방지(결과서 참고)


def test_ci07_slow_network_test_excluded_and_known_warnings_not_blocking():
    wf = load()
    tooling = " ".join(s.get("run", "") for s in wf["jobs"]["tooling"]["steps"])
    assert '-k "not bu19"' in tooling
    ruff = next(s for s in wf["jobs"]["backend"]["steps"] if "ruff" in s.get("run", ""))
    lint = next(s for s in wf["jobs"]["frontend"]["steps"] if s.get("run") == "npm run lint")
    assert ruff.get("continue-on-error") is True and lint.get("continue-on-error") is True
    # 타입 검사·빌드·테스트는 경고가 아니라 필수
    for step in wf["jobs"]["frontend"]["steps"]:
        if step.get("run") in ("npx tsc --noEmit", "npm run build"):
            assert "continue-on-error" not in step
