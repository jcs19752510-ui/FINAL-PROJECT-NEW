"""음성 운율(Prosody) 분석 — 원안 REQ-018/REQ-019 축소판, 2026-09-22 사용자 승인
(unit-24, `docs/harness/units/unit-24-note.md` 참고).

원 계획서(§5.3.2)는 "librosa 라이브러리를 이용한 오디오 신호 처리"로 Pitch(높낮이),
Jitter(떨림), 말하기 속도를 분석해 "자신감"/"긴장도"를 측정한다고 명시했다. 이
모듈은 그 신호처리 부분만 구현한다 — "자신감/긴장도"라는 정성적 라벨을 자동으로
붙이지는 않는다(검증되지 않은 자체 알고리즘으로 사람을 평가하는 것은 REQ-N-004
공정성/설명가능성 원칙과 충돌 소지가 있어, 원시 수치(Hz/비율)만 반환하고 해석은
사람 몫으로 남긴다 — 이 판단은 ③ 매트릭스 근거란에 이미 명시된 "신뢰도 검증 필요"
캐비엇의 연장).

**디코딩 경로**: librosa의 기본 로더(soundfile→audioread 폴백) 대신, faster-whisper가
이미 의존하는 PyAV(`av`)로 직접 디코딩한다 — 시스템에 별도 `ffmpeg` CLI가 없어도
동작을 보장하기 위함(audioread의 ffmpeg 폴백은 PATH 상의 ffmpeg 바이너리를 요구하나,
PyAV는 정적으로 링크된 코덱을 자체 포함). 이렇게 얻은 raw PCM을 librosa 신호처리
함수(파일 I/O가 아닌 numpy 배열을 받는 함수들)에 직접 넘긴다.

**그레이스풀 디그레이드 원칙(TTS 실패 처리와 동일)**: 이 분석은 답변 제출의 필수
경로가 아니다 — 실패해도 턴 제출 자체는 막지 않는다(호출부 책임, 이 모듈은 실패를
`ProsodyAnalysisError`로 단일화해 알릴 뿐 재시도/폴백 정책은 갖지 않는다).
"""
import io
import logging
import math
import struct
import wave

import numpy as np

logger = logging.getLogger(__name__)

_TARGET_SR = 16000
# librosa.pyin 권장 범위(사람 목소리 대역) — 원 계획서가 구체적 Hz 범위를 명시하지
# 않아 librosa 공식 예제 관례를 그대로 따른다(구현 세부값, 비가역성 낮음).
_FMIN_HZ = 65.0  # 약 C2
_FMAX_HZ = 2093.0  # 약 C7


class ProsodyAnalysisError(Exception):
    """디코딩 실패, 무음 오디오 등 프로소디 분석 중 발생한 모든 예외를 단일 계약으로
    승격한다(stt_engine.SttTranscriptionError와 동일 원칙). 호출부는 이 예외를
    턴 제출 실패로 취급하지 않고 그레이스풀 디그레이드해야 한다.
    """


def _decode_to_mono_pcm(audio_bytes: bytes, target_sr: int = _TARGET_SR) -> np.ndarray:
    """PyAV로 임의 컨테이너/코덱의 오디오 바이트를 모노 16kHz float32 PCM으로 디코딩한다."""
    import av  # faster-whisper의 기존 의존성 재사용(신규 의존성 아님)

    try:
        container = av.open(io.BytesIO(audio_bytes))
    except Exception as exc:  # noqa: BLE001 — PyAV의 다양한 하위 예외를 단일 계약으로 승격
        raise ProsodyAnalysisError("오디오 컨테이너를 열 수 없습니다.") from exc

    try:
        resampler = av.AudioResampler(format="s16", layout="mono", rate=target_sr)
        chunks: list[np.ndarray] = []
        for frame in container.decode(audio=0):
            frame.pts = None  # 일부 PyAV 버전에서 리샘플러가 pts 불연속에 민감(실측 대응)
            for rframe in resampler.resample(frame):
                chunks.append(rframe.to_ndarray())
    except Exception as exc:  # noqa: BLE001
        raise ProsodyAnalysisError("오디오 디코딩에 실패했습니다.") from exc
    finally:
        container.close()

    if not chunks:
        raise ProsodyAnalysisError("디코딩된 오디오 프레임이 없습니다(무음/빈 스트림).")

    pcm_int16 = np.concatenate(chunks, axis=1).flatten()
    return pcm_int16.astype(np.float32) / 32768.0


