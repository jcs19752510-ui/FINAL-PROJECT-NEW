# ruff: noqa: E501, E741
"""라이브 코딩 제출물 분석 — 원본 계획서 REQ-F-004 "AI 분석(정답, 시간복잡도, 스타일, 주석)" (2026-10-12).

설계 원칙 (20년차 기준)
- **숫자는 도구가 내고 LLM은 설명만 한다.** 로컬 1.5B 모델은 코드 판정에 약하므로 정답·복잡도·스타일·주석 수치는 전부 결정적 방법으로
  계산한다. LLM은 리포트 생성 때 이 수치를 읽고 서술할 뿐이다(app/worker/tasks.py).
- **정답**: 문제의 테스트케이스를 기존 격리 샌드박스(code_sandbox.py)로 실행해 표준출력을 비교한다(AI 없음, 확정 값).
- **시간복잡도**: 정적 분석(Python은 AST, JavaScript는 토큰 휴리스틱) + 선택적 실측 보조. **근사치**이며 항상 그렇게 표기한다.
- **스타일**: Python은 ruff(코드를 실행하지 않고 파싱만 함), JavaScript는 내장 경량 규칙.
- **주석**: 주석 줄 비율과 docstring 유무. 내용의 적절성은 판정하지 않는다.
- 지원자 코드를 이 프로세스에서 실행하지 않는다. 실행은 오직 샌드박스 컨테이너 안에서만 일어난다.
"""

import ast
import io
import json
import logging
import math
import re
import shutil
import subprocess
import sys
import time
import tokenize
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

MAX_TESTS = 30
MAX_REPORTED_FAILURES = 5
MAX_STYLE_ITEMS = 20
MAX_CODE_CHARS = 20000
_HIDDEN_MASK = "(비공개 테스트)"
_MAX_FIELD_CHARS = 300
_PERF_MIN_SPREAD_SECONDS = 0.3  # 컨테이너 기동 시간에 묻히지 않을 만큼 실행시간 차이가 있을 때만 실측을 쓴다

DISCLAIMER = (
    "시간복잡도는 코드 구조와 실행시간으로 추정한 근사치이며 증명이 아닙니다. 스타일·주석 지표는 형식 검사로 "
    "코드의 설계 품질을 대신하지 않습니다. 정답 여부는 등록된 테스트케이스 기준입니다. AI 분석은 채용 판단의 보조 자료입니다."
)

RUNNABLE = ("python", "javascript")  # 샌드박스 실행 지원 언어(code_sandbox 와 일치해야 함)
COMPLEXITY_ORDER = ["O(1)", "O(log n)", "O(n)", "O(n log n)", "O(n^2)", "O(n^3)", "O(2^n)"]


