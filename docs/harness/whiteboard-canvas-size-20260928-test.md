# 테스트 결과서 (Test Result Report) — unit-35-note.md §5-1 후속: 화이트보드 `_CANVAS_SIZE` 프론트 실측 대조

## 1. 개요
- 테스트 대상: `backend/app/services/whiteboard_vision.py::_CANVAS_SIZE` 및
  `render_strokes_to_png()`가 실제 프론트 `WhiteboardCanvas.tsx` 좌표계와
  일치하는지
- 테스트 유형: 단위(Low 등급, 상수 1개 정정 — 렌더링은 분석 요청 시점에
  온더플라이로 수행되어 과거 저장 데이터에 영향 없음)
- 적용 Tier: Low
- 테스트 목적: (1) 실제 배선된 프론트 캔버스 크기를 코드로 직접 확인, (2)
  기존 상수(1200×800)와 불일치함을 픽셀 단위로 실증, (3) 정정 후(640×400)
  같은 좌표가 이미지 전체를 채우는지 재확인
- 관련 산출물: `docs/harness/decisions.md` DEC-081, `docs/harness/units/unit-35-note.md`
  §5-1, `docs/harness/units/unit-35-test.md` §8, `docs/harness/traceability.md` REQ-021
- 테스트 수행자(에이전트): 본 세션
- 테스트 일시: 2026-09-28

## 2. 테스트 범위 및 제외 범위
- 범위: `whiteboard_vision.py`의 렌더링 상수·함수(Pillow 기반, 외부 의존성
  없음)와 `frontend/app/interviews/[id]/components/WhiteboardCanvas.tsx` +
  `InterviewSidePanel.tsx`(실제 배선 지점)의 코드 대조
