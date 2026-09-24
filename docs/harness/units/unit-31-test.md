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

---

## 11. 후속 — API 배선(개인 PC 임시 테스트 전용) + uvicorn cp949 크래시 재확인 (2026-09-24, DEC-070)

### 11.1 경위
사용자가 "DeepFace 서비스연결 → 법무 자문 필요없음(개인 PC에서만 임시 테스트)"라고 범위를 명시적으로 좁혀 연결을 승인. §9의 "법무 검토 완료 전까지 프로덕션 연결 금지" 조건은 문자 그대로 유지 — 이번 배선은 실제 서비스(면접 평가/리포트 파이프라인)에는 연결하지 않은 완전히 독립된 진단용 엔드포인트다.

### 11.2 §8이 미해결로 남겼던 질문의 해소 — "uvicorn도 cp949로 크래시하는가?"
§8이 "cp949 크래시(DEF-001)는 직접 python 스크립트에서 재현된 것 — uvicorn이 같은 방식으로 크래시하는지 별도 확인 필요"라고 명시적으로 남겨뒀던 질문을 이번에 실측으로 확인했다 — **그렇다, uvicorn도 동일하게 크래시했다.** `POST /interviews/{id}/webcam-emotion`을 실 HTTP로 호출했더니 500 Internal Server Error가 발생했고, 서버 로그에서 `UnicodeEncodeError: 'cp949' codec can't encode character '\u26a0'`(deepface 라이브러리 자체의 `logger.warn()`이 ⚠️ 이모지가 포함된 배포 경고 메시지를 출력하려다 발생)를 직접 확인했다.

### 11.3 원인 및 수정
uvicorn을 기동하는 `.claude/launch.json`의 backend 실행 커맨드가 `PYTHONIOENCODING`을 설정하지 않아, Windows 기본 로케일(cp949)로 stdout이 열려 있었다 — deepface 외에도 이모지/비ASCII 문자를 print하는 어떤 라이브러리든 같은 방식으로 서버 전체를 크래시시킬 수 있는 구조적 위험이었다. `.claude/launch.json`의 backend 커맨드에 `set PYTHONIOENCODING=utf-8 &&`를 추가해 근본 해결.

### 11.4 추가로 발견한 결함 — requirements.txt/venv 자체가 깨져 있었음
`backend/.venv`에 `deepface`/`tensorflow`/`tf-keras`/`opencv-python`이 전혀 설치돼 있지 않았다(unit-31-note.md §2가 "이번 검증 전용으로 설치했고 requirements.txt는 의도적으로 갱신하지 않았다"고 기록한 그대로 — 이후 venv가 재생성되며 그 미선언 패키지들이 사라진 것으로 추정). `pip show`로 실측 확인 후 unit-31-test.md §3이 실측한 것과 동일한 버전(`deepface==0.0.101`, `tensorflow==2.21.0`, `tf-keras==2.21.0`, `opencv-python==5.0.0.93`)으로 재설치하고, 이번에는 실제로 연결하므로 `requirements.txt`에도 선언을 추가했다(신규 환경에서 재현 가능하도록 — unit-35의 Pillow 누락 결함과 같은 유형의 문제를 사전 방지).

### 11.5 구현
- `backend/app/services/emotion_engine.py`: `LOCAL_TEST_ONLY_DISCLAIMER` 상수 추가 — 모든 응답에 "개인 PC 임시 기술 테스트 전용, 실제 채용 프로세스 미연결, 법무 검토 필요" 고지를 동봉(whiteboard_vision.py의 저신뢰 disclaimer와 동일 패턴).
- `backend/app/schemas/emotion.py`(신규): `EmotionAnalysisOut`.
- `backend/app/api/v1/webcam_emotion.py`(신규): `POST /interviews/{id}/webcam-emotion` — 소유권 검사 → 이미지 파싱/크기제한(8MB) → `analyze_face_emotion()` 호출. 결과는 DB에 저장하지 않음(면접 평가 파이프라인과 완전 분리).
- `backend/app/main.py`: 라우터 등록.
- `.claude/launch.json`: `PYTHONIOENCODING=utf-8` 추가(§11.3).
- `backend/requirements.txt`: 4개 패키지 신규 선언(§11.4).

