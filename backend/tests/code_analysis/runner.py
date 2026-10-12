# ruff: noqa: E501, E741
"""테스트 전용 실행기 — 신뢰하는 기준 풀이를 로컬 python/node 로 실행한다. 운영에서는 code_sandbox(격리 컨테이너)만 쓴다."""

import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class R:
    stdout: str
    stderr: str
    exit_code: int | None
    timed_out: bool


def local_runner(language: str, code: str, stdin_text: str | None = None) -> R:
    exe = {"python": [sys.executable], "javascript": [shutil.which("node") or "node"]}[language]
    suffix = ".py" if language == "python" else ".js"
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / f"main{suffix}"
        f.write_text(code, encoding="utf-8")
        try:
            p = subprocess.run(
                [*exe, str(f)], input=stdin_text or "", capture_output=True, text=True, timeout=5, check=False
            )
            return R(p.stdout, p.stderr, p.returncode, False)
        except subprocess.TimeoutExpired:
            return R("", "시간 초과", None, True)
