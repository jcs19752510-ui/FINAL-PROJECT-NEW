# 테스트 결과서 (Test Result Report) — Feature H 통합테스트 (웹캠/운영모니터링/화이트보드, REQ-015/016/017)

> `templates/test-report-template.md` 사용. 07단계 — unit-16/17/18/20이 남긴 "L1 부채"
> (프론트 실브라우저 렌더링·전이, 화이트보드 에러경로)를 정산한다. "07단계 통합테스트
> 부채 21건" 계속 진행분.

## 1. 개요
- 테스트 대상: `backend/app/api/v1/whiteboard.py`(PUT/GET), `backend/app/api/v1/ops.py`
  (`GET /ops/health`), `frontend/components/WebcamPreview.tsx`, `frontend/app/interviews/[id]/components/WhiteboardCanvas.tsx`,
  `frontend/app/admin/ops/page.tsx`
- 테스트 유형: 통합(07단계) — 백엔드 API 실측 + 실제 브라우저 UI 실측
- 적용 Tier: Low(오케스트레이터 지시 승계)
- 테스트 목적: (1) 화이트보드 PUT/GET의 미검증 에러 경로(401/403/404/422) 실측,
  (2) 웹캠 프리뷰 타일의 실제 권한 거부 시나리오와 DEF-001(hydration mismatch
  가능성) 라이브 확인, (3) 화이트보드 캔버스의 실제 마우스 드로잉·저장 확인,
  (4) `/admin/ops` 화면의 실제 렌더링(정상/미인증)
- 관련 산출물: `docs/harness/units/unit-16-note.md`/`unit-16-test.md`,
  `unit-17-note.md`/`unit-17-test.md`, `unit-18-note.md`/`unit-18-test.md`,
  `docs/harness/decisions.md` DEC-090
- 테스트 수행자(에이전트): 본 세션(07-integration-tester 역할 수행)
- 테스트 일시: 2026-09-28

## 2. 테스트 범위 및 제외 범위
- 범위: 화이트보드 PUT/GET 7케이스(TC-H01~H07), `/ops/health` 3케이스(TC-H08~H10),
  실브라우저 웹캠 권한거부 상태 렌더링, 화이트보드 마우스 드로잉+저장, `/admin/ops`
  정상/미인증 렌더링
- 제외 범위 및 사유: 실제 카메라 권한 **허용**(active) 상태는 이 브라우저 환경이
  가상 카메라 장치를 제공하지 않아(Browser pane 자체가 카메라 접근을 차단) 재현
  불가 — 대신 권한 **거부**(permission-denied) 상태로 그레이스풀 디그레이드가
  실제로 동작하는지를 검증했다(off→요청→거부 전이는 실사용 시나리오 중 하나를
  실제로 완주한 것). `/admin/ops`의 "candidate로 로그인했지만 admin이 아님"(403)
  상세 UI는 API 레벨(TC-H09)로 이미 확인, 브라우저 레벨은 미인증(로그인 필요) 상태만
  실브라우저로 확인 — 시간 제약상 두 경우 모두 백엔드 계약은 동일(403 vs 401)하고
  프론트가 둘 다 오류 배너로 처리하는 공통 로직임을 코드로 확인.

## 3. 테스트 환경
- 로컬 backend(uvicorn, 포트 8000)+frontend(Next.js, 포트 3000), `preview_start`로 기동
- 백엔드 에러 경로: `itH1-*`/`itH2-*` candidate 2명 + `itH-admin-*`(DB에서 role을
  admin으로 직접 변경, admin은 자가등록 불가라 unit-18 선례와 동일하게 처리)
- 브라우저 시나리오: `itH-browser-*` candidate 1명(live 세션 1건) + `itH-admin-browser-*`
  (admin 승격) — Claude 내장 브라우저로 실제 클릭/드래그/카메라 권한 요청 수행

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 예상 결과 | 실제 결과 | Pass/Fail |
|----|----------|-----------|-----------|-----------|
| TC-H01 | 화이트보드 PUT 인증 없음 | 401 | `401` | PASS |
| TC-H02 | PUT 존재하지 않는 id | 404 | `404` | PASS |
| TC-H03 | PUT 타인 세션 | 403 | `403` | PASS |
| TC-H04 | PUT 잘못된 stroke(빈 points) | 422 | `422`, `value_error` | PASS |
| TC-H05 | GET 인증 없음 | 401 | `401` | PASS |
| TC-H06 | GET 타인 세션 | 403 | `403` | PASS |
| TC-H07 | GET 존재하지 않는 id | 404 | `404` | PASS |
| TC-H08 | `/ops/health` 인증 없음 | 401 | `401` | PASS |
| TC-H09 | `/ops/health` candidate(비admin) | 403 | `403` | PASS |
| TC-H10 | `/ops/health` admin | 200, 4지표+notes | `200`, `queue_length`/`gpu_memory_used_bytes`/`error_rate`/`active_sessions`/`checked_at`/`notes` 전부 포함 확인 | PASS |
| TC-H11 | 실브라우저: 웹캠 타일 off→"켜기" 클릭→권한 거부 전이 | 초기 "웹캠이 꺼져 있습니다" → 클릭 시 권한 요청 → 거부 시 "카메라 권한이 거부되었습니다. 웹캠 없이 텍스트로 계속 진행할 수 있습니다." 안내 + "다시 시도" 버튼, 크래시 없음 | 정확히 그대로 재현, 화면 크래시·에러 경계 발동 없음, 이후 화면 조작(탭 전환 등) 계속 정상 동작 | PASS |
| TC-H12 | 실브라우저: 화이트보드 마우스 드래그로 선 그리기 | 캔버스에 시각적으로 선이 그려짐 | 스크린샷으로 선이 실제로 그려짐을 시각 확인 | PASS |
| TC-H13 | 실브라우저: 화이트보드 "저장" 클릭 | 실제 `PUT .../whiteboard` 발생, 200 응답 | 네트워크 로그에서 `PUT .../whiteboard → 200 OK` 확인 | PASS |
| TC-H14 | 실브라우저: `/admin/ops` admin 로그인 상태 렌더링 | 4개 지표 카드(큐길이/GPU메모리/에러율/활성세션)+최근갱신시각+"지표 산출 근거" 섹션 | 전부 정확히 렌더링 확인(활성 세션 수는 실제 DB 누적값 646명 — 실측 카운트가 살아있음을 확인) | PASS |
| TC-H15 | 실브라우저: `/admin/ops` 미인증 상태 렌더링 | "로그인이 필요합니다" 안내 + 로그인 링크, 크래시 없음 | 정확히 그대로 재현 | PASS |