### 11.6 테스트 케이스(실 HTTP E2E)
| ID | 시나리오 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail |
|----|----------|-----------|-----------|-----------|-----------|
| TC-005 | 얼굴 없는 이미지(수정 전) | 단색 200x200 JPEG로 호출 | 422(수정 전에는 500이 실제로 발생함을 먼저 확인) | 수정 전: 500(§11.2). 수정 후 재실행: `422 {"detail":"이미지에서 얼굴을 감지하지 못했습니다."}` | Pass(수정 후) |
| TC-006 | 타인/존재하지 않는 interview_id | 존재하지 않는 UUID로 호출 | 404 | `404 {"detail":"면접 세션을 찾을 수 없습니다."}` | Pass |
| TC-007 | 실제 얼굴 이미지(unit-31과 동일 소스) | 사용자 승인 하에 DeepFace 공식 테스트 사진(`serengil/deepface` GitHub, `tests/unit/dataset/img1.jpg`, 2.28MB) 재다운로드 후 호출 | unit-31-test.md TC-004와 동일한 결과 재현 | `dominant_emotion="happy"`, `face_confidence=0.97`, 6.7초 — **unit-31 최초 검증(TC-004, confidence 0.97)과 정확히 일치** | Pass |

### 11.7 결함 목록
- **DEF-003(High, Fixed)** — uvicorn 프로세스의 stdout이 cp949로 열려 있어 deepface(및 잠재적으로 이모지를 출력하는 다른 라이브러리)가 크래시를 유발. `.claude/launch.json`에 `PYTHONIOENCODING=utf-8` 추가로 수정, TC-005 재실행으로 재검증.
- **DEF-004(Medium, Fixed)** — `backend/.venv`에 deepface 관련 4개 패키지가 실제로 설치돼 있지 않았음(§11.4). 재설치 + requirements.txt 선언 추가로 수정.

### 11.8 테스트 환경 정리(규칙 K)
- 이번 라운드가 만든 진단 계정 4건과 그 인터뷰는 검증 직후 전부 삭제.
- 다운로드한 테스트 얼굴 이미지는 세션 스크래치패드에만 존재(프로젝트 저장소에 커밋 안 됨).
- DeepFace 모델 가중치 캐시(`C:\Users\<user>\.deepface\weights`)는 재사용 가능한 로컬 캐시라 유지(Docker 이미지 캐시와 동일 원칙).
- 강제 중단 없음.

### 11.9 결론 및 판정(추가분)
- [x] **PASS** — API 배선 + 실 HTTP E2E(정상 얼굴 인식·얼굴 없음 거부·타인 접근 차단) 전부 완료. §8이 남겨뒀던 "uvicorn도 크래시하는가?" 질문도 실측으로 해소(그렇다 → 수정 완료).
- §9의 "법무 검토 완료 전까지 프로덕션 연결 금지" 조건은 **그대로 유지** — 이번 엔드포인트는 면접 평가/리포트 파이프라인 어디에도 연결되지 않았고, 모든 응답에 그 사실을 명시하는 disclaimer가 동봉된다.
- 프런트엔드 UI(실제 웹캠 프레임을 캡처해 이 엔드포인트를 호출하는 화면)는 이번 범위에 포함하지 않았다 — 이 세션의 Browser pane 자체가 마이크와 마찬가지로 카메라 장치 접근도 차단될 가능성이 높아(§ unit-36-test.md §12 마이크 제약과 동일 유형) 만들어도 이 세션이 스스로 검증할 수 없기 때문. 필요하면 사용자가 별도로 요청 시 진행.
