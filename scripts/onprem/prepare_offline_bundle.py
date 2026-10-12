#!/usr/bin/env python3
"""폐쇄망(내부망) 반입용 설치물 번들을 만드는 도구 — 인터넷이 되는 PC에서 실행한다.

폐쇄망에는 인터넷이 없어서 설치/첫 실행 때 자동으로 내려받던 부품(패키지, Docker 이미지, AI 모델)이
없으면 프로그램이 멈춘다. 이 도구가 필요한 부품을 한 폴더(번들)에 모으고, 파일마다 크기와 SHA-256 을
적은 manifest.json 을 만든다. 번들을 USB/사내 전송으로 옮긴 뒤, 폐쇄망 쪽에서 `verify` 로 빠짐·손상을
확인한다. 설치 방법은 docs/onprem/설치물반입목록.md 참고.

사용법 (표준 라이브러리만 사용, 단계별로 필요한 도구는 아래 REQUIRES 참고):
    python prepare_offline_bundle.py list                              # 반입 목록 출력
    python prepare_offline_bundle.py download --out D:\\bundle          # 전체 다운로드
    python prepare_offline_bundle.py download --out D:\\bundle --only pip,npm
    python prepare_offline_bundle.py download --out D:\\bundle --dry-run  # 실행할 일만 출력
    python prepare_offline_bundle.py verify --out E:\\bundle            # 폐쇄망 쪽 무결성 확인

종료코드: 0 = 전부 성공 / 1 = 일부 단계 실패(나머지는 계속 진행됨) / 2 = 사용법·입력 오류
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_NAME = "manifest.json"

# --- 출처 (확인 상태를 함께 적는다) -----------------------------------------------------
LLAMA_CPP_TAG = "b11050"  # 프로젝트에서 실제 검증한 릴리즈(unit-7-note.md §6)
LLAMA_ZIPS = (
    f"llama-{LLAMA_CPP_TAG}-bin-win-vulkan-x64.zip",
    f"llama-{LLAMA_CPP_TAG}-bin-win-cpu-x64.zip",
)
LLAMA_BASE = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_CPP_TAG}/"
QWEN_REPO, QWEN_FILE, QWEN_SIZE = "Qwen/Qwen2.5-1.5B-Instruct-GGUF", "qwen2.5-1.5b-instruct-q4_k_m.gguf", 1_117_320_736
# 아래 SmolVLM 저장소/파일명은 프로젝트 문서에 출처가 없어 일반 지식 기준이다 — 첫 실행 때 받아지는지 확인 필요.
SMOLVLM_REPO = "ggml-org/SmolVLM-500M-Instruct-GGUF"
SMOLVLM_FILES = {  # 저장소 파일명 -> 프로젝트 코드가 찾는 파일명(whiteboard_vision.py)
    "SmolVLM-500M-Instruct-Q8_0.gguf": "smolvlm-500m-instruct-q8.gguf",
    "mmproj-SmolVLM-500M-Instruct-f16.gguf": "smolvlm-mmproj-f16.gguf",
}
WHISPER_REPO = "Systran/faster-whisper-small"  # faster-whisper 'small' 모델의 저장소(코드: stt_engine.py)
MINILM_REPO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"  # 코드: rag_engine.py
PIPER_VOICE = "ko_KR-kss-medium"  # 코드: tts_engine.py
DOCKER_IMAGES = (
    "pgvector/pgvector:pg16",
    "redis:7-alpine",
    "python:3.13-slim",
    "node:20-slim",
)  # compose + code_sandbox.py
HF_IGNORE = ["onnx/*", "openvino/*", "*.onnx", "*.msgpack", "*.h5", "tf_model*", "rust_model*"]  # 쓰지 않는 변환본


@dataclass
class Ctx:
    out: Path
    repo: Path = REPO_ROOT
    dry_run: bool = False
    run: Callable[..., subprocess.CompletedProcess] = field(default=subprocess.run)
    download: Callable[[str, Path], None] | None = None  # 테스트에서 교체
    hf_download: Callable[[str, str, Path], Path] | None = None  # (repo, filename, dest_dir) -> 경로
    hf_snapshot: Callable[[str, Path, list[str]], None] | None = None
    python: str = sys.executable
    log: Callable[[str], None] = field(default=print)

    def mkdir(self, path: Path) -> None:
        if not self.dry_run:
            path.mkdir(parents=True, exist_ok=True)

    def sh(self, args: list[str], cwd: Path | None = None, env: dict | None = None) -> None:
        self.log("  $ " + " ".join(str(a) for a in args))
        if self.dry_run:
            return
        import os

        full_env = {**os.environ, **(env or {})}
        proc = self.run(args, cwd=cwd, env=full_env, capture_output=True, text=True)
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-8:]
            raise RuntimeError(f"명령 실패(종료코드 {proc.returncode}): {' '.join(map(str, args))}\n" + "\n".join(tail))


# --- 실제 다운로드 구현 ------------------------------------------------------------------
def _default_download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=60) as resp, open(tmp, "wb") as fh:  # noqa: S310 - 고정 URL
        shutil.copyfileobj(resp, fh)
    tmp.replace(dest)


def _default_hf_download(repo: str, filename: str, dest_dir: Path) -> Path:
    from huggingface_hub import hf_hub_download  # 지연 import: 이 단계에서만 필요

    dest_dir.mkdir(parents=True, exist_ok=True)
    return Path(hf_hub_download(repo_id=repo, filename=filename, local_dir=str(dest_dir)))


def _default_hf_snapshot(repo: str, cache_dir: Path, ignore: list[str]) -> None:
    from huggingface_hub import snapshot_download

    cache_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=repo, cache_dir=str(cache_dir), ignore_patterns=ignore)


# --- 단계 정의 ---------------------------------------------------------------------------
def step_pip(ctx: Ctx) -> str:
    wheels = ctx.out / "pip"
    ctx.mkdir(wheels)
    req = ctx.repo / "backend" / "requirements.txt"
    base = [ctx.python, "-m", "pip", "download", "-r", str(req), "-d", str(wheels)]
    try:
        ctx.sh(base + ["--only-binary=:all:"])
        note = "휠(wheel)만 사용"
    except RuntimeError:
        ctx.log(
            "  휠만으로는 받지 못한 패키지가 있어 소스 배포본 허용으로 다시 시도합니다"
            "(폐쇄망에서 빌드 도구가 필요할 수 있음)."
        )
        ctx.sh(base)
        note = "일부 소스 배포본 포함(빌드 도구 필요 가능)"
    ctx.sh([ctx.python, "-m", "pip", "download", "pip", "setuptools", "wheel", "-d", str(wheels)])
    return note + f" / 대상 파이썬 {platform.python_version()}, {platform.system()} {platform.machine()}"


def step_npm(ctx: Ctx) -> str:
    cache = ctx.out / "npm-cache"
    ctx.mkdir(cache)
    for app in ("frontend", "frontend-apply"):
        app_dir = ctx.repo / app
        ctx.sh(["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund", "--cache", str(cache)], cwd=app_dir)
    return "npm 캐시에 두 프런트엔드의 의존성을 채움(폐쇄망: npm ci --offline --cache <경로>)"


def step_docker(ctx: Ctx) -> str:
    target = ctx.out / "docker"
    ctx.mkdir(target)
    for image in DOCKER_IMAGES:
        ctx.sh(["docker", "pull", "--platform", "linux/amd64", image])
    ctx.sh(["docker", "save", "-o", str(target / "images.tar"), *DOCKER_IMAGES])
    return "이미지 " + ", ".join(DOCKER_IMAGES)


def step_hf_models(ctx: Ctx) -> str:
    snap = ctx.hf_snapshot or _default_hf_snapshot
    cache = ctx.out / "hf_cache"
    for repo in (WHISPER_REPO, MINILM_REPO):
        ctx.log(f"  모델 받기: {repo}")
        if not ctx.dry_run:
            snap(repo, cache, HF_IGNORE)
    return "HF 캐시 형식으로 저장(폐쇄망: HF_HUB_CACHE=<경로>, HF_HUB_OFFLINE=1)"


def step_piper(ctx: Ctx) -> str:
    dest = ctx.out / "piper_voices"
    ctx.mkdir(dest)
    try:
        ctx.sh([ctx.python, "-m", "piper.download_voices", PIPER_VOICE, "--download-dir", str(dest)])
        return "piper.download_voices 사용(앱이 쓰는 방식과 동일)"
    except RuntimeError:
        hf = ctx.hf_download or _default_hf_download
        for name in (f"{PIPER_VOICE}.onnx", f"{PIPER_VOICE}.onnx.json"):
            ctx.log(f"  piper 미설치 또는 실패 — HF 직접 받기: {name}")
            if not ctx.dry_run:
                hf("rhasspy/piper-voices", f"ko/ko_KR/kss/medium/{name}", dest)
        # local_dir 로 받으면 하위 폴더 구조가 생기므로 평평하게 정리한다
        if not ctx.dry_run:
            for p in dest.rglob("ko_KR-kss-medium*"):
                if p.parent != dest:
                    p.replace(dest / p.name)
        return "HF 직접 받기(경로 미검증)"


def step_deepface(ctx: Ctx) -> str:
    home = ctx.out / "deepface"
    ctx.mkdir(home)
    code = (
        "import numpy as np\n"
        "from deepface import DeepFace\n"
        "DeepFace.analyze(np.zeros((224,224,3),dtype='uint8'), actions=['emotion'], "
        "detector_backend='mtcnn', enforce_detection=False)\n"
    )
    ctx.sh([ctx.python, "-c", code], env={"DEEPFACE_HOME": str(home)})
    return "DeepFace 감정 모델 가중치(폐쇄망: DEEPFACE_HOME=<경로>). deepface/tensorflow 설치된 파이썬 필요"


def step_llama_bin(ctx: Ctx) -> str:
    dl = ctx.download or _default_download
    for name in LLAMA_ZIPS:
        ctx.log(f"  받기: {name}")
        if not ctx.dry_run:
            dl(LLAMA_BASE + name, ctx.out / "llm" / "bin" / name)
    return f"llama.cpp {LLAMA_CPP_TAG} Windows 실행파일(Vulkan/CPU zip). 압축 해제 위치는 설치물반입목록.md 참고"


def step_llm_models(ctx: Ctx) -> str:
    hf = ctx.hf_download or _default_hf_download
    models = ctx.out / "llm" / "models"
    notes = []
    if not ctx.dry_run:
        path = hf(QWEN_REPO, QWEN_FILE, models)
        if path.stat().st_size != QWEN_SIZE:
            raise RuntimeError(f"{QWEN_FILE} 크기가 기대값({QWEN_SIZE})과 다릅니다: {path.stat().st_size}")
        notes.append("Qwen 크기 일치")
        for repo_name, local_name in SMOLVLM_FILES.items():
            got = hf(SMOLVLM_REPO, repo_name, models)
            final = models / local_name
            if got != final:
                got.replace(final)
        notes.append("SmolVLM 파일명을 프로젝트 이름으로 변경")
    else:
        ctx.log(f"  받기: {QWEN_REPO}/{QWEN_FILE}, {SMOLVLM_REPO} 2개 파일")
    return "; ".join(notes) or "모델 3개 파일"


@dataclass(frozen=True)
class Step:
    key: str
    title: str
    requires: str
    fn: Callable[[Ctx], str]


STEPS = (
    Step("pip", "파이썬 패키지(backend/requirements.txt)", "pip", step_pip),
    Step("npm", "프런트엔드 패키지(frontend, frontend-apply)", "node/npm", step_npm),
    Step("docker", "Docker 이미지 4종", "Docker 실행 중", step_docker),
    Step("hf", "음성인식(Whisper small)·임베딩(MiniLM) 모델", "pip install huggingface_hub", step_hf_models),
    Step("piper", "음성 합성 음성파일(ko_KR-kss-medium)", "piper-tts 또는 huggingface_hub", step_piper),
    Step("deepface", "표정 분석(DeepFace) 가중치", "deepface/tensorflow 설치된 파이썬", step_deepface),
    Step("llama", "llama.cpp 실행파일(Windows zip 2종)", "인터넷(GitHub)", step_llama_bin),
    Step("llm", "LLM(Qwen 1.5B)·비전(SmolVLM) 모델 파일", "pip install huggingface_hub", step_llm_models),
)


# --- 매니페스트 / 검증 --------------------------------------------------------------------
def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(out: Path, results: list[dict]) -> dict:
    files = []
    for p in sorted(out.rglob("*")):
        if p.is_file() and p.name != MANIFEST_NAME and not p.name.endswith(".part"):
            files.append({"path": p.relative_to(out).as_posix(), "size": p.stat().st_size, "sha256": sha256_of(p)})
    return {
        "created": datetime.now().isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "platform": f"{platform.system()} {platform.machine()}",
        "steps": results,
        "files": files,
    }


def verify_bundle(out: Path, log: Callable[[str], None] = print) -> int:
    manifest_path = out / MANIFEST_NAME
    if not manifest_path.exists():
        log(f"[오류] {manifest_path} 가 없습니다. 번들 폴더가 맞는지, 복사가 끝났는지 확인하세요.")
        return 2
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = manifest["files"]
    except (ValueError, KeyError):
        log("[오류] manifest.json 형식이 올바르지 않습니다.")
        return 2
    missing, bad_size, bad_hash = [], [], []
    for entry in entries:
        p = out / entry["path"]
        if not p.is_file():
            missing.append(entry["path"])
        elif p.stat().st_size != entry["size"]:
            bad_size.append(entry["path"])
        elif sha256_of(p) != entry["sha256"]:
            bad_hash.append(entry["path"])
    failed_steps = [s for s in manifest.get("steps", []) if s.get("status") == "failed"]
    skipped_steps = [s for s in manifest.get("steps", []) if s.get("status") == "skipped"]
    log(f"번들 생성 {manifest.get('created')} / 만든 PC: 파이썬 {manifest.get('python')}, {manifest.get('platform')}")
    log(f"이 PC: 파이썬 {platform.python_version()}, {platform.system()} {platform.machine()}")
    if (
        manifest.get("python", "").rsplit(".", 1)[0] != platform.python_version().rsplit(".", 1)[0]
        or manifest.get("platform") != f"{platform.system()} {platform.machine()}"
    ):
        log("[주의] 번들을 만든 PC와 파이썬 버전/OS가 다릅니다. 파이썬 패키지(wheel)가 맞지 않을 수 있습니다.")
    log(f"파일 {len(entries)}개 확인: 누락 {len(missing)}, 크기 불일치 {len(bad_size)}, 해시 불일치 {len(bad_hash)}")
    for label, items in (("누락", missing), ("크기 불일치", bad_size), ("해시 불일치(손상)", bad_hash)):
        for item in items[:20]:
            log(f"  [{label}] {item}")
    for s in failed_steps:
        log(f"  [생성 당시 실패한 단계] {s['key']}: {s.get('note', '')}")
    for s in skipped_steps:
        log(f"  [주의: 번들에 포함되지 않은 단계] {s['key']} — 폐쇄망에서 해당 부품이 필요하면 다시 받아야 합니다.")
    ok = not (missing or bad_size or bad_hash or failed_steps)
    log("결과: " + ("PASS — 번들이 완전합니다." if ok else "FAIL — 위 항목을 해결하세요."))
    return 0 if ok else 1


# --- 실행 ---------------------------------------------------------------------------------
def run_download(ctx: Ctx, only: set[str] | None, skip: set[str]) -> int:
    ctx.mkdir(ctx.out)
    previous: dict[str, dict] = {}
    prev_path = ctx.out / MANIFEST_NAME
    if prev_path.exists():
        try:
            previous = {s["key"]: s for s in json.loads(prev_path.read_text(encoding="utf-8")).get("steps", [])}
        except (ValueError, KeyError, TypeError):
            previous = {}
    results: list[dict] = []
    for step in STEPS:
        if (only and step.key not in only) or step.key in skip:
            kept = previous.get(step.key)
            results.append(
                kept
                if kept and kept.get("status") == "ok"
                else {"key": step.key, "title": step.title, "status": "skipped", "note": "이번 실행에서 제외"}
            )
            continue
        ctx.log(f"\n[{step.key}] {step.title}  (필요: {step.requires})")
        try:
            note = step.fn(ctx)
            results.append({"key": step.key, "title": step.title, "status": "ok", "note": note})
            ctx.log(f"  → {'예정(dry-run, 실행하지 않음)' if ctx.dry_run else '완료'}: {note}")
        except Exception as exc:  # noqa: BLE001 — 한 단계 실패가 나머지를 막지 않도록 모두 잡는다
            results.append({"key": step.key, "title": step.title, "status": "failed", "note": str(exc).splitlines()[0]})
            ctx.log(f"  → 실패: {exc}")
    failed = [r for r in results if r["status"] == "failed"]
    if ctx.dry_run:
        ctx.log("\n(dry-run: 실제 다운로드와 manifest 생성은 하지 않았습니다.)")
        return 0
    manifest = build_manifest(ctx.out, results)
    (ctx.out / MANIFEST_NAME).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    ctx.log(f"\nmanifest.json 작성: 파일 {len(manifest['files'])}개")
    for r in results:
        ctx.log(f"  {r['status']:<8}{r['key']:<10}{r['title']}")
    if failed:
        ctx.log(
            "\n일부 단계가 실패했습니다. 실패한 단계만 `--only 단계이름` 으로 다시 실행하면 manifest 가 갱신됩니다."
        )
    return 1 if failed else 0


def print_list(log: Callable[[str], None] = print) -> None:
    log("반입 목록 (인터넷이 되는 PC에서 download 로 한 번에 받습니다)")
    for s in STEPS:
        log(f"  {s.key:<9}{s.title}   [필요: {s.requires}]")


def main(argv: list[str] | None = None, ctx_factory: Callable[[Path, bool], Ctx] | None = None) -> int:
    parser = argparse.ArgumentParser(description="폐쇄망 반입용 설치물 번들 만들기/검증")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="반입 목록 출력")
    dl = sub.add_parser("download", help="번들 만들기(인터넷 PC)")
    dl.add_argument("--out", required=True)
    dl.add_argument("--only", default="", help="쉼표로 구분한 단계 이름만 실행")
    dl.add_argument("--skip", default="", help="쉼표로 구분한 단계 이름 제외")
    dl.add_argument("--dry-run", action="store_true")
    vf = sub.add_parser("verify", help="번들 무결성 확인(폐쇄망 PC)")
    vf.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    if args.cmd == "list":
        print_list()
        return 0
    out = Path(args.out)
    if args.cmd == "verify":
        return verify_bundle(out)
    keys = {s.key for s in STEPS}
    only = {k for k in args.only.split(",") if k}
    skip = {k for k in args.skip.split(",") if k}
    unknown = (only | skip) - keys
    if unknown:
        print(
            f"[오류] 알 수 없는 단계 이름: {', '.join(sorted(unknown))} (가능: {', '.join(sorted(keys))})",
            file=sys.stderr,
        )
        return 2
    ctx = ctx_factory(out, args.dry_run) if ctx_factory else Ctx(out=out, dry_run=args.dry_run)
    return run_download(ctx, only or None, skip)


if __name__ == "__main__":
    sys.exit(main())