def analyze_prosody(audio_bytes: bytes) -> dict:
    """음성 바이트에서 원시 운율 지표를 추출한다. 반환값은 전부 원시 수치이며,
    "자신감"/"긴장도" 같은 해석 라벨은 이 함수가 만들지 않는다(모듈 docstring 참고).

    반환 스키마: {
      "duration_sec": float,
      "pitch_mean_hz": float | None,   # 유성음 구간의 평균 기본주파수(높낮이)
      "pitch_std_hz": float | None,    # 유성음 구간의 기본주파수 표준편차(떨림 근사)
      "voiced_ratio": float,           # 전체 프레임 중 유성음(발화) 비율
    }
    `pitch_*`는 유성음 구간이 전혀 없으면(예: 매우 짧거나 잡음뿐인 입력) None이다.
    """
    import librosa  # 지연 임포트 — numba JIT 컴파일 비용이 있어 모듈 최초 사용 시점에만 지불

    pcm = _decode_to_mono_pcm(audio_bytes)
    duration_sec = float(len(pcm)) / _TARGET_SR
    if duration_sec <= 0:
        raise ProsodyAnalysisError("오디오 길이가 0입니다.")

    try:
        f0, _voiced_flag, _voiced_probs = librosa.pyin(
            pcm, fmin=_FMIN_HZ, fmax=_FMAX_HZ, sr=_TARGET_SR
        )
    except Exception as exc:  # noqa: BLE001 — librosa 내부 신호처리 예외를 단일 계약으로 승격
        raise ProsodyAnalysisError("피치 추출에 실패했습니다.") from exc

    voiced = f0[~np.isnan(f0)]
    voiced_ratio = float(len(voiced)) / float(len(f0)) if len(f0) else 0.0

    return {
        "duration_sec": round(duration_sec, 3),
        "pitch_mean_hz": round(float(np.mean(voiced)), 2) if len(voiced) else None,
        "pitch_std_hz": round(float(np.std(voiced)), 2) if len(voiced) else None,
        "voiced_ratio": round(voiced_ratio, 4),
    }


def _generate_warmup_wav_bytes() -> bytes:
    """실측 결함 대응(2026-09-22, unit-24-test.md TC 참고): `librosa.pyin`은 내부적으로
    numba JIT 컴파일에 의존해 완전 콜드 스타트 첫 호출이 최대 약 32초까지 걸림을
    실측했다(디스크 캐시가 있으면 약 5초, 이후 호출은 1초 미만). faster-whisper의
    모델 로딩(수 초)·Piper의 서브프로세스 기동(수 초)과 같은 "최초 1회만 느림" 계열
    이슈이나 그 규모가 훨씬 커, 실사용자의 첫 음성 답변이 이 비용을 그대로 떠안으면
    프런트/리버스프록시 타임아웃 위험이 있다 — 서버 기동 시 이 함수로 생성한 순수
    사인파(외부 TTS 의존 없이 stdlib `wave`만 사용)로 미리 한 번 호출해 JIT을
    예열해둔다(`app/main.py` 참고).
    """
    buf = io.BytesIO()
    sr = 16000
    n_samples = sr // 2  # 0.5초
    samples = [int(3000 * math.sin(2 * math.pi * 220 * i / sr)) for i in range(n_samples)]
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return buf.getvalue()


def warmup() -> None:
    """서버 기동 시 호출용(동기 함수 — 호출부가 threadpool/백그라운드 태스크로
    감싼다). 실패해도 예외를 삼킨다 — 예열 실패가 서버 기동 자체를 막으면 안 된다
    (그레이스풀 디그레이드, 이 경우 첫 실사용 요청이 콜드 비용을 떠안을 뿐).
    """
    try:
        analyze_prosody(_generate_warmup_wav_bytes())
        logger.info("prosody_engine 예열 완료(numba JIT 컴파일)")
    except Exception:  # noqa: BLE001 — 예열은 best-effort, 실패해도 서버 기동을 막지 않음
        logger.warning("prosody_engine 예열 실패(치명적이지 않음, 첫 실사용 요청이 콜드 비용을 부담)", exc_info=True)
