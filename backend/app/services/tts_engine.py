"""ITTSEngine 어댑터 구현체 — Piper(한국어 `ko_KR-kss-medium`) (03-system-design.md
§2.5 실측 근거, §4.5 어댑터 인터페이스 원칙, DEC-017 GPL-3.0-or-later 격리 대응).

REQ-006: 임의의 텍스트를 실제 음성(WAV)으로 합성한다. STT(`stt_engine.py`)와 달리
Piper 라이브러리를 이 프로세스에 **직접 import하지 않는다** — DEC-017이 요구하는
격리 원칙(정적 링크 금지, 별도 실행 파일/프로세스로만 연동)에 따라 항상
`python -m piper`를 **별도 서브프로세스**로 실행해 표준 파일 인터페이스(입력
텍스트 파일 → 출력 WAV 파일)로만 연동한다. 이후 라이선스 법무검토(§2.5, §8-2)
결과에 따라 교체해야 할 경우, 이 모듈(`ITTSEngine` 구현체)만 교체하면 되고
호출부(`app/api/v1/interviews.py`)는 `synthesize_speech_file()` 시그니처를 그대로
사용한다.

**연결 경계(unit-6, note.md §2 참고)**: 이 모듈은 텍스트→음성 변환 자체는 실제로
동작하지만, "AI가 생성한 응답 텍스트"를 이 모듈에 넘기는 것은 LLM(unit-7)이 아직
없어 이 유닛 범위가 아니다. `app/api/v1/interviews.py`의 `POST
/interviews/{id}/tts-preview`가 이 모듈을 실제로 호출하는 유일한 현재 경로이며,
unit-7은 AI 응답(`speak_text`)이 준비되는 시점에 동일한 `synthesize_speech_file()`을
호출해 `turn_result.audio_url`(§4.3)을 채우면 된다.
"""
import logging
import subprocess
import sys
import threading
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)

# backend/var/piper_voices, backend/var/media/tts — 둘 다 실행 중 생성되는 산출물이라
# 저장소에 커밋하지 않는다(.gitignore에 `backend/var/` 추가, DEC-017과 무관한 순수
# 구현 세부값).
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
VOICE_DIR = _BACKEND_ROOT / "var" / "piper_voices"
MEDIA_ROOT = _BACKEND_ROOT / "var" / "media"
_TTS_MEDIA_SUBDIR = "tts"

# 03-design §2.5 실측 선정값 그대로: 한국어 ko_KR-kss-medium.
_VOICE_NAME = "ko_KR-kss-medium"
_MODEL_PATH = VOICE_DIR / f"{_VOICE_NAME}.onnx"
_CONFIG_PATH = VOICE_DIR / f"{_VOICE_NAME}.onnx.json"

# 03-design §5.4: TTS 단계 타임아웃 10초(실측 RTF 0.056 대비 충분한 여유). 모델
# 다운로드(네트워크 의존, 최초 1회성)는 이 예산과 무관한 별도 타임아웃을 둔다.
_SYNTHESIS_TIMEOUT_SECONDS = 10
_DOWNLOAD_TIMEOUT_SECONDS = 120

_download_lock = threading.Lock()


class TtsSynthesisError(Exception):
    """음성 모델 준비 실패, 서브프로세스 실행 실패, 타임아웃 등 TTS 처리 중 발생한
    모든 예외를 단일 계약으로 승격한다.

    호출부(app/api/v1/interviews.py)는 이 예외를 03-design §5.4의 `AI_SERVICE_TIMEOUT`
    (504)으로 매핑한다(stt_engine.py의 `SttTranscriptionError`와 동일 원칙).
    """


class ITTSEngine(ABC):
    """03-design §4.5 어댑터 인터페이스 — TTS 구현체 교체 가능성에 대한 최소 대비."""

    @abstractmethod
    def synthesize(self, text: str) -> bytes:
        """텍스트를 WAV(PCM) 오디오 바이트로 변환한다."""


