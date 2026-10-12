# ruff: noqa: E501, E741
"""REQ-F-004 분석 모듈 단위 테스트 — 실제 ruff, 실제 기준 풀이 실행(로컬 python, 신뢰 코드)."""

import pytest

from app.services import code_analysis as ca
from app.services import coding_problem_seed as seed
from tests.code_analysis.runner import R, local_runner

# ───── 시간복잡도(Python) ─────
PY = {
    "O(1)": "x = int(input())\nprint(x + 1)\n",
    "O(n)": "a = list(map(int, input().split()))\ns = 0\nfor v in a:\n    s += v\nprint(s)\n",
    "O(n^2)": "n = 5\nfor i in range(n):\n    for j in range(n):\n        pass\n",
    "O(n^3)": "for i in range(3):\n    for j in range(3):\n        for k in range(3):\n            pass\n",
    "O(n log n)": "a = [3, 1, 2]\nprint(sorted(a))\n",
    "O(log n)": "n = 1000\nwhile n > 1:\n    n //= 2\n",
}


@pytest.mark.parametrize("expected,code", PY.items())
def test_c01_python_static_complexity(expected, code):
    assert ca.estimate_complexity_python(code)["estimate"] == expected


def test_c02_recursion_exponential_vs_memo():
    naive = "def f(n):\n    return n if n < 2 else f(n-1) + f(n-2)\nprint(f(5))\n"
    memo = "from functools import lru_cache\n@lru_cache\ndef f(n):\n    return n if n < 2 else f(n-1) + f(n-2)\nprint(f(5))\n"
    assert ca.estimate_complexity_python(naive)["estimate"] == "O(2^n)"
    r = ca.estimate_complexity_python(memo)
    assert r["estimate"] == "O(n)" and r["confidence"] == "low"


def test_c03_comprehension_counts_as_loop_and_syntax_error():
    assert ca.estimate_complexity_python("x=[[j for j in range(3)] for i in range(3)]")["estimate"] == "O(n^2)"
    r = ca.estimate_complexity_python("def (:")
    assert r["estimate"] == "unknown" and r["confidence"] == "low"


# ───── 시간복잡도(JavaScript) ─────
def test_c04_js_loops_and_methods():
    assert ca.estimate_complexity_javascript("for (let i=0;i<n;i++){ x++; }")["estimate"] == "O(n)"
    assert (
        ca.estimate_complexity_javascript("for (let i=0;i<n;i++){ for (let j=0;j<n;j++){ x++; } }")["estimate"]
        == "O(n^2)"
    )
    assert ca.estimate_complexity_javascript("a.forEach(x => { b.map(y => { z(); }); });")["estimate"] == "O(n^2)"
    assert ca.estimate_complexity_javascript("a.sort((x,y)=>x-y);")["estimate"] == "O(n log n)"
    assert ca.estimate_complexity_javascript("const x = 1;")["estimate"] == "O(1)"


def test_c05_js_strings_and_comments_do_not_confuse():
    code = '// for (;;) { while(1) {} }\nconst s = "for (i) { for (j) {";\nconsole.log(s);\n'
    assert ca.estimate_complexity_javascript(code)["estimate"] == "O(1)"
    assert ca.estimate_complexity("java", "class A{}")["estimate"] == "unknown"


# ───── 실측 보조 ─────
def test_c06_fit_growth():
    lin = [(1000, 0.5), (4000, 0.9), (16000, 2.5), (64000, 9.0)]
    quad = [(100, 0.5), (200, 0.9), (400, 2.5), (800, 9.0 * 4)]
    assert ca.fit_growth([(10, 0.5), (100, 0.52)]) is None  # 표본 부족
    assert ca.fit_growth([(10, 0.5), (100, 0.55), (1000, 0.6)]) is None  # 차이가 작음(컨테이너 기동에 묻힘)
    assert ca.fit_growth(lin) == "O(n)"
    assert ca.fit_growth(quad) in ("O(n^2)", "O(n^3)")