# ──────────────────────────── 정답 ────────────────────────────
def _norm_output(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


def _clip(text: str) -> str:
    return text if len(text) <= _MAX_FIELD_CHARS else text[:_MAX_FIELD_CHARS] + "…"


def evaluate_correctness(language: str, code: str, tests: list[dict], runner: Callable[..., Any]) -> dict:
    """테스트케이스별로 샌드박스 실행 후 출력 비교. `runner(language, code, stdin_text=...)` 는 SandboxResult 호환 객체를 돌려준다."""
    tests = tests[:MAX_TESTS]
    passed = 0
    failures: list[dict] = []
    for idx, tc in enumerate(tests):
        hidden = bool(tc.get("hidden"))
        expected = str(tc.get("expected", ""))
        try:
            res = runner(language, code, stdin_text=str(tc.get("input", "")))
        except Exception:  # noqa: BLE001 — 실행기 오류는 해당 케이스 실패로 처리하고 분석 전체는 계속한다
            logger.warning("테스트케이스 실행 오류 idx=%s", idx, exc_info=True)
            actual, timed_out, ok = "(실행 오류)", False, False
        else:
            timed_out = bool(getattr(res, "timed_out", False))
            exit_code = getattr(res, "exit_code", None)
            actual = res.stdout if exit_code == 0 and not timed_out else (res.stderr or res.stdout or "")
            ok = (not timed_out) and exit_code == 0 and _norm_output(res.stdout) == _norm_output(expected)
        if ok:
            passed += 1
        elif len(failures) < MAX_REPORTED_FAILURES:
            failures.append(
                {
                    "index": idx,
                    "input": _HIDDEN_MASK if hidden else _clip(str(tc.get("input", ""))),
                    "expected": _HIDDEN_MASK if hidden else _clip(expected),
                    "actual": _HIDDEN_MASK if hidden else _clip(actual),
                    "timed_out": timed_out,
                }
            )
    total = len(tests)
    return {
        "total": total,
        "passed": passed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "failures": failures,
    }


# ──────────────────────────── 시간복잡도 ────────────────────────────
def _loop_complexity(depth: int, has_sort: bool, halving: bool) -> str:
    if depth >= 3:
        return "O(n^3)"
    if depth == 2:
        return "O(n^2)"
    if depth == 1:
        if halving:
            return "O(log n)"
        return "O(n log n)" if has_sort else "O(n)"
    return "O(n log n)" if has_sort else "O(1)"


class _PyLoopVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.max_depth = 0
        self._depth = 0
        self.has_sort = False
        self.halving = False

    def _loop(self, node: ast.AST) -> None:
        self._depth += 1
        self.max_depth = max(self.max_depth, self._depth)
        self.generic_visit(node)
        self._depth -= 1

    visit_For = visit_While = visit_ListComp = visit_SetComp = visit_DictComp = visit_GeneratorExp = _loop  # noqa: N815

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        # while 루프 안에서 i //= 2, i >>= 1, i /= 2 → 로그 시간 단서
        if isinstance(node.op, (ast.FloorDiv, ast.RShift, ast.Div)) and isinstance(node.value, ast.Constant):
            if node.value.value in (2, 1) and (isinstance(node.op, ast.RShift) or node.value.value == 2):
                self.halving = True
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        f = node.func
        if (isinstance(f, ast.Name) and f.id == "sorted") or (isinstance(f, ast.Attribute) and f.attr == "sort"):
            self.has_sort = True
        self.generic_visit(node)


def _py_recursion(tree: ast.AST) -> tuple[bool, int, bool]:
    """(재귀 여부, 한 함수 안 자기 호출 최대 횟수, 메모이제이션 단서)."""
    recursive, max_calls, memo = False, 0, False
    for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        calls = sum(
            1 for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == fn.name
        )
        if calls:
            recursive = True
            max_calls = max(max_calls, calls)
            for d in fn.decorator_list:
                name = ast.unparse(d)
                if "lru_cache" in name or name.endswith("cache"):
                    memo = True
    if recursive and re.search(r"\b(memo|cache|dp)\b", ast.unparse(tree)):
        memo = True
    return recursive, max_calls, memo


def estimate_complexity_python(code: str) -> dict:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return {"estimate": "unknown", "basis": [f"문법 오류로 구조 분석 불가 (줄 {exc.lineno})"], "confidence": "low"}
    v = _PyLoopVisitor()
    v.visit(tree)
    recursive, calls, memo = _py_recursion(tree)
    basis = [f"반복문 최대 중첩 깊이 {v.max_depth}"]
    if v.has_sort:
        basis.append("정렬(sorted/sort) 사용")
    if v.halving and v.max_depth == 1:
        basis.append("반복마다 값을 절반으로 줄이는 패턴")
    est = _loop_complexity(v.max_depth, v.has_sort, v.halving and v.max_depth == 1)
    confidence = "medium"
    if recursive:
        basis.append(f"재귀 호출 감지(함수 내 자기 호출 {calls}회)")
        confidence = "low"
        if calls >= 2 and not memo:
            est = "O(2^n)"
            basis.append("메모이제이션 단서 없음 → 중복 호출로 지수 시간 가능성")
        elif calls >= 2 and memo:
            est = max(est, "O(n)", key=COMPLEXITY_ORDER.index)
            basis.append("메모이제이션 단서 있음")
        elif est == "O(1)":
            est = "O(n)"
    return {"estimate": est, "basis": basis, "confidence": confidence}


_JS_LOOP_KW = re.compile(r"\b(for|while)\s*\(")
_JS_ITER_METHOD = re.compile(r"\.(forEach|map|filter|reduce|some|every|find|findIndex|flatMap)\s*\(")
_JS_SORT = re.compile(r"\.sort\s*\(")


def _strip_js(code: str) -> str:
    """주석·문자열 리터럴을 공백으로 치환(구조 휴리스틱이 문자열 안의 괄호에 속지 않도록)."""
    out, i, n = [], 0, len(code)
    while i < n:
        c = code[i]
        if code.startswith("//", i):
            j = code.find("\n", i)
            i = n if j == -1 else j
        elif code.startswith("/*", i):
            j = code.find("*/", i + 2)
            i = n if j == -1 else j + 2
        elif c in "\"'`":
            j = i + 1
            while j < n and code[j] != c:
                j += 2 if code[j] == "\\" else 1
            out.append(" ")
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def estimate_complexity_javascript(code: str) -> dict:
    src = _strip_js(code)
    stack: list[bool] = []  # 각 중괄호 블록이 반복 본문인지
    pending = False
    paren = 0
    max_depth = 0
    i, n = 0, len(src)
    while i < n:
        m_loop = _JS_LOOP_KW.match(src, i) if src[i] in "fw" else None
        m_iter = _JS_ITER_METHOD.match(src, i) if src[i] == "." else None
        if m_loop or m_iter:
            pending = True
            paren = 1  # 매칭된 여는 괄호는 이미 소비됨 — for(;;) 헤더 안의 ';' 를 문장 끝으로 오인하지 않기 위해 추적
            i = (m_loop or m_iter).end()
            continue
        c = src[i]
        if c == "(":
            paren += 1
        elif c == ")":
            paren = max(0, paren - 1)
        if c == "{":
            stack.append(pending)
            pending = False
            max_depth = max(max_depth, sum(stack))
        elif c == "}" and stack:
            stack.pop()
        elif c == ";" and pending and paren == 0:
            pending = False
        i += 1
    has_sort = bool(_JS_SORT.search(src))
    basis = [
        f"반복 구조(for/while/배열 메서드) 최대 중첩 깊이 {max_depth}",
        "JavaScript는 토큰 휴리스틱이라 정확도가 낮음",
    ]
    if has_sort:
        basis.append("정렬(.sort) 사용")
    names = re.findall(r"function\s+(\w+)\s*\(", src) + re.findall(r"(?:const|let|var)\s+(\w+)\s*=\s*\(?[^=]*=>", src)
    recursive = any(len(re.findall(rf"\b{re.escape(nm)}\s*\(", src)) >= 2 for nm in names)
    est = _loop_complexity(max_depth, has_sort, False)
    if recursive:
        basis.append("재귀 호출 가능성 감지")
        if est == "O(1)":
            est = "O(n)"
    return {"estimate": est, "basis": basis, "confidence": "low"}


def fit_growth(samples: list[tuple[float, float]]) -> str | None:
    """(입력크기 n, 실행시간 초) 표본에서 log-log 기울기로 증가율 등급을 추정. 표본이 부족하거나 차이가 작으면 None."""
    pts = sorted((n, t) for n, t in samples if n > 0 and t > 0)
    if len(pts) < 3:
        return None
    base = pts[0][1]
    adj = [(n, t - base * 0.9) for n, t in pts[1:]]  # 컨테이너 기동 시간 근사 제거
    adj = [(n, t) for n, t in adj if t > 1e-4]
    if len(adj) < 2 or (pts[-1][1] - pts[0][1]) < _PERF_MIN_SPREAD_SECONDS:
        return None
    xs = [math.log(n) for n, _ in adj]
    ys = [math.log(t) for _, t in adj]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / den
    if slope < 0.35:
        return "O(log n)"
    if slope < 1.25:
        return "O(n)"
    if slope < 1.6:
        return "O(n log n)"
    if slope < 2.5:
        return "O(n^2)"
    return "O(n^3)"


def estimate_complexity(language: str, code: str, measured: str | None = None) -> dict:
    if language == "python":
        res = estimate_complexity_python(code)
    elif language in ("javascript", "typescript"):
        res = estimate_complexity_javascript(code)
    else:
        return {
            "estimate": "unknown",
            "basis": [f"'{language}' 언어는 복잡도 분석을 지원하지 않음"],
            "confidence": "low",
        }
    if measured:
        res = dict(res, basis=list(res["basis"]))
        if res["estimate"] == "unknown":
            res.update(estimate=measured, confidence="low")
            res["basis"].append(f"실행시간 실측 추정 {measured}")
        elif measured == res["estimate"]:
            res["confidence"] = "medium"
            res["basis"].append(f"실행시간 실측도 {measured}로 일치")
        else:
            res["basis"].append(f"실행시간 실측은 {measured}로 정적 분석과 다름(참고)")
            res["confidence"] = "low"
    return res


# ──────────────────────────── 스타일 ────────────────────────────
def _ruff_cmd() -> list[str] | None:
    exe = shutil.which("ruff")
    if exe:
        return [exe]
    try:
        import ruff  # noqa: F401

        return [sys.executable, "-m", "ruff"]
    except ImportError:
        return None


def _builtin_style(code: str, max_line: int = 100) -> list[dict]:
    items: list[dict] = []
    for no, line in enumerate(code.splitlines(), 1):
        if len(line) > max_line:
            items.append({"line": no, "code": "LINE_LEN", "message": f"줄 길이 {len(line)}자 (권장 {max_line}자 이하)"})
        if line != line.rstrip():
            items.append({"line": no, "code": "TRAIL_WS", "message": "줄 끝 공백"})
        if "\t" in line[: len(line) - len(line.lstrip())]:
            items.append({"line": no, "code": "TAB_INDENT", "message": "들여쓰기에 탭 사용"})
    return items


def _js_style(code: str) -> list[dict]:
    items = _builtin_style(code)
    for no, line in enumerate(code.splitlines(), 1):
        s = line.strip()
        if re.match(r"var\s", s):
            items.append({"line": no, "code": "NO_VAR", "message": "var 대신 let/const 사용 권장"})
        if "==" in s and "===" not in s and "!=" not in s.replace("!==", ""):
            items.append({"line": no, "code": "EQEQEQ", "message": "== 대신 === 사용 권장"})
        if re.match(r"console\.log\(", s):
            items.append({"line": no, "code": "NO_CONSOLE", "message": "console.log 호출(디버그 잔재 가능성)"})
    return items


def check_style(language: str, code: str) -> dict:
    tool = "builtin"
    items: list[dict] = []
    if language == "python":
        cmd = _ruff_cmd()
        ran = False
        if cmd:
            try:
                proc = subprocess.run(  # noqa: S603 — 고정 인자, 코드는 stdin 데이터로만 전달(실행하지 않음)
                    [
                        *cmd,
                        "check",
                        "--isolated",
                        "--select",
                        "E,W,F,N,B",
                        "--line-length",
                        "100",
                        "--output-format",
                        "json",
                        "--stdin-filename",
                        "main.py",
                        "-",
                    ],
                    input=code,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                data = json.loads(proc.stdout or "[]")
                items = [
                    {
                        "line": int((d.get("location") or {}).get("row", 0)),
                        "code": str(d.get("code") or ""),
                        "message": str(d.get("message") or ""),
                    }
                    for d in data
                ]
                tool, ran = "ruff", True
            except (subprocess.SubprocessError, ValueError, OSError):
                logger.warning("ruff 실행 실패 — 내장 규칙으로 대체", exc_info=True)
        if not ran:
            items = _builtin_style(code)
    elif language in ("javascript", "typescript"):
        items = _js_style(code)
        tool = "builtin-js"
    else:
        items = _builtin_style(code)
    items.sort(key=lambda d: (d["line"], d["code"]))
    violations = len(items)
    score = max(0, 100 - min(100, violations * 5))
    return {"tool": tool, "violations": violations, "score": score, "items": items[:MAX_STYLE_ITEMS]}


# ──────────────────────────── 주석 ────────────────────────────
def analyze_comments(language: str, code: str) -> dict:
    lines = code.splitlines()
    comment_lines = 0
    has_doc = False
    if language == "python":
        try:
            comment_line_set: set[int] = set()
            for tok in tokenize.generate_tokens(io.StringIO(code).readline):
                if tok.type == tokenize.COMMENT and tok.line.strip().startswith("#"):
                    comment_line_set.add(tok.start[0])
            tree = ast.parse(code)
            doc_lines: set[int] = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    body = getattr(node, "body", [])
                    if (
                        body
                        and isinstance(body[0], ast.Expr)
                        and isinstance(getattr(body[0], "value", None), ast.Constant)
                        and isinstance(body[0].value.value, str)
                    ):
                        has_doc = True
                        doc_lines.update(range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1))
            comment_lines = len(comment_line_set | doc_lines)
        except (tokenize.TokenError, SyntaxError, IndentationError):
            comment_lines = sum(1 for ln in lines if ln.strip().startswith("#"))
    else:
        in_block = False
        for ln in lines:
            s = ln.strip()
            if in_block:
                comment_lines += 1
                if "*/" in s:
                    in_block = False
            elif s.startswith("//"):
                comment_lines += 1
            elif s.startswith("/*"):
                comment_lines += 1
                has_doc = has_doc or s.startswith("/**")
                in_block = "*/" not in s
    non_empty = [ln for ln in lines if ln.strip()]
    code_lines = max(0, len(non_empty) - comment_lines)
    total = comment_lines + code_lines
    ratio = round(comment_lines / total, 3) if total else 0.0
    if comment_lines == 0:
        note = "주석이 없습니다."
    elif ratio > 0.5:
        note = "주석 비율이 매우 높습니다(코드보다 주석이 많음)."
    elif ratio < 0.05 and code_lines > 20:
        note = "코드 분량에 비해 주석이 적습니다."
    else:
        note = "주석 비율이 일반적인 범위입니다(내용의 적절성은 판정하지 않음)."
    return {
        "comment_lines": comment_lines,
        "code_lines": code_lines,
        "ratio": ratio,
        "has_docstring": has_doc,
        "note": note,
    }


# ──────────────────────────── 종합 ────────────────────────────
def _measure_growth(language: str, code: str, perf: list[dict], runner: Callable[..., Any]) -> str | None:
    samples: list[tuple[float, float]] = []
    for case in perf[:6]:
        try:
            t0 = time.perf_counter()
            res = runner(language, code, stdin_text=str(case.get("input", "")))
            dt = time.perf_counter() - t0
        except Exception:  # noqa: BLE001
            return None
        if getattr(res, "timed_out", False) or getattr(res, "exit_code", 1) != 0:
            return None
        samples.append((float(case.get("n", 0)), dt))
    return fit_growth(samples)


def analyze_code(
    language: str,
    code: str,
    *,
    tests: list[dict] | None,
    perf: list[dict] | None,
    runner: Callable[..., Any],
) -> dict:
    """제출물 하나를 분석해 JSON 직렬화 가능한 dict 로 반환한다."""
    code = code[:MAX_CODE_CHARS]
    correctness = evaluate_correctness(language, code, tests, runner) if tests and language in RUNNABLE else None
    measured = _measure_growth(language, code, perf, runner) if perf and language in ("python", "javascript") else None
    return {
        "correctness": correctness,
        "complexity": estimate_complexity(language, code, measured),
        "style": check_style(language, code),
        "comments": analyze_comments(language, code),
        "disclaimer": DISCLAIMER,
    }


def summarize_for_report(analysis: dict | None) -> str:
    """리포트 LLM 입력에 덧붙일 한국어 요약. 수치는 도구 결과이며 LLM 은 이를 서술만 한다."""
    if not analysis:
        return ""
    parts: list[str] = []
    c = analysis.get("correctness")
    if c:
        parts.append(f"정답: 테스트 {c['total']}개 중 {c['passed']}개 통과({c['pass_rate'] * 100:.0f}%)")
    cx = analysis.get("complexity") or {}
    if cx:
        parts.append(f"시간복잡도(근사): {cx.get('estimate')} (신뢰도 {cx.get('confidence')})")
    st = analysis.get("style") or {}
    if st:
        parts.append(f"스타일: 점수 {st.get('score')}/100, 위반 {st.get('violations')}건")
    cm = analysis.get("comments") or {}
    if cm:
        parts.append(
            f"주석: 비율 {cm.get('ratio', 0) * 100:.0f}%, docstring {'있음' if cm.get('has_docstring') else '없음'}"
        )
    return "[코드 분석 결과(도구 계산값)]\n" + "\n".join(f"- {p}" for p in parts)
