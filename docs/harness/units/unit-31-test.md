# 테스트 결과서 (Test Result Report) — unit-31

## 1. 개요
- 테스트 대상: DeepFace 표정 감정분석(`app/services/emotion_engine.py`) —
  정지 이미지 1장 분석만(실시간 영상 파이프라인 범위 밖)
- 테스트 유형: 단위
- 적용 Tier: Low(신규 격리 모듈, 어떤 API 엔드포인트에도 연결하지 않음)
- 적용 속도 트랙: L1(경량판), 표준 수준으로 채움
- 테스트 목적: 실제 얼굴 이미지로 감정 확률 분포가 정확히 반환되는지, 얼굴
  없음/손상 이미지에서 정상적으로 거부되는지, 이 환경 특유의 의존성 문제를
  실측으로 확인·해결
- 관련 산출물: `unit-31-note.md`, 원 계획서 §5.3.1
- 테스트 수행자: 본 세션
- 테스트 일시: 2026-09-22

## 2. 테스트 범위 및 제외 범위
- 범위: 실제 얼굴 이미지 분석, 얼굴없음/손상이미지 에러 처리, 의존성 문제
  해결(cp949 크래시, opencv haarcascade 누락)
- 제외 범위 및 사유: (1) GPU 미사용 실측(`nvidia-smi`) — 플랫폼 안전 분류기
  일시 장애로 재시도 못함(unit-31-note.md §5). (2) 실시간 영상 스트림/시계열
  — 그 전제(미디어 서버)가 없음(unit-28 범위 밖). (3) API 엔드포인트 통합 —
  법무 검토 전 연결하지 않기로 결정.

## 3. 테스트 환경
- Windows, Python 3.13(backend/.venv), 신규 설치: deepface 0.0.101, tensorflow
  2.21.0, tf-keras 2.21.0, mtcnn 1.0.0(이미 deepface 의존성으로 설치됨)
- 테스트 데이터: DeepFace 공식 GitHub 저장소(`serengil/deepface`)의 테스트용
  얼굴 사진(`tests/unit/dataset/img1.jpg`, 실제 사람 사진, 2.28MB) — 라이브러리
  자체의 공식 테스트 자산이라 신뢰 가능한 출처로 판단해 사용. 얼굴 없는
  이미지는 PNG 바이트를 직접 구성해 생성(외부 소스 없음).

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail |
|----|----------|-----------|-----------|-----------|-----------|
| TC-001 | 문법/린트 | `py_compile`+`ruff check` | 오류 0건 | clean | PASS |
| TC-002 | cp949 크래시 재현·해결 | `PYTHONIOENCODING` 미설정 상태로 최초 실행 | (최초) `UnicodeEncodeError`로 프로세스 크래시 → 환경변수 설정 후 재실행 | 정확히 재현 확인 → `PYTHONIOENCODING=utf-8`로 해결 확인 | PASS(우회 확인) |
| TC-003 | opencv haarcascade 누락 재현·해결 | 기본 detector_backend("opencv")로 최초 실행 | (최초) `ValueError`(cascade 파일 없음) → mtcnn으로 전환 후 재실행 | 정확히 재현 확인 → 전환 후 정상 동작 확인 | PASS(우회 확인) |
| TC-004 | 실제 얼굴 이미지 분석 | DeepFace 공식 테스트 사진으로 `analyze_face_emotion()` 호출 | 7종 감정 확률 분포 + dominant_emotion 반환, 합리적 신뢰도 | `dominant_emotion="happy"`(100%), `face_confidence=0.97`, 13.48초 | PASS |
| TC-005 | 얼굴 없는 이미지 | 순수 단색 PNG(직접 생성) 입력 | `EmotionAnalysisError` 발생 | 정확히 일치("얼굴을 감지하지 못했습니다") | PASS |
| TC-006 | 손상된/비이미지 바이트 | `b'not a real image at all'` 입력 | `EmotionAnalysisError` 발생 | 정확히 일치("디코딩할 수 없습니다") | PASS |

## 5. 커버리지
- L1이나 표준 수준. 정상/얼굴없음/손상 3개 핵심 분기 전량 실제 실행 커버.
- 커버되지 않은 부분(2절 사유): GPU 미사용 실측, 실시간 파이프라인.

## 6. 결함(Defect) 목록
| ID | 설명 | 심각도 | 상태 | 조치 |
|----|------|--------|------|------|
| DEF-001 | DeepFace 로거의 이모지 출력이 Windows cp949 콘솔에서 `UnicodeEncodeError`로 프로세스 크래시 | Medium(이 환경 특유, 코드 결함 아님) | Fixed(우회) | `PYTHONIOENCODING=utf-8` — **`content_text` DB 손상 결함 조사 시 최우선 용의선상에 둘 것**(unit-31-note.md §3) |
| DEF-002 | `opencv-python` 패키지에 haarcascade 데이터 파일 누락, 기본 얼굴검출기 항상 실패 | Medium(패키징 이슈로 추정) | Fixed | `detector_backend="mtcnn"`으로 전환(더 정확한 검출기라 실질 개선) |

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 생성한 임시 아티팩트: `.harness-tmp/test_face.jpg`(외부 다운로드),
  `no_face.png`(직접 생성), `deepface_out.log`/`deepface_out2.log`/
  `deepface_errtest.log`(테스트 출력) — 전량 삭제 확인
- 신규 pip 패키지 설치: `deepface`, `tensorflow`, `tf-keras` 등 — venv 내부에만
  설치됨(호스트 시스템 변경 없음), `requirements.txt`에는 미반영(unit-31-note.md
  §2, 실제 연결 결정 시점까지 보류)
- 전부 `.harness-tmp/` 하위에서만 생성: [x] 예
- 정리 완료 여부: 완료
- 정리 후 git status: 사용자 지시("Git 작업 금지")로 미실행
- 강제 중단 여부: 없음(단, `nvidia-smi` 실행 1건이 플랫폼 안전 분류기 일시
  장애로 차단됨 — 강제 중단과는 다른 사유, 8절 참고)

## 8. 리스크 및 잔존 이슈
- **법무 검토 미완료 — 실제 서비스 연결 절대 금지**(unit-31-note.md 최상단
  경고 반복).
- GPU 미사용 여부 실측 미확인(5절) — 후속 세션에서 `nvidia-smi` 재확인 필요.
- cp949 크래시(DEF-001)는 이 세션의 테스트 실행 방식(직접 python 스크립트)에서
  재현된 것 — 실제 uvicorn API 서버가 같은 방식으로 크래시하는지는 별도 확인
  필요(uvicorn은 로깅 핸들러 설정이 다를 수 있음).

## 9. 결론 및 판정
- [x] CONDITIONAL PASS — 조건: 기술적으로는 정상 동작 확인, 그러나 법무
  검토 완료 전까지 프로덕션 연결 금지.

## 10. 내부 검증
- L1 경량판 — 검증 생략. DEF-001/002는 "재현→해결→재검증" 사이클을 실제로
  거침.