- 제외 범위 및 사유: SmolVLM 비전 모델 자체의 응답 품질 개선은 이번 범위 밖
  (unit-35가 이미 "실측상 매우 낮음"으로 기록했고 disclaimer로 완화 중이라는
  기존 결정을 뒤집는 것이 아니라, 그 낮은 품질에 "여백까지 더해 상황을
  악화시키는" 별도 결함만 정정). 프론트 코드(`WhiteboardCanvas.tsx`) 자체는
  변경하지 않음 — 백엔드 상수를 프론트 실제값에 맞추는 방향으로만 수정(프론트
  기본 props를 바꾸는 것보다 영향범위가 작음).

## 3. 테스트 환경
- Windows, Python 3.13(`backend/.venv`), Pillow — DB/서버 프로세스 기동 불필요
  (순수 함수 호출 검증)
- 테스트 데이터: 코너-투-코너 대각선 스트로크 2개(좌상단→우하단, 우상단→
  좌하단)를 실제 좌표(0~639, 0~399)로 구성해 `render_strokes_to_png()`에 직접
  전달
- 전제 조건: cp949 콘솔 표시 문제를 피하기 위해 `PYTHONIOENCODING=utf-8`로
  실행, 결과를 UTF-8 파일로 저장 후 `Read` 도구로 재확인

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-001 | 실제 배선 지점 확인 | `InterviewSidePanel.tsx` 소스 | `grep -n "WhiteboardCanvas" InterviewSidePanel.tsx` | width/height props 지정 여부 확인 | `<WhiteboardCanvas interviewId=... accessToken=... />` — width/height 미지정, 컴포넌트 기본값(640×400) 그대로 사용 확인 | PASS | 실제 사용처가 컴포넌트 정의(unit-17)의 `width=640, height=400`을 그대로 씀을 코드로 직접 확인 |
| TC-002 | 종횡비 불일치 확인 | 위 결과 + 기존 상수(1200×800) | 계산 | 8:5(1.6) vs 3:2(1.5) — 단순 스케일이 아니라 비율 자체가 다름 | 640/400=1.6, 1200/800=1.5, 서로 다름 확인 | PASS | 단순 축소·확대로 보정되지 않고 여백이 생기는 근거 |
| TC-003 | 수정 전 재현 — 실제로 여백이 발생했었는지 | `_CANVAS_SIZE=(1200,800)`(수정 전 값)로 동일 로직 재현 | 640×400 범위 대각선 렌더링 → 이미지 우하단 끝(1199,799) 픽셀 확인 | 흰색(빈 여백) | `(255,255,255)` 흰색 확인 — 여백 실증 | PASS | 회귀 증거: 수정 전 실제로 결함이 있었음을 실측으로 확인(추정이 아님) |
| TC-004 | 수정 후 상수 값 확인 | 수정된 `whiteboard_vision.py` | `from app.services.whiteboard_vision import _CANVAS_SIZE` | `(640, 400)` | `(640, 400)` 확인 | PASS | |
| TC-005 | 수정 후 렌더링 이미지 크기 확인 | 위 | `render_strokes_to_png(strokes)` → `PIL.Image.open()` | `img.size == (640, 400)` | 일치 확인 | PASS | |
| TC-006 | 수정 후 코너까지 실제로 채워지는지(여백 해소) | 위 | 같은 대각선 스트로크로 렌더링 후 (638,398) 픽셀 확인 | 흰색이 아님(검은 선 픽셀) | `(0, 0, 0)` 확인 — 더 이상 흰 여백이 아님 | PASS | 수정 전(TC-003)과 대조되는 직접 증거 |
| TC-007 | 린트 | 수정된 `whiteboard_vision.py` | `ruff check` | 오류 0건 | `All checks passed!` | PASS | |

## 5. 커버리지
- 커버리지 지표: 상수 변경 자체는 100% — 수정 전/후 양쪽 모두 실제 PNG
  렌더링으로 대조(TC-003 vs TC-006)
- 커버되지 않은 부분과 사유: 실제 브라우저에서 640×400 캔버스에 마우스로
  그린 스트로크가 서버로 정확히 그 좌표 그대로 전송되는지의 실HTTP/실브라우저
  E2E는 이번 범위에서 재현하지 않음(`getCanvasPoint()`가 `canvas.width`/
  `canvas.height`를 직접 참조하는 것을 코드로 확인했고, 이 값은 React가
  `width={640} height={400}` props로 그대로 캔버스 엘리먼트에 반영하므로
  좌표계 자체는 코드 읽기로 충분히 확정적 — 09단계에서 필요 시 브라우저
  재검증 가능)

## 6. 결함(Defect) 목록
- 결함 없음(신규) — 원래 결함(unit-35-note.md §5-1, "후속 확인 필요")을
  TC-001~007로 실측 확인 후 정정 완료. 결함 0건 근거는 위 표.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트: `scratchpad/canvas_size_test_result.txt`,
  `scratchpad/canvas_size_before_fix_result.txt`(세션 스크래치패드, 프로젝트
  저장소 밖) — 프로젝트 `.harness-tmp/`에는 아무것도 생성하지 않음(DB/서버/venv
  불필요, 순수 함수 호출 검증)
- 전부 `.harness-tmp/` 하위에서만 생성했는가: 해당 없음(저장소 내 임시
  아티팩트 자체를 생성하지 않음)
- 정리 완료 여부: 정리 대상 없음(저장소 내 생성물 없음)
- 정리 후 `git status`: `whiteboard_vision.py`, `decisions.md`,
  `traceability.md`, `unit-35-note.md`, `unit-35-test.md` 변경분만 존재,
  `.harness-tmp/` 관련 항목 없음
- 이번 테스트 도중 강제 중단 여부: 없음

## 8. 리스크 및 잔존 이슈
- 이 정정은 "프론트 기본 props(640×400)로 실제 배선돼 있다"는 현재 코드
  상태를 기준으로 한다 — 향후 누군가 `InterviewSidePanel.tsx`에서
  `WhiteboardCanvas`에 다른 width/height를 명시적으로 넘기도록 바꾸면 이
  상수도 함께 갱신해야 한다(두 파일 사이에 컴파일 타임 강제 연결이 없는
  암묵적 계약 — 코드 주석으로 참조 경로를 명시해 둠, 완전한 구조적 해결은
  아님).
- SmolVLM 자체의 응답 품질 낮음 문제(unit-35 기존 기록)는 이번 수정과 무관하게
  그대로 남아있음 — disclaimer로 계속 완화.

## 9. 결론 및 판정
- [x] PASS — 다음 단계 진행 가능(7절 Teardown 확인 완료)

## 10. 내부 검증
- L1 경량판(Low Tier) — 1차 검증(작성자 관점): TC-001~007 실행 로그와 본
  문서 대조, 결함 0건. 규칙 B Tier=Low 예외에 따라 2차 생략. 단, §8의 암묵적
  계약(두 파일 간 값 동기화가 코드로 강제되지 않음) 한계는 2차 없이도
  명시적으로 남김.
