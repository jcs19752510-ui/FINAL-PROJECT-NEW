# 테스트 결과서 (Test Result Report) — unit-35

## 1. 개요
- 테스트 대상: 화이트보드 AI 비전 분석(REQ-021) — `backend/app/services/whiteboard_vision.py`
  중 `render_strokes_to_png()`(실행 검증) + `analyze_diagram_with_vision()`(mock 검증, 실네트워크는 여전히 불가)
- 테스트 유형: 단위(함수 수준, API 미배선이라 통합/E2E 대상 없음)
- 적용 Tier: Low(운영 API에 연결되지 않은 격리 모듈, 원본 데이터/스키마 변경 없음)
- 적용 속도 트랙: L1(경량판) — unit-32(벤더 어댑터)와 동일한 성격의 "코드
  준비 + 가능한 범위까지 실검증" 유닛
- 테스트 목적: `render_strokes_to_png()`의 실제 동작(정상/경계/예외 입력)을
  실행으로 검증하고, `analyze_diagram_with_vision()`의 파싱/에러 처리 로직을
  mock으로 검증(실제 벤더 통신은 API 키 부재로 범위 밖)
- 관련 산출물: `docs/harness/units/unit-35-note.md`, `docs/harness/decisions.md`
  DEC-050, `docs/harness/traceability.md` REQ-021
- 테스트 수행자(에이전트): 본 세션(06 역할)
- 테스트 일시: 2026-09-23

## 2. 테스트 범위 및 제외 범위
- 범위(In-Scope): `render_strokes_to_png()` 실행 검증(정상/단일점/빈 점/결손
  필드/빈 스트로크목록/스키마 통합/경계값), `analyze_diagram_with_vision()`의
  성공/스키마오류/네트워크오류 3분기를 mock으로 검증
- 제외 범위 및 사유: (1) `analyze_diagram_with_vision()`의 실제 OpenAI 서버
  통신 — API 키가 없어 원천적으로 불가능(unit-32와 동일 제약, 사용자 승인
  범위 그대로). (2) API 엔드포인트 배선/통합 테스트 — 이번 유닛이 의도적으로
  어떤 라우터에도 배선하지 않기로 결정했으므로(unit-35-note.md §3) 대상 자체가
  없음. (3) 프론트 `WhiteboardCanvas.tsx`와의 좌표계(1200×800) 실제 일치 여부 —
  코드 대조를 하지 않았음(unit-35-note.md §5 후속 확인 항목)

## 3. 테스트 환경
- Windows, Python 3.13(`backend/.venv`, 기존 프로젝트 가상환경 — 이번 유닛이
  신규 venv를 만들지 않음)
- 테스트 데이터: 테스트 스크립트 내 인라인으로 생성한 스트로크 좌표(고정값),
  실제 DB/서버 프로세스 불필요(순수 함수 테스트)
- 전제 조건: `backend/.venv`에 Pillow 설치돼 있음(12.3.0, 이번 유닛이
  `requirements.txt` 누락을 발견·수정 — §6 DEF-001)

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-001 | 다중점 스트로크 렌더링(정상 경로) | 없음 | 3개 좌표점 스트로크 1개로 `render_strokes_to_png()` 호출 | PNG(1200×800) 유효 이미지 반환 | `Image.open()`으로 재파싱 성공, format=PNG, size=(1200,800) | PASS | |
| TC-002 | 단일점 스트로크(원으로 렌더링) | 없음 | 점 1개짜리 스트로크 호출 | 예외 없이 원(circle) 렌더링, 유효 PNG | size=(1200,800), 예외 없음 | PASS | 코드 내 명시적 분기(`len(points)==1`) 확인 |
| TC-003 | 빈 points 배열 명시적 거부 | 없음 | `points=[]`인 스트로크 호출 | `WhiteboardRenderError` 발생(조용히 무시하지 않음) | `WhiteboardRenderError` 발생, 메시지 "빈 stroke(points 없음)는 렌더링할 수 없습니다." | PASS | 코드 주석이 명시한 "PIL이 빈 stroke를 조용히 무시하는 것을 방지"하는 방어 로직 실측 확인 |
| TC-004 | 결손 필드(width 누락) 방어 | 없음 | `width` 키 없는 stroke dict로 호출 | `KeyError`가 그대로 새지 않고 `WhiteboardRenderError`로 변환 | `WhiteboardRenderError` 발생 | PASS | `except (KeyError, TypeError, ValueError)` 캐치 경로 실측 확인 |
| TC-005 | 빈 스트로크 목록(빈 캔버스) | 없음 | `strokes=[]`로 호출 | 예외 없이 흰 배경 PNG(1200×800) 반환 | size=(1200,800), 예외 없음 | PASS | 화이트보드를 한 번도 안 그린 채 분석 시도하는 경계 상황 대응 확인 |
| TC-006 | 스키마 통합(`WhiteboardSaveRequest.model_dump()` → 렌더 함수 직결) | 없음 | `schemas/whiteboard.py`의 `WhiteboardStroke`로 객체 생성 후 `model_dump()`한 결과를 그대로 `render_strokes_to_png()`에 전달 | 별도 변환 없이 정상 렌더링 | size=(1200,800), 예외 없음 | PASS | 실제 API 계약 타입과 렌더 함수 입력 계약이 실측으로 일치함을 확인(unit-17 스키마 재사용) |
| TC-007 | 경계값(`width=64`, 스키마 상한) | 없음 | width=64(schemas/whiteboard.py `le=64` 상한값)로 호출 | 크래시 없이 렌더링 | 예외 없음, PNG 바이트 반환 | PASS | |
| TC-008 | `analyze_diagram_with_vision()` 성공 경로(mock) | `urllib.request.urlopen`을 mock으로 대체 | 정상 GPT-4V 응답 형태를 mock에 주입 후 호출 | 응답 텍스트를 정확히 추출·trim | `content` 필드 정확히 파싱, 앞뒤 공백 제거 확인 | PASS | 실제 네트워크는 타지 않음(mock) — 파싱 로직만 검증 |
| TC-009 | `analyze_diagram_with_vision()` 응답 스키마 불일치(mock) | mock 응답에 `choices` 키 없음 | 위 상태로 호출 | `KeyError`가 그대로 새지 않고 `VisionAnalysisError`로 변환 | `VisionAnalysisError` 발생, 메시지 "GPT-4V 응답 스키마가 예상과 다릅니다(미검증 어댑터)." | PASS | |
| TC-010 | `analyze_diagram_with_vision()` 네트워크 실패(mock) | `urlopen`이 `URLError` 발생하도록 mock | 위 상태로 호출 | `URLError`가 그대로 새지 않고 `VisionAnalysisError`로 변환 | `VisionAnalysisError` 발생 | PASS | |

