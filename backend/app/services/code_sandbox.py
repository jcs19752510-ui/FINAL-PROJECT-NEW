"""코드 실행 샌드박스 (원안 REQ-F-004/REQ-022, 2026-09-22 사용자 승인, unit-29).

**DEC-008(03-system-design.md)가 "코드 실행 기능은 Out-of-Scope"라고 명시적으로
확정한 결정을 이 유닛이 뒤집는다** — 사용자가 이 위험을 명시적으로 인지한
상태에서 승인해 진행한다. `app/models/code_submission.py`가 "이 테이블/모델은
순수 저장소이며 코드 실행과 관련된 어떤 필드/로직도 갖지 않는다"고 명시한 것도
마찬가지로 이 유닛으로 사실상 무효화된다 — 인수인계 문서에 반드시 남긴다.

**보안 설계 원칙(20년차 보안 담당자 기준 — 임의 사용자 코드 실행은 RCE와
동급 위험)**: 아래 전부를 동시에 적용해야만 "사용 가능한 최소 안전선"으로
간주한다. 하나라도 빠지면 이 모듈을 프로덕션에 연결하지 않는다.

1. **네트워크 완전 차단** (`--network none`) — 데이터 유출/추가 공격의 가장
   흔한 경로를 원천 차단.
2. **읽기 전용 루트 파일시스템** (`--read-only`) + 코드 실행에 필요한 `/tmp`만
   임시 tmpfs로 허용 — 컨테이너 탈출 후에도 영구 변경 불가.
3. **비루트 사용자** (`--user 65534:65534`, nobody) — 컨테이너 내부 권한 상승
   표면 최소화.
4. **모든 리눅스 capability 제거** (`--cap-drop=ALL`) — 권한 있는 시스템 콜
   차단.
5. **`--security-opt=no-new-privileges`** — setuid 바이너리로 권한 상승 차단.
6. **메모리/CPU/프로세스 수 제한** (`--memory`, `--cpus`, `--pids-limit`) —
   리소스 고갈(fork bomb 등)로 호스트 전체에 영향 주는 것을 방지.
7. **실행 시간 제한 + 강제 종료** — 무한루프가 컨테이너를 영원히 점유하지
   않도록 타임아웃 후 `docker kill`.
8. **`--rm`** — 실행 후 컨테이너를 반드시 즉시 제거(디스크 누적 방지, §6.2
   최소수집 원칙과 동일 정신).
9. 코드 자체는 호스트 임시 디렉터리에 썼다가 **읽기 전용으로만** 마운트 —
   컨테이너 안에서 그 파일을 고쳐도 호스트에는 반영되지 않는다.

**지원 언어(이번 유닛 범위)**: `python`, `javascript` 2종만 실제로 구현·검증
했다. `code_submissions.py`의 11개 언어 화이트리스트 중 나머지(java/c/cpp 등,
컴파일이 필요한 언어)는 같은 아키텍처를 따르되 언어별 빌드 이미지/컴파일
스크립트가 추가로 필요해 이번 범위에서 제외했다(unit-29-note.md §4 인수인계).
"""
import logging
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 8
_MEMORY_LIMIT = "128m"
_CPU_LIMIT = "0.5"
_PIDS_LIMIT = "32"
_MAX_OUTPUT_CHARS = 4000  # 무한 출력(예: `while True: print(...)`)으로 응답이 비대해지는 것 방지

_LANGUAGE_RUNTIMES = {
    "python": {
        "image": "python:3.13-slim",
        "filename": "main.py",
        "command": ["python", "/sandbox/main.py"],
    },
    "javascript": {
        "image": "node:20-slim",
        "filename": "main.js",
        "command": ["node", "/sandbox/main.js"],
    },
}


class UnsupportedSandboxLanguage(Exception):
    pass


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int | None
    timed_out: bool


def execute_code_sandboxed(language: str, code: str) -> SandboxResult:
    """`docker run`을 서브프로세스로 실행해 격리된 컨테이너 안에서만 코드를
    돌린다. 모듈 docstring의 9가지 원칙을 전부 적용한다 — 이 함수를 수정할
    때 그중 하나라도 빠뜨리면 안 된다.
    """
    runtime = _LANGUAGE_RUNTIMES.get(language)
    if runtime is None:
        raise UnsupportedSandboxLanguage(
            f"'{language}'는 샌드박스 실행을 지원하지 않습니다(지원: {', '.join(_LANGUAGE_RUNTIMES)})."
        )

    with tempfile.TemporaryDirectory(prefix="code_sandbox_") as tmpdir:
        code_path = Path(tmpdir) / runtime["filename"]
        code_path.write_text(code, encoding="utf-8")

        container_name = f"sandbox-{uuid.uuid4().hex[:12]}"
        docker_cmd = [
            "docker", "run",
            "--name", container_name,
            "--rm",
            "--network", "none",
            "--read-only",
            "--tmpfs", "/tmp:rw,size=16m",
            "--user", "65534:65534",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--memory", _MEMORY_LIMIT,
            "--cpus", _CPU_LIMIT,
            "--pids-limit", _PIDS_LIMIT,
            "-v", f"{code_path}:/sandbox/{runtime['filename']}:ro",
            runtime["image"],
            *runtime["command"],
        ]

        timed_out = False
        try:
            proc = subprocess.run(
                docker_cmd,
                capture_output=True,
                timeout=_TIMEOUT_SECONDS,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            stdout, stderr, exit_code = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            # `docker run --rm`은 타임아웃으로 subprocess가 죽어도 컨테이너 자체는
            # 계속 돌 수 있다 — 이름으로 명시적으로 kill해 좀비 컨테이너를 남기지
            # 않는다(모듈 원칙 8번, 리소스 누적 방지).
            subprocess.run(["docker", "kill", container_name], capture_output=True, timeout=5, check=False)
            stdout, stderr, exit_code = "", "실행 시간 제한을 초과해 강제 종료되었습니다.", None

        return SandboxResult(
            stdout=stdout[:_MAX_OUTPUT_CHARS],
            stderr=stderr[:_MAX_OUTPUT_CHARS],
            exit_code=exit_code,
            timed_out=timed_out,
        )
