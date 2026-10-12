# ruff: noqa: E501, E741
"""기본 코딩 문제 초안 12개 — 표준입력/표준출력 방식 (원본 REQ-F-004, 2026-10-12).

**초안이다.** 문제 선정·난이도·테스트케이스의 채용 기준 적합성은 채용 담당자가 검수해야 한다.
기대 출력은 아래 기준 풀이(`ref`)로 계산해 손으로 적은 값의 오류를 막는다.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.coding_problem import CodingProblem

logger = logging.getLogger(__name__)


def _is_prime(n: int) -> bool:
    return n >= 2 and all(n % d for d in range(2, int(n**0.5) + 1))


def _valid_parens(s: str) -> bool:
    pairs, st = {")": "(", "]": "[", "}": "{"}, []
    for ch in s:
        if ch in "([{":
            st.append(ch)
        elif ch in pairs:
            if not st or st.pop() != pairs[ch]:
                return False
    return not st


def _fib(n: int) -> int:
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def _bsearch(arr: list[int], t: int) -> int:
    lo, hi = 0, len(arr) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if arr[mid] == t:
            return mid
        lo, hi = (mid + 1, hi) if arr[mid] < t else (lo, mid - 1)
    return -1


def _kadane(a: list[int]) -> int:
    best = cur = a[0]
    for x in a[1:]:
        cur = max(x, cur + x)
        best = max(best, cur)
    return best


def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a


def _two_sum(a: list[int], t: int) -> bool:
    seen: set[int] = set()
    for x in a:
        if t - x in seen:
            return True
        seen.add(x)
    return False


def _nums(a: list[int]) -> str:
    return f"{len(a)}\n{' '.join(map(str, a))}"


YN = lambda b: "YES" if b else "NO"  # noqa: E731

# (slug, 제목, 설명, 난이도, [(입력, 기대출력, hidden)])
_SPECS: list[tuple[str, str, str, str, list[tuple[str, str, bool]]]] = [
    (
        "sum-two",
        "두 수의 합",
        "공백으로 구분된 두 정수 a, b 를 입력받아 a+b 를 출력하세요.",
        "easy",
        [
            (f"{a} {b}", str(a + b), h)
            for (a, b, h) in [(1, 2, False), (-5, 5, False), (100000, 99999, True), (0, 0, True)]
        ],
    ),
    (
        "array-max",
        "배열의 최댓값",
        "첫 줄에 정수 개수 n, 둘째 줄에 n개의 정수가 주어집니다. 최댓값을 출력하세요.",
        "easy",
        [
            (_nums(a), str(max(a)), h)
            for a, h in [([3, 1, 2], False), ([-4, -9, -1], False), ([7], True), ([5, 5, 5, 9, 0], True)]
        ],
    ),
    (
        "palindrome",
        "팰린드롬 판별",
        "소문자 문자열 하나가 주어집니다. 앞뒤로 읽어도 같으면 YES, 아니면 NO 를 출력하세요.",
        "easy",
        [
            (s, YN(s == s[::-1]), h)
            for s, h in [("level", False), ("hello", False), ("a", True), ("abccba", True), ("abca", True)]
        ],
    ),
    (
        "fibonacci",
        "피보나치 수",
        "정수 n(0 ≤ n ≤ 30)이 주어집니다. n번째 피보나치 수를 출력하세요. (F0=0, F1=1)",
        "easy",
        [(str(n), str(_fib(n)), h) for n, h in [(0, False), (1, False), (10, False), (20, True), (30, True)]],
    ),
    (
        "is-prime",
        "소수 판별",
        "정수 n(1 ≤ n ≤ 1000000)이 주어집니다. 소수이면 YES, 아니면 NO 를 출력하세요.",
        "easy",
        [
            (str(n), YN(_is_prime(n)), h)
            for n, h in [(1, False), (2, False), (15, False), (97, True), (999983, True), (1000000, True)]
        ],
    ),
    (
        "unique-sorted",
        "중복 제거 후 정렬",
        "첫 줄에 n, 둘째 줄에 n개의 정수가 주어집니다. 중복을 제거하고 오름차순으로 공백 구분 출력하세요.",
        "easy",
        [
            (_nums(a), " ".join(map(str, sorted(set(a)))), h)
            for a, h in [([3, 1, 3, 2, 1], False), ([5], False), ([-1, -1, 0, 0], True), ([9, 8, 7, 8], True)]
        ],
    ),
    (
        "valid-parens",
        "괄호 유효성",
        "(), [], {} 로 이루어진 문자열이 주어집니다. 올바르게 닫혔으면 YES, 아니면 NO 를 출력하세요.",
        "medium",
        [
            (s, YN(_valid_parens(s)), h)
            for s, h in [("()[]{}", False), ("(]", False), ("{[()]}", True), ("((", True), ("([)]", True)]
        ],
    ),
    (
        "binary-search",
        "이진 탐색",
        "첫 줄에 n, 둘째 줄에 오름차순 정렬된 n개의 정수, 셋째 줄에 찾을 값 t 가 주어집니다. t 의 0-기반 인덱스를, 없으면 -1 을 출력하세요.",
        "medium",
        [
            (f"{len(a)}\n{' '.join(map(str, a))}\n{t}", str(_bsearch(a, t)), h)
            for a, t, h in [
                ([1, 3, 5, 7, 9], 7, False),
                ([1, 3, 5, 7, 9], 4, False),
                ([2], 2, True),
                ([1, 2, 3, 4, 5, 6], 1, True),
                ([1, 2, 3, 4, 5, 6], 6, True),
            ]
        ],
    ),
    (
        "two-sum-exists",
        "합이 target 인 두 수",
        "첫 줄에 n 과 target, 둘째 줄에 n개의 정수가 주어집니다. 서로 다른 위치의 두 수의 합이 target 이 되는 쌍이 있으면 YES, 없으면 NO.",
        "medium",
        [
            (f"{len(a)} {t}\n{' '.join(map(str, a))}", YN(_two_sum(a, t)), h)
            for a, t, h in [
                ([2, 7, 11, 15], 9, False),
                ([1, 2, 3], 7, False),
                ([3, 3], 6, True),
                ([5], 10, True),
                ([-1, 4, 6, 1], 5, True),
            ]
        ],
    ),
    (
        "reverse-words",
        "단어 순서 뒤집기",
        "공백으로 구분된 단어들이 한 줄로 주어집니다. 단어 순서를 뒤집어 출력하세요.",
        "easy",
        [
            (s, " ".join(s.split()[::-1]), h)
            for s, h in [("hello world", False), ("a b c d", False), ("one", True), ("the quick brown fox", True)]
        ],
    ),
    (
        "max-subarray",
        "최대 부분 배열 합",
        "첫 줄에 n, 둘째 줄에 n개의 정수가 주어집니다. 연속 부분 배열의 합 중 최댓값을 출력하세요.",
        "medium",
        [
            (_nums(a), str(_kadane(a)), h)
            for a, h in [
                ([-2, 1, -3, 4, -1, 2, 1, -5, 4], False),
                ([1], False),
                ([-3, -1, -2], True),
                ([5, 4, -1, 7, 8], True),
            ]
        ],
    ),
    (
        "gcd",
        "최대공약수",
        "공백으로 구분된 두 양의 정수 a, b 가 주어집니다. 최대공약수를 출력하세요.",
        "easy",
        [
            (f"{a} {b}", str(_gcd(a, b)), h)
            for a, b, h in [(12, 18, False), (7, 13, False), (100, 10, True), (1000000, 250000, True)]
        ],
    ),
]


def build_problems() -> list[dict]:
    return [
        {
            "slug": slug,
            "title": title,
            "statement": stmt,
            "difficulty": diff,
            "tests_json": [{"input": i, "expected": e, "hidden": h} for i, e, h in cases],
        }
        for slug, title, stmt, diff, cases in _SPECS
    ]


def seed_if_empty(db: Session) -> int:
    """코딩 문제가 하나도 없을 때만 기본 문제를 넣는다(멱등). 이미 있으면 건드리지 않는다."""
    if db.scalar(select(CodingProblem.id).limit(1)) is not None:
        return 0
    rows = build_problems()
    db.add_all(CodingProblem(**r) for r in rows)
    db.commit()
    logger.info("기본 코딩 문제 %d개 등록", len(rows))
    return len(rows)
