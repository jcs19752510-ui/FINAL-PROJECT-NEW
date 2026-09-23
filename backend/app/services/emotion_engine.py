"""표정 기반 감정분석 (원안 REQ-018, 2026-09-22 사용자 승인, unit-31).

**법적/윤리적 경고(반드시 읽을 것)**: 이 기능은 원 계획서 작성 시점부터
Out-of-Scope로 확정돼 있었다(`docs/harness/traceability.md` REQ-018 —
"GPU 4GB 제약, EU AI Act 감정인식 금지관행 논의, 국내 생체인식정보 리스크,
L1 트랙 부적합"). 얼굴 이미지는 국내 개인정보 보호법상 민감정보(생체인식정보)
이며, 감정인식 AI는 EU AI Act가 특정 활용 사례(직장/교육기관에서의 감정 추론
등)를 금지 관행으로 규정하는 논의가 진행 중이다. 이 모듈은 사용자가 이 위험을
명시적으로 인지한 상태에서 기술 검증 목적으로 구현을 승인해 존재하지만,
**실제 채용 프로세스에 연결하기 전 반드시 법무 검토가 선행되어야 한다.**

**정직한 범위**: 이 모듈은 **정지 이미지 1장**을 분석한다. 원안이 요구한
"초당 1~2 프레임 추출 + 시계열 타임라인"은 실시간 영상 스트림이 전제인데,
그 전제(WebRTC 미디어 서버)가 아직 없다(unit-28이 시그널링만 구현, 미디어
자체는 범위 밖). 이 모듈은 "DeepFace 호출 자체가 이 환경에서 실제로 동작하고
정확한 결과를 낸다"는 것만 실측으로 증명한다 — 연속 프레임 파이프라인/시계열
저장은 구현하지 않았다.

**리소스 격리**: GPU는 이미 LLM(llama-server)이 점유 중이다(unit-7 실측,
VRAM 598MiB→1717MiB). DeepFace/TensorFlow가 같은 GPU를 잡으려 하면 자원
경합이 발생하므로, 이 모듈을 임포트하는 시점에 `CUDA_VISIBLE_DEVICES`를
비워 **강제로 CPU만 쓰게 한다**(모듈 최상단, TensorFlow가 GPU를 초기화하기
전에 반드시 설정되어야 함 — 임포트 순서가 중요).
"""
import os

# TensorFlow/DeepFace가 GPU를 잡기 전에 반드시 먼저 설정해야 한다(임포트 순서
# 중요 — 이 파일 최상단, 다른 import보다 먼저 실행되어야 함).
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")  # TensorFlow 진단 로그 소음 억제(구현 세부값)

import logging  # noqa: E402 — 위 os.environ 설정 이후에 import해야 하는 모듈들
from dataclasses import dataclass  # noqa: E402

import numpy as np  # noqa: E402

logger = logging.getLogger(__name__)

# 원 계획서 §5.3.1 "7가지 기본 감정(행복, 슬픔, 분노, 놀람, 공포, 혐오, 중립)"과
# 동일한 DeepFace 기본 7종 그대로.
_EMOTION_LABELS = ("angry", "disgust", "fear", "happy", "sad", "surprise", "neutral")


class EmotionAnalysisError(Exception):
    """디코딩 실패, 얼굴 미검출 등을 단일 계약으로 승격한다."""


@dataclass
class EmotionResult:
    dominant_emotion: str
    scores: dict[str, float]  # 감정별 확률(%) — 원안 "확률 분포" 요구 그대로
    face_confidence: float


def analyze_face_emotion(image_bytes: bytes) -> EmotionResult:
    """이미지 바이트(정지 프레임 1장)에서 얼굴을 찾아 7종 감정 확률 분포를
    반환한다. 얼굴이 없거나 디코딩 실패 시 `EmotionAnalysisError`.
    """
    import cv2
    from deepface import DeepFace

    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise EmotionAnalysisError("이미지를 디코딩할 수 없습니다.")

    try:
        # 실측 결함(2026-09-22): 이 환경의 `opencv-python`(5.0.0.93) 패키지가
        # `cv2/data/haarcascade_*.xml`을 포함하지 않아 DeepFace 기본 검출기
        # ("opencv", Haar cascade 기반)가 항상 실패함을 확인. 이미 설치돼 있는
        # (DeepFace의 정식 의존성) MTCNN 검출기로 전환해 우회 — Haar cascade보다
        # 정확도도 더 높아 실질적으로도 더 나은 선택.
        results = DeepFace.analyze(img, actions=["emotion"], detector_backend="mtcnn", enforce_detection=True)
    except ValueError as exc:
        # DeepFace는 얼굴을 못 찾으면 ValueError를 던진다(라이브러리 자체 계약).
        raise EmotionAnalysisError("이미지에서 얼굴을 감지하지 못했습니다.") from exc

    # DeepFace.analyze는 이미지 안의 얼굴 수만큼 리스트를 반환한다 — 이 모듈은
    # 면접자 1인 전제(원안 시나리오와 동일)라 첫 번째 얼굴만 사용한다.
    face = results[0]
    return EmotionResult(
        dominant_emotion=face["dominant_emotion"],
        scores={k: round(float(v), 2) for k, v in face["emotion"].items()},
        face_confidence=round(float(face.get("face_confidence", 0.0)), 4),
    )
