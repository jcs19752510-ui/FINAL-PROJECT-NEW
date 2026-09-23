# unit-31 구현 노트 — DeepFace 표정 감정분석 (정지 이미지, 부분 구현)

- 작성 에이전트: 본 세션, 작성일: 2026-09-22
- 원 계획서 §5.3.1(REQ-018), traceability Out-of-Scope 사유(GPU 제약·EU AI
  Act·생체인식정보 리스크) — 2026-09-22 사용자가 리스크 인지 후 기술검증 승인.

## ⚠️ 법적/윤리적 경고 (모듈 docstring과 동일, 반복 강조)

이 기능은 국내 개인정보 보호법상 민감정보(생체인식정보)를 다루고, EU AI Act가
직장 내 감정인식을 금지 관행으로 논의 중인 영역이다. **배포 전 반드시 법무
검토가 선행되어야 한다.** 이 유닛은 "기술적으로 동작하는가"만 검증했다.

## 1. 정직한 스코프

원안은 "초당 1~2 프레임 추출 + 시계열 타임라인"(실시간 영상 스트림 전제)을
요구했으나, 그 전제(WebRTC 미디어 서버)가 없다(unit-28은 시그널링만 구현).
이 유닛은 **정지 이미지 1장 → 감정 확률 분포**만 구현·검증했다 — 연속 프레임
파이프라인, 시계열 저장, 타임라인 시각화는 전혀 구현하지 않았다.

## 2. 구현 범위

- `backend/app/services/emotion_engine.py`(신규): DeepFace 기반, 7종 감정
  확률 분포 반환. GPU는 LLM(llama-server)이 이미 점유 중이라 `CUDA_VISIBLE_
  DEVICES=-1`로 **강제 CPU 실행**(모듈 최상단, import 순서 중요).
- `backend/requirements.txt`: 미갱신 — `deepface`/`tf-keras`는 이번 검증
  과정에서 설치했으나 requirements.txt에 추가할지는 unit-29(코드샌드박스)와
  같은 이유로 "실제 서비스 연결 여부가 아직 결정 안 됨" 상태라 보류(인수인계
  4절 참고).

## 3. 실측으로 발견한 결함 2건 (전부 이 환경 특유 — 코드 결함 아님)

| 문제 | 원인 | 대응 |
|---|---|---|
| `UnicodeEncodeError`로 프로세스 크래시 | DeepFace 로거가 이모지(⚠️)를 `print()`하는데 Windows 콘솔 cp949 코드페이지가 인코딩 못 함 | `PYTHONIOENCODING=utf-8` 환경변수로 우회(테스트 실행 시에만 필요 — 실제 API 서버는 uvicorn 로깅 경로가 달라 별도 확인 필요, 4절 인수인계) |
| 얼굴 검출 항상 실패(`ValueError`) | 이 환경의 `opencv-python`(5.0.0.93) 패키지가 `cv2/data/haarcascade_*.xml`을 포함하지 않음(패키징 이슈로 추정) | DeepFace 기본 검출기("opencv") 대신 이미 설치된 MTCNN으로 전환(`detector_backend="mtcnn"`) — 정확도도 더 높아 실질적으로 더 나은 선택 |

**중요**: 1번째 결함(cp949 크래시)은 unit-24(prosody, 콘솔 출력 mojibake)·
unit-27(curl 한글 테스트 422)이 각각 겪은 것과 **같은 근본 원인 계열**(Windows
콘솔/프로세스 인코딩)이 이번엔 "크래시"라는 가장 심각한 형태로 나타났다 —
`content_text` DB 손상 결함 조사 시 반드시 이 패턴을 최우선 용의선상에 둘 것.

## 4. 실측 결과 요약(테스트 보고서 상세는 unit-31-test.md)

DeepFace 공식 테스트 이미지(GitHub `serengil/deepface` 저장소, 실제 사람 얼굴
사진)로 감정분석 성공(dominant_emotion="happy", confidence=0.97, 13.48초).
얼굴 없는 이미지·손상된 이미지 입력 시 정상적으로 `EmotionAnalysisError` 발생
확인.

## 5. 범위 밖 (인수인계)

- GPU 미사용을 `nvidia-smi`로 직접 실측 확인하지 못함(플랫폼 안전 분류기
  일시 장애로 재시도 불가) — `CUDA_VISIBLE_DEVICES=-1` 설정 자체는 TensorFlow
  표준 메커니즘이라 이론적으로는 신뢰 가능하나, 이 세션에서 "실측 확인"까지는
  못함. 후속 세션에서 재확인 권장.
- 프로덕션 API 엔드포인트에 연결하지 않았다 — 법무 검토 없이 실제 서비스
  경로에 노출하지 않는다는 원칙(unit-29 코드샌드박스와 동일 판단).
- `requirements.txt`에 `deepface`/`tf-keras`를 추가하지 않았다(위 2절) — 실제
  연결 결정 시점에 함께 추가할 것.
- uvicorn/API 서버 프로세스 자체가 cp949 크래시에 취약한지는 별도 확인 필요
  (이번 크래시는 순수 Python 스크립트 직접 실행 시 재현됐고, FastAPI 앱은
  로깅 설정이 다를 수 있음).