def test_c07_measured_merge_rules():
    base = ca.estimate_complexity("python", PY["O(n)"], measured="O(n)")
    assert base["confidence"] == "medium"
    diff = ca.estimate_complexity("python", PY["O(n)"], measured="O(n^2)")
    assert diff["estimate"] == "O(n)" and diff["confidence"] == "low"
    unk = ca.estimate_complexity("python", "def (:", measured="O(n)")
    assert unk["estimate"] == "O(n)" and unk["confidence"] == "low"


# ───── 정답 판정 ─────
SUM = "a, b = map(int, input().split())\nprint(a + b)\n"
TESTS = [{"input": "1 2", "expected": "3"}, {"input": "5 5", "expected": "10", "hidden": True}]


def test_c08_correctness_all_pass_and_trailing_space_tolerated():
    r = ca.evaluate_correctness("python", SUM.replace("print(a + b)", "print(a + b, end='  \\n')"), TESTS, local_runner)
    assert (r["total"], r["passed"], r["pass_rate"], r["failures"]) == (2, 2, 1.0, [])


def test_c09_wrong_answer_and_hidden_masking():
    r = ca.evaluate_correctness("python", "print(0)\n", TESTS, local_runner)
    assert r["passed"] == 0 and len(r["failures"]) == 2
    assert r["failures"][0]["expected"] == "3"
    assert r["failures"][1]["input"] == r["failures"][1]["expected"] == r["failures"][1]["actual"] == "(비공개 테스트)"


def test_c10_runtime_error_timeout_and_runner_exception():
    err = ca.evaluate_correctness("python", "raise ValueError('x')\n", TESTS[:1], local_runner)
    assert err["passed"] == 0 and "ValueError" in err["failures"][0]["actual"]
    to = ca.evaluate_correctness("python", "x", TESTS[:1], lambda l, c, stdin_text=None: R("", "", None, True))
    assert to["failures"][0]["timed_out"] is True
    boom = ca.evaluate_correctness("python", "x", TESTS[:1], lambda l, c, stdin_text=None: 1 / 0)
    assert boom["passed"] == 0 and boom["failures"][0]["actual"] == "(실행 오류)"


def test_c11_failure_cap_and_test_cap():
    many = [{"input": str(i), "expected": "z"} for i in range(40)]
    r = ca.evaluate_correctness("python", "print(1)", many, local_runner)
    assert r["total"] == ca.MAX_TESTS and len(r["failures"]) == ca.MAX_REPORTED_FAILURES


def test_c12_no_tests_and_unsupported_language():
    out = ca.analyze_code("python", SUM, tests=None, perf=None, runner=local_runner)
    assert out["correctness"] is None
    out2 = ca.analyze_code("java", "class A {}", tests=TESTS, perf=None, runner=local_runner)
    assert out2["correctness"] is None and out2["complexity"]["estimate"] == "unknown"


# ───── 기본 문제 12개: 기준 풀이로 전부 통과해야 한다 ─────
REF = {
    "sum-two": "a,b=map(int,input().split());print(a+b)",
    "array-max": "input();print(max(map(int,input().split())))",
    "palindrome": "s=input().strip();print('YES' if s==s[::-1] else 'NO')",
    "fibonacci": "n=int(input());a,b=0,1\nfor _ in range(n):a,b=b,a+b\nprint(a)",
    "is-prime": "n=int(input())\nprint('YES' if n>=2 and all(n%d for d in range(2,int(n**.5)+1)) else 'NO')",
    "unique-sorted": "input();print(*sorted(set(map(int,input().split()))))",
    "valid-parens": "s=input().strip();p={')':'(',']':'[','}':'{'};st=[]\nok=True\nfor c in s:\n  if c in '([{':st.append(c)\n  elif not st or st.pop()!=p[c]:ok=False;break\nprint('YES' if ok and not st else 'NO')",
    "binary-search": "input();a=list(map(int,input().split()));t=int(input())\nprint(a.index(t) if t in a else -1)",
    "two-sum-exists": "n,t=map(int,input().split());a=list(map(int,input().split()));s=set();f=False\nfor x in a:\n  if t-x in s:f=True\n  s.add(x)\nprint('YES' if f else 'NO')",
    "reverse-words": "print(' '.join(input().split()[::-1]))",
    "max-subarray": "input();a=list(map(int,input().split()));b=c=a[0]\nfor x in a[1:]:\n  c=max(x,c+x);b=max(b,c)\nprint(b)",
    "gcd": "from math import gcd;a,b=map(int,input().split());print(gcd(a,b))",
}


