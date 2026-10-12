"""prepare_offline_bundle.py 내부 테스트.
- 가짜 실행기/다운로더로 모든 분기를 검증하고, pip·npm 은 실제 네트워크로도 한 번 확인한다(접속 불가 시 건너뜀).
- 프로젝트 코드의 상수(파일명·모델명·이미지)와 이 도구의 상수가 어긋나면 실패하도록 드리프트 검사를 둔다.
실행: python -m pytest scripts/onprem/tests -q"""

import importlib.util
import json
import pathlib
import re
import socket
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "prepare_offline_bundle", ROOT / "scripts/onprem/prepare_offline_bundle.py"
)
pob = importlib.util.module_from_spec(_SPEC)
sys.modules["prepare_offline_bundle"] = pob
_SPEC.loader.exec_module(pob)


@pytest.fixture(autouse=True)
def small_qwen(monkeypatch):
    """가짜 Qwen 파일이 1.1GB 가 되지 않도록 기대 크기를 작게 바꾼다(크기 검사 로직 자체는 그대로 검증)."""
    monkeypatch.setattr(pob, "QWEN_SIZE", 64)


class Recorder:
    """subprocess.run 대역: 호출을 기록하고, fail_when 에 걸리면 실패 코드를 돌려준다."""

    def __init__(self, fail_when=None):
        self.calls = []
        self.fail_when = fail_when or (lambda args: False)

    def __call__(self, args, cwd=None, env=None, capture_output=True, text=True):
        self.calls.append((list(map(str, args)), cwd, env))
        if self.fail_when(list(map(str, args))):
            return SimpleNamespace(returncode=1, stdout="", stderr="시뮬레이션된 실패")
        # 명령이 만들어야 하는 산출물을 흉내 낸다
        joined = " ".join(map(str, args))
        if "pip download" in joined and "-d" in args:
            (pathlib.Path(args[args.index("-d") + 1]) / "pkg-1.0-py3-none-any.whl").write_bytes(b"whl")
        if args[:2] == ["docker", "save"]:
            pathlib.Path(args[args.index("-o") + 1]).write_bytes(b"tar")
        if "piper.download_voices" in joined:
            d = pathlib.Path(args[args.index("--download-dir") + 1])
            (d / "ko_KR-kss-medium.onnx").write_bytes(b"onnx")
            (d / "ko_KR-kss-medium.onnx.json").write_text("{}")
        if args[:2] == ["npm", "ci"]:
            pathlib.Path(args[args.index("--cache") + 1], "index.bin").write_bytes(b"npm")
        if "DeepFace" in joined:
            (pathlib.Path(env["DEEPFACE_HOME"]) / "w.h5").write_bytes(b"h5")
        return SimpleNamespace(returncode=0, stdout="", stderr="")


def fake_download(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"zip:" + url.encode())


def fake_hf_download_factory(qwen_size=None):
    calls = []

    def hf(repo, filename, dest_dir):
        calls.append((repo, filename))
        dest_dir.mkdir(parents=True, exist_ok=True)
        p = dest_dir / pathlib.Path(filename).name
        p.write_bytes(
            b"x" * (pob.QWEN_SIZE if (filename == pob.QWEN_FILE and qwen_size is None) else (qwen_size or 10))
        )
        return p

    hf.calls = calls
    return hf


def fake_snapshot(repo, cache_dir, ignore):
    d = cache_dir / ("models--" + repo.replace("/", "--"))
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.json").write_text(json.dumps({"ignore": ignore}))


def make_ctx(tmp_path, run=None, qwen_size=None, dry=False):
    out = tmp_path / "bundle"
    return pob.Ctx(
        out=out,
        repo=tmp_path / "repo",
        dry_run=dry,
        run=run or Recorder(),
        download=fake_download,
        hf_download=fake_hf_download_factory(qwen_size),
        hf_snapshot=fake_snapshot,
        python="python-fake",
        log=lambda m: None,
    )


def factory_for(tmp_path, run=None, qwen_size=None):
    return lambda out, dry: make_ctx(tmp_path, run, qwen_size, dry)


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "repo" / "backend").mkdir(parents=True)
    (tmp_path / "repo" / "backend" / "requirements.txt").write_text("six\n")
    for app in ("frontend", "frontend-apply"):
        (tmp_path / "repo" / app).mkdir()
    return tmp_path