## 5. 커버리지
- REQ-017(화이트보드) 에러 경로 7종 + 실드로잉/저장 전부 커버.
- REQ-016(운영 모니터링) 인증/권한 3종 + 실렌더링(정상/미인증) 커버 — candidate
  403의 브라우저 레벨 렌더링만 시간 제약상 API 검증으로 대체(§2 명시).
- REQ-015(웹캠 프리뷰) off→권한거부 전이 실측 — DEF-001(hydration mismatch
  가능성)은 이번 페이지 로드·상태 전이 과정에서 React hydration 관련 콘솔 에러가
  관측되지 않았으나, 이 세션의 브라우저 콘솔 로그가 하루 종일 누적된 상태라
  "이번 로드에 한정된 깨끗한 로그"로 단정하기 어려움 — **DEF-001은 완전히 Closed로
  확정하지 않고 Medium/Deferred 상태 그대로 유지**(정직성 원칙, 근거 불충분한 낙관
  금지).

## 6. 결함(Defect) 목록
- 결함 없음(신규) — TC-H01~H15 전부 실측으로 확인. 기존 DEF-001(unit-16-test.md)은
  이번에도 재현되지 않았으나 "완전히 해소됨"을 확정할 만큼 깨끗한 콘솔 로그 조건이
  아니었으므로 상태를 낙관적으로 바꾸지 않고 Deferred로 유지(위 5절 참고).

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 신규 생성한 DB 레코드: candidate 4명(에러경로 2 + 브라우저 2) + interview 2건
  + whiteboard_snapshot 1건 + consent 1건 — 전부 테스트 종료 직후 DELETE, 재조회
  0건 확인. 실사용자 기존 데이터(`active_sessions` 등 집계값에 포함된 것)는 전혀
  수정/삭제하지 않음(읽기만 함)
- 기동한 프로세스: `preview_start("backend")`(2회), `preview_start("frontend")`(1회)
  — 매번 `preview_stop`으로 종료
- 전부 `.harness-tmp/` 하위에서만 생성했는가: 해당 없음(저장소 내 임시 아티팩트 없음)
- 정리 완료 여부: 완료
- 정리 후 `git status`: `docs/harness/*` 외 코드 변경 없음(결함이 없어 코드 수정 없음)
- 강제 중단 여부: 없음

## 8. 리스크 및 잔존 이슈
- `active_sessions` 실측값이 646으로 상당히 큼 — 이 프로젝트가 장기간 다수
  세션에 걸쳐 반복 테스트되며 정리되지 않은 `live` 상태 interview가 누적된 것으로
  추정된다(REQ-013 `paused` 자동전이 미구현과 맞물려, 시작만 하고 끝내지 않은
  세션은 만료 전까지 계속 `live`로 집계됨). **이번 07 범위 밖이라 정리하지 않았음**
  — 운영 관점에서 별도 정리가 필요하다면 후속 논의 필요(실사용자 데이터라 이
  세션이 임의로 삭제하지 않음).
- DEF-001(hydration mismatch)은 여전히 미확정(Deferred) — 완전한 확정을 원하면
  브라우저를 완전히 새로 열어(콘솔 로그 0줄 상태에서) 웹캠 타일이 있는 페이지의
  최초 로드만 단독으로 재현하는 별도 세션이 필요.

## 9. 결론 및 판정
- [x] PASS — REQ-015/016/017의 "L1 부채"(에러경로+UI렌더링) 정산 완료. DEF-001은
  의도적으로 미확정 상태 유지(정직성 원칙, 8절 참고).

## 10. 내부 검증
- 1차(커버리지 확인): unit-16/17/18-note.md 미검증 항목과 TC-H01~H15 1:1 대조 —
  DEF-001 완전 확정만 의도적으로 보류, 나머지 누락 없음.
- 2차(과신 경계 재검토): "권한 거부 화면이 떴다 = DEF-001이 없다"고 성급히
  결론짓지 않았다 — hydration mismatch는 최초 SSR↔최초 client render 순간에만
  발생하는 특성이라 콘솔이 이미 다른 페이지 이동으로 오염된 상태에서는 재현
  여부를 판단할 근거가 불충분함을 인지하고, 판정을 Deferred로 정직하게 유지했다
  (근거 없는 낙관적 Closed 처리 금지 — ORCHESTRATOR.md 정직성 원칙 그대로 적용).