def test_c13_seed_data_shape():
    probs = seed.build_problems()
    assert len(probs) == 12 and len({p["slug"] for p in probs}) == 12
    for p in probs:
        assert (
            len(p["tests_json"]) >= 4
            and any(not t["hidden"] for t in p["tests_json"])
            and any(t["hidden"] for t in p["tests_json"])
        )
        assert all(t["expected"] != "" for t in p["tests_json"])


@pytest.mark.parametrize("slug", sorted(REF))
def test_c14_reference_solutions_pass_every_seed_problem(slug):
    prob = next(p for p in seed.build_problems() if p["slug"] == slug)
    r = ca.evaluate_correctness("python", REF[slug], prob["tests_json"], local_runner)
    assert r["passed"] == r["total"], r["failures"]


# ───── 스타일 ─────
def test_c15_style_ruff_detects_and_scores():
    bad = "import os\nx=1\ndef F( a ):\n    return a\n"
    r = ca.check_style("python", bad)
    assert r["tool"] == "ruff" and r["violations"] >= 2 and r["score"] < 100
    assert all(i["line"] >= 1 for i in r["items"])
    assert ca.check_style("python", "x = 1\nprint(x)\n")["score"] == 100


def test_c16_style_fallback_when_ruff_missing(monkeypatch):
    monkeypatch.setattr(ca, "_ruff_cmd", lambda: None)
    r = ca.check_style("python", "x = 1   \n" + "y" * 120 + "\n")
    assert r["tool"] == "builtin" and r["violations"] == 2


def test_c17_style_js_rules_and_cap():
    r = ca.check_style("javascript", "var a = 1;\nif (a == 2) {}\nconsole.log(a);\n")
    codes = {i["code"] for i in r["items"]}
    assert {"NO_VAR", "EQEQEQ", "NO_CONSOLE"} <= codes
    many = ca.check_style("javascript", "var a;\n" * 40)
    assert many["violations"] == 40 and len(many["items"]) == ca.MAX_STYLE_ITEMS and many["score"] == 0


# ───── 주석 ─────
def test_c18_comments_python():
    code = '"""모듈 설명"""\n# 합\ndef f(a):\n    """더하기"""\n    return a\n\nx = 1\n'
    r = ca.analyze_comments("python", code)
    assert r["has_docstring"] is True and r["comment_lines"] == 3 and r["code_lines"] == 3
    none = ca.analyze_comments("python", "x = 1\ny = 2\n")
    assert none["comment_lines"] == 0 and none["ratio"] == 0 and "없습니다" in none["note"]


def test_c19_comments_javascript_and_edge():
    r = ca.analyze_comments("javascript", "/** 설명\n * 더\n */\n// 한 줄\nconst a = 1;\n")
    assert r["comment_lines"] == 4 and r["code_lines"] == 1 and r["has_docstring"] is True
    assert ca.analyze_comments("python", "")["ratio"] == 0.0
    assert ca.analyze_comments("python", "def (:\n# c\n")["comment_lines"] == 1  # 문법 오류에도 죽지 않음


def test_c20_summary_for_report():
    a = ca.analyze_code("python", SUM, tests=TESTS, perf=None, runner=local_runner)
    s = ca.summarize_for_report(a)
    assert "테스트 2개 중 2개 통과(100%)" in s and "시간복잡도(근사)" in s and "스타일" in s
    assert ca.summarize_for_report(None) == ""