def run_cli(tmp_path, *args, run=None, qwen_size=None):
    return pob.main(list(args), ctx_factory=factory_for(tmp_path, run, qwen_size))


def test_bu01_list_shows_all_steps(capsys):
    assert pob.main(["list"]) == 0
    out = capsys.readouterr().out
    for key in ("pip", "npm", "docker", "hf", "piper", "deepface", "llama", "llm"):
        assert key in out


def test_bu02_dry_run_creates_nothing_and_runs_nothing(repo):
    rec = Recorder()
    ctx = make_ctx(repo, run=rec, dry=True)
    assert pob.run_download(ctx, None, set()) == 0
    assert rec.calls == [] and not ctx.out.exists()


def test_bu03_full_run_builds_manifest_with_hashes(repo):
    rec = Recorder()
    assert run_cli(repo, "download", "--out", str(repo / "bundle"), run=rec) == 0
    manifest = json.loads((repo / "bundle" / "manifest.json").read_text(encoding="utf-8"))
    assert all(s["status"] == "ok" for s in manifest["steps"]) and len(manifest["steps"]) == 8
    paths = {f["path"] for f in manifest["files"]}
    assert "llm/models/qwen2.5-1.5b-instruct-q4_k_m.gguf" in paths
    assert "llm/models/smolvlm-500m-instruct-q8.gguf" in paths and "llm/models/smolvlm-mmproj-f16.gguf" in paths
    assert any(p.startswith("llm/bin/llama-b11050-bin-win-vulkan") for p in paths)
    assert "docker/images.tar" in paths and any(
        p.startswith("hf_cache/models--Systran--faster-whisper-small") for p in paths
    )
    assert all(len(f["sha256"]) == 64 for f in manifest["files"])
    assert pob.verify_bundle(repo / "bundle", log=lambda m: None) == 0


def test_bu04_one_failed_step_does_not_stop_others(repo):
    rec = Recorder(fail_when=lambda a: a[:2] == ["docker", "pull"])
    assert run_cli(repo, "download", "--out", str(repo / "bundle"), run=rec) == 1
    manifest = json.loads((repo / "bundle" / "manifest.json").read_text(encoding="utf-8"))
    status = {s["key"]: s["status"] for s in manifest["steps"]}
    assert status["docker"] == "failed" and status["llm"] == "ok" and status["hf"] == "ok"
    logs = []
    assert pob.verify_bundle(repo / "bundle", log=logs.append) == 1
    assert any("docker" in line and "실패" in line for line in logs)


def test_bu05_rerun_only_failed_step_merges_previous(repo):
    bad = Recorder(fail_when=lambda a: a[:2] == ["docker", "pull"])
    run_cli(repo, "download", "--out", str(repo / "bundle"), run=bad)
    assert run_cli(repo, "download", "--out", str(repo / "bundle"), "--only", "docker", run=Recorder()) == 0
    manifest = json.loads((repo / "bundle" / "manifest.json").read_text(encoding="utf-8"))
    assert all(s["status"] == "ok" for s in manifest["steps"])
    assert pob.verify_bundle(repo / "bundle", log=lambda m: None) == 0


def test_bu06_verify_detects_tamper_delete_resize(repo):
    run_cli(repo, "download", "--out", str(repo / "bundle"))
    b = repo / "bundle"
    target = b / "llm/models/smolvlm-mmproj-f16.gguf"
    original = target.read_bytes()
    target.write_bytes(original[:-1] + b"Z")  # 같은 크기, 다른 내용
    logs = []
    assert pob.verify_bundle(b, log=logs.append) == 1 and any(x.strip().startswith("[해시 불일치") for x in logs)
    target.write_bytes(original + b"+")  # 크기 변경
    logs = []
    assert pob.verify_bundle(b, log=logs.append) == 1 and any(x.strip().startswith("[크기 불일치]") for x in logs)
    target.unlink()  # 누락
    logs = []
    assert pob.verify_bundle(b, log=logs.append) == 1 and any(x.strip().startswith("[누락]") for x in logs)