- 실행 방법: `backend/.venv/Scripts/python.exe`로 `.harness-tmp/unit35_test.py`
  직접 실행(임시 스크립트, §7에서 정리). 10개 케이스 전부 실제 `import`·실제
  함수 호출로 재현(문법 검토만이 아님).
- 게이트 1·2(문법/린트): `py_compile app/services/whiteboard_vision.py` 통과,
  `ruff check app/services/whiteboard_vision.py` — "All checks passed!"

## 5. 커버리지
- `render_strokes_to_png()`: 정상 경로(다중점/단일점/빈목록) + 예외 경로(빈
  points, 결손 필드) + 경계값(width 상한) 전부 실행 커버. 커버되지 않은 것:
  `MAX_STROKES`(2000)/`MAX_POINTS_PER_STROKE`(5000) 초과 시 렌더 함수 자체의
  동작 — 이 상한은 `schemas/whiteboard.py`의 API 경계(Pydantic validator)에서
  이미 막히므로 렌더 함수까지 도달하지 않는 입력이라 이번 유닛 범위에서 제외.
- `analyze_diagram_with_vision()`: 성공/스키마오류/네트워크오류 3개 분기 전부
  mock으로 커버. 커버되지 않은 것: 실제 OpenAI 서버와의 인증·타임아웃·요금제
  한도 등 — API 키 없이는 원천적으로 커버 불가(§2 제외 범위 참고).

## 6. 결함(Defect) 목록
| ID | 설명 | 재현 절차 | 심각도 | 상태 | 조치 내용 |
|----|------|-----------|--------|------|-----------|
| DEF-001 | `backend/requirements.txt`에 `Pillow` 선언 누락 — `whiteboard_vision.py`가 import하지만 신선한 환경에서는 `pip install -r requirements.txt`만으로 `ImportError` 발생 | 신규 venv에서 `requirements.txt`만 설치 후 `import app.services.whiteboard_vision` 시도 | Low(개발 venv에는 이미 설치돼 있어 로컬 개발에는 영향 없었으나, CI/신규 환경 재현성 결함) | Fixed | `requirements.txt`에 `Pillow>=11.0,<13.0` 추가(unit-35 주석 포함) |

- 위 1건 외 결함 없음 — TC-001~010 전부 PASS로 실측 확인(위 표 근거).

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 생성한 임시 아티팩트: `.harness-tmp/unit35_test.py`(테스트 스크립트)
- 전부 `.harness-tmp/` 하위에서만 생성했는가: [x] 예
- 정리(삭제) 완료 여부: 완료(아래 명령 직후 실행)
- 정리 후 `git status` 실행 결과: 본 결과서 작성 직후 별도로 실행해 확인함(9절
  PASS 판정 전제조건, 아래 커맨드 결과 그대로):
  - `.harness-tmp/unit35_test.py` 삭제 확인, `.harness-tmp/`에 잔여물 없음
  - `git status`상 변경분은 원본 코드(requirements.txt, 신규 note/test 문서,
    decisions.md/traceability.md)뿐이며 `.harness-tmp/` 관련 항목 없음
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: [x] 없음
- `backend/.venv`는 이번 유닛이 생성하지 않은 프로젝트 기존 가상환경이므로
  정리 대상이 아님(규칙 K는 "이번 테스트에서 생성한" 아티팩트만 대상으로 함).

## 8. 리스크 및 잔존 이슈
- REQ-021 전체 목표(다이어그램을 AI가 보고 타당성 평가)는 아직 미달성 — 렌더링
  부분만 실질적으로 완료. API 키 확보 전까지 "완료"로 볼 수 없음(unit-35-note.md
  §3).
- `_CANVAS_SIZE`(1200×800)가 실제 프론트 캔버스 크기와 일치하는지 미검증
  (unit-35-note.md §5-1).
- 이 코드는 어떤 API 엔드포인트에도 배선되지 않아 현재 라이브 영향은 없음(회귀
  위험 없음).

## 9. 결론 및 판정
- [x] PASS — 다음 단계 진행 가능(7절 Teardown 확인 완료). 단, REQ-021 자체는
  "부분착수"이며 08(전체시스템테스트) 착수 전 API 키·배선 여부에 대한 사용자
  결정이 별도로 필요함(unit-35-note.md §5-3).

## 10. 내부 검증
- L1 경량판 — 1차 검증(작성자 관점 자가 재검토)에서 결함 0건(테스트 실행
  결과와 본 문서 기술 내용 대조, TC-001~010 전부 실제 실행 로그와 일치 확인).
  규칙 B Tier=Low 예외에 따라 2차 생략. 검증 로그 파일: 별도 미작성(L1 경량판,
  ORCHESTRATOR.md 1장 "구현 속도 트랙" 참고).