def _ensure_voice_downloaded() -> None:
    if _MODEL_PATH.exists() and _CONFIG_PATH.exists():
        return
    with _download_lock:
        if _MODEL_PATH.exists() and _CONFIG_PATH.exists():
            return
        VOICE_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("Piper 한국어 음성모델(%s) 다운로드 시작", _VOICE_NAME)
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "piper.download_voices",
                    _VOICE_NAME,
                    "--download-dir",
                    str(VOICE_DIR),
                ],
                capture_output=True,
                timeout=_DOWNLOAD_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TtsSynthesisError("음성 모델 다운로드가 시간 내에 완료되지 않았습니다.") from exc

        if result.returncode != 0 or not (_MODEL_PATH.exists() and _CONFIG_PATH.exists()):
            raise TtsSynthesisError(
                "음성 모델(ko_KR-kss-medium) 다운로드에 실패했습니다: "
                + result.stderr.decode("utf-8", errors="replace")
            )
        logger.info("Piper 한국어 음성모델(%s) 다운로드 완료", _VOICE_NAME)


class PiperTTSEngine(ITTSEngine):
    """DEC-017: Piper(GPL-3.0-or-later)를 이 프로세스에 링크하지 않고 매 합성마다
    `python -m piper` 서브프로세스를 실행해 격리한다.
    """

    def synthesize(self, text: str) -> bytes:
        _ensure_voice_downloaded()

        run_id = uuid.uuid4().hex
        work_dir = MEDIA_ROOT / ".tts_tmp"
        work_dir.mkdir(parents=True, exist_ok=True)
        input_path = work_dir / f"{run_id}.txt"
        output_path = work_dir / f"{run_id}.wav"
        try:
            # 표준입력(stdin) 파이프 대신 UTF-8 파일을 명시적으로 써서 넘긴다 —
            # Windows 콘솔/서브프로세스 stdin 인코딩이 시스템 코드페이지를 따라가며
            # 한글이 손상되는 문제(unit-4/5-note.md가 이미 겪은 것과 동일 현상)를
            # 실측으로 확인해 우회했다.
            input_path.write_text(text, encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "piper",
                    "-m",
                    str(_MODEL_PATH),
                    "-c",
                    str(_CONFIG_PATH),
                    "-i",
                    str(input_path),
                    "-f",
                    str(output_path),
                ],
                capture_output=True,
                timeout=_SYNTHESIS_TIMEOUT_SECONDS,
                check=False,
            )
            if result.returncode != 0 or not output_path.exists() or output_path.stat().st_size == 0:
                raise TtsSynthesisError(
                    "음성 합성에 실패했습니다: " + result.stderr.decode("utf-8", errors="replace")
                )
            return output_path.read_bytes()
        except subprocess.TimeoutExpired as exc:
            raise TtsSynthesisError("음성 합성이 시간 내에 완료되지 않았습니다.") from exc
        finally:
            input_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)


_engine: ITTSEngine | None = None
_engine_lock = threading.Lock()


def get_tts_engine() -> ITTSEngine:
    """§4.5 어댑터 팩토리 — 교체 시 이 함수 내부만 바꾸면 호출부 영향 없음."""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = PiperTTSEngine()
    return _engine


def synthesize_speech_file(text: str) -> str:
    """텍스트를 합성해 `MEDIA_ROOT/tts/`에 저장하고, 클라이언트가 재생할 수 있는
    상대 URL(§4.3 `audio_url` 표기와 동일한 `/media/xxx.wav` 형식)을 반환한다.
    """
    engine = get_tts_engine()
    wav_bytes = engine.synthesize(text)

    tts_dir = MEDIA_ROOT / _TTS_MEDIA_SUBDIR
    tts_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4()}.wav"
    (tts_dir / filename).write_bytes(wav_bytes)

    return f"/media/{_TTS_MEDIA_SUBDIR}/{filename}"