def test_bu07_verify_missing_or_corrupt_manifest_exit2(tmp_path):
    assert pob.verify_bundle(tmp_path, log=lambda m: None) == 2
    (tmp_path / "manifest.json").write_text("깨짐", encoding="utf-8")
    assert pob.verify_bundle(tmp_path, log=lambda m: None) == 2


def test_bu08_unknown_step_name_exit2(repo, capsys):
    assert run_cli(repo, "download", "--out", str(repo / "b"), "--only", "nope") == 2
    assert "알 수 없는 단계" in capsys.readouterr().err


def test_bu09_pip_falls_back_to_sdist_when_wheels_only_fails(repo):
    rec = Recorder(fail_when=lambda a: "--only-binary=:all:" in a)
    ctx = make_ctx(repo, run=rec)
    note = pob.step_pip(ctx)
    cmds = [c for c, _, _ in rec.calls]
    assert "--only-binary=:all:" in cmds[0] and "--only-binary=:all:" not in cmds[1]
    assert "소스 배포본" in note and any("setuptools" in " ".join(c) for c in cmds)


def test_bu10_npm_ci_for_both_apps_with_shared_cache(repo):
    rec = Recorder()
    pob.step_npm(make_ctx(repo, run=rec))
    npm_calls = [(c, cwd) for c, cwd, _ in rec.calls]
    assert {pathlib.Path(cwd).name for _, cwd in npm_calls} == {"frontend", "frontend-apply"}
    assert all(c[:2] == ["npm", "ci"] and "--cache" in c and "--ignore-scripts" in c for c, _ in npm_calls)
    assert len({c[c.index("--cache") + 1] for c, _ in npm_calls}) == 1


def test_bu11_docker_pulls_four_images_amd64_and_saves_once(repo):
    rec = Recorder()
    pob.step_docker(make_ctx(repo, run=rec))
    cmds = [c for c, _, _ in rec.calls]
    pulls = [c for c in cmds if c[:2] == ["docker", "pull"]]
    assert [c[-1] for c in pulls] == list(pob.DOCKER_IMAGES) and all("linux/amd64" in c for c in pulls)
    assert len([c for c in cmds if c[:2] == ["docker", "save"]]) == 1


def test_bu12_hf_models_ignore_unneeded_variants(repo):
    ctx = make_ctx(repo)
    pob.step_hf_models(ctx)
    cfg = json.loads(next((ctx.out / "hf_cache").rglob("config.json")).read_text())
    assert "onnx/*" in cfg["ignore"] and "openvino/*" in cfg["ignore"]
    assert (ctx.out / "hf_cache" / "models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2").is_dir()


def test_bu13_piper_falls_back_to_hf_and_flattens(repo):
    rec = Recorder(fail_when=lambda a: "piper.download_voices" in " ".join(a))
    ctx = make_ctx(repo, run=rec)
    hf_calls = ctx.hf_download.calls
    orig = ctx.hf_download

    def nested(repo_id, filename, dest):
        sub = dest / "ko" / "ko_KR" / "kss" / "medium"
        sub.mkdir(parents=True, exist_ok=True)
        hf_calls.append((repo_id, filename))
        p = sub / pathlib.Path(filename).name
        p.write_bytes(b"v")
        return p

    ctx.hf_download = nested
    pob.step_piper(ctx)
    assert hf_calls == [
        ("rhasspy/piper-voices", "ko/ko_KR/kss/medium/ko_KR-kss-medium.onnx"),
        ("rhasspy/piper-voices", "ko/ko_KR/kss/medium/ko_KR-kss-medium.onnx.json"),
    ]
    voices = ctx.out / "piper_voices"
    assert (voices / "ko_KR-kss-medium.onnx").exists() and (voices / "ko_KR-kss-medium.onnx.json").exists()
    del orig


def test_bu14_llm_models_renamed_and_size_checked(repo):
    ctx = make_ctx(repo)
    pob.step_llm_models(ctx)
    m = ctx.out / "llm" / "models"
    assert (m / "qwen2.5-1.5b-instruct-q4_k_m.gguf").stat().st_size == pob.QWEN_SIZE
    assert (m / "smolvlm-500m-instruct-q8.gguf").exists() and (m / "smolvlm-mmproj-f16.gguf").exists()
    assert not (m / "SmolVLM-500M-Instruct-Q8_0.gguf").exists()


def test_bu15_llm_wrong_qwen_size_fails_step(repo):
    ctx = make_ctx(repo, qwen_size=123)
    with pytest.raises(RuntimeError, match="크기"):
        pob.step_llm_models(ctx)


def test_bu16_deepface_sets_home_env(repo):
    rec = Recorder()
    pob.step_deepface(make_ctx(repo, run=rec))
    _, _, env = rec.calls[0]
    assert env["DEEPFACE_HOME"].endswith("deepface")


def test_bu17_verify_warns_on_platform_mismatch(repo):
    run_cli(repo, "download", "--out", str(repo / "bundle"))
    mpath = repo / "bundle" / "manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    manifest["python"], manifest["platform"] = "3.8.0", "Plan9 mips"
    mpath.write_text(json.dumps(manifest), encoding="utf-8")
    logs = []
    pob.verify_bundle(repo / "bundle", log=logs.append)
    assert any("파이썬 버전/OS가 다릅니다" in x for x in logs)


# --- 프로젝트 코드와의 드리프트 검사 --------------------------------------------------------
def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_bu18_constants_match_project_code():
    llm = _read("backend/app/services/llm_engine.py")
    assert pob.QWEN_FILE in llm
    vision = _read("backend/app/services/whiteboard_vision.py")
    for local_name in pob.SMOLVLM_FILES.values():
        assert local_name in vision
    assert pob.PIPER_VOICE in _read("backend/app/services/tts_engine.py")
    assert pob.MINILM_REPO.split("/")[1] in _read("backend/app/services/rag_engine.py")
    assert re.search(r'_MODEL_SIZE\s*=\s*"small"', _read("backend/app/services/stt_engine.py"))
    assert "Systran/faster-whisper-small" == pob.WHISPER_REPO
    compose = _read("backend/docker-compose.yml")
    sandbox = _read("backend/app/services/code_sandbox.py")
    for image in pob.DOCKER_IMAGES:
        assert image in compose or image in sandbox, image


# --- 실제 네트워크 확인(pip, npm) ----------------------------------------------------------
def _online(host, port=443):
    try:
        socket.create_connection((host, port), timeout=4).close()
        return True
    except OSError:
        return False


@pytest.mark.skipif(not (_online("pypi.org") and _online("registry.npmjs.org")), reason="네트워크 접속 불가")
def test_bu19_real_pip_and_npm_download(tmp_path):
    repo_dir = tmp_path / "repo"
    (repo_dir / "backend").mkdir(parents=True)
    (repo_dir / "backend" / "requirements.txt").write_text("six==1.16.0\n")
    for app in ("frontend", "frontend-apply"):
        d = repo_dir / app
        d.mkdir()
        (d / "package.json").write_text(
            json.dumps({"name": app, "version": "1.0.0", "dependencies": {"is-number": "7.0.0"}})
        )
        subprocess.run(
            ["npm", "install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund"],
            cwd=d,
            check=True,
            capture_output=True,
        )
    out = tmp_path / "bundle"
    ctx = pob.Ctx(out=out, repo=repo_dir, log=lambda m: None)
    pob.step_pip(ctx)
    pob.step_npm(ctx)
    assert list((out / "pip").glob("six-*.whl"))
    assert any((out / "npm-cache").rglob("*"))
    # 받은 npm 캐시로 인터넷 없이 설치되는지(--offline) 확인
    install_dir = tmp_path / "offline_install"
    install_dir.mkdir()
    for f in ("package.json", "package-lock.json"):
        (install_dir / f).write_bytes((repo_dir / "frontend" / f).read_bytes())
    proc = subprocess.run(
        ["npm", "ci", "--offline", "--ignore-scripts", "--cache", str(out / "npm-cache")],
        cwd=install_dir,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert (install_dir / "node_modules" / "is-number").is_dir()
    # 받은 휠로 인터넷 없이 설치되는지(--no-index) 확인
    target = tmp_path / "pip_target"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-index",
            "--find-links",
            str(out / "pip"),
            "--target",
            str(target),
            "six==1.16.0",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
