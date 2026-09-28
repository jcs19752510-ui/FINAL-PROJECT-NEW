# 테스트 결과서 (Test Result Report) — Feature D 통합테스트 (라이브 코딩, REQ-008)

> `templates/test-report-template.md` 사용. 07단계 — unit-9/unit-20이 남긴 "L1 부채"
> (traceability.md REQ-008 비고: 화이트리스트외언어422/인증없음401/존재하지않는id404/
> 타인세션403/`CodeEditorPanel` 실브라우저 상호작용, unit-20은 "06 정식+07 필요"로
> 별도 명시)를 정산한다. "07단계 통합테스트 부채 21건" 계속 진행분.

## 1. 개요
- 테스트 대상: `backend/app/api/v1/code_submissions.py`(POST/GET), `frontend/app/interviews/[id]/components/CodeEditorPanel.tsx`(Monaco 에디터, [C-07])
- 테스트 유형: 통합(07단계) — 백엔드 API 실측 + 실제 브라우저 UI 실측
- 적용 Tier: Low(오케스트레이터 지시 승계)
- 테스트 목적: unit-9-test.md가 명시적으로 제외한 에러 경로 4종(화이트리스트 외 언어
  422, 인증없음 401, 존재하지 않는 id 404, 타인 세션 403)을 실측하고, unit-20-note.md가
  "브라우저 자동화 포함 06 정식 + 07 필요"로 남긴 `CodeEditorPanel`의 실제 렌더링·
  저장·재접속 복원 동작을 이 프로젝트 최초로 실제 브라우저로 검증
- 관련 산출물: `docs/harness/units/unit-9-note.md`/`unit-9-test.md`, `unit-20-note.md`,
  `docs/harness/decisions.md` DEC-088
- 테스트 수행자(에이전트): 본 세션(07-integration-tester 역할 수행)
- 테스트 일시: 2026-09-28

## 2. 테스트 범위 및 제외 범위
- 범위: POST/GET 양쪽의 인증없음/존재하지않는id/타인세션/화이트리스트외언어 에러
  경로 8케이스(TC-D01~D08) + 실제 면접장 화면에서 코드 에디터 탭 전환→입력→저장→
  새로고침 후 재접속 복원까지의 실브라우저 시나리오(TC-D09)
- 제외 범위 및 사유: 코드 **실행** 기능은 DEC-008에 따라 이 REQ 범위 밖(실행
  엔드포인트는 이미 DEC-069/unit-29로 별도 완료·검증됨, 08 실HTTP+실브라우저 8TC
  PASS). Mobile 전체화면 모달/Tablet 분할 레이아웃 등 반응형 변형은 unit-20-note.md
  자체 브라우저 실측(47/47)이 이미 커버했고 이번 07은 REQ-008(코드 저장/조회) 자체의
  에러 경로·핵심 UX에 집중.

## 3. 테스트 환경
- 로컬 backend(uvicorn, 포트 8000)+frontend(Next.js, 포트 3000), `preview_start`로 기동
- 백엔드 에러 경로(TC-D01~08): `itD1-*`/`itD2-*` candidate 2명, httpx 실HTTP
- 브라우저 시나리오(TC-D09): `itD-browser-*` candidate 1명, 실제 live 세션 1건,
  Claude 내장 브라우저(Browser pane)로 실제 클릭/타이핑/새로고침 수행
- Celery 워커는 기동하지 않음(코드 에디터 저장/조회는 워커에 의존하지 않으므로
  범위 밖 — "AI 면접관이 첫 질문을 준비 중" 무한 대기는 예상된 현상, 결함 아님)

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 예상 결과 | 실제 결과 | Pass/Fail |
|----|----------|-----------|-----------|-----------|
| TC-D01 | POST 인증 없음 | 401 | `401` | PASS |
| TC-D02 | POST 존재하지 않는 interview id | 404 | `404` | PASS |
| TC-D03 | POST 타인 세션(수평 권한 상승) | 403 | `403` | PASS |
| TC-D04 | POST 화이트리스트 외 언어(`cobol`) | 422 | `422`, `value_error` "지원하지 않는 언어" | PASS |
| TC-D05 | GET 인증 없음 | 401 | `401` | PASS |
| TC-D06 | GET 타인 세션 | 403 | `403` | PASS |
| TC-D07 | GET 존재하지 않는 id | 404 | `404` | PASS |
| TC-D08 | 정상 제출(대조군, TC-D05~07 사전조건) | 201 | `201` | PASS |
| TC-D09 | 실브라우저: 탭 전환→Monaco 입력→"제출"→새로고침→탭 재전환 시 저장 내용 복원 | 코드 에디터 탭 클릭 시 Monaco 렌더링, 타이핑 반영, "제출" 클릭 시 실제 `POST .../code-submissions`(201) 발생 + 상태 "저장됨"으로 전환, 페이지 새로고침 후 탭 재클릭 시 이전에 저장한 내용이 에디터에 그대로 복원 | 전부 실제 화면에서 확인: 탭 클릭 시 Monaco 에디터·언어 드롭다운(Python 기본)·"# 여기에 코드를 작성하세요" 플레이스홀더 렌더링, 타이핑 후 상태가 "미저장"으로 전환, "제출" 클릭 시 네트워크 로그에서 `POST .../code-submissions → 201 Created` 확인 + 상태 "저장됨"으로 복귀, 새로고침 후 코드 에디터 탭 재클릭 시 스크린샷으로 이전 입력 내용이 에디터에 그대로 표시됨을 시각 확인 | PASS |

## 5. 커버리지
- unit-9-note.md 미검증 인수조건(에러 경로 4종 × POST/GET) 전부 커버, unit-20-note.md가
  "07 필요"로 명시한 `CodeEditorPanel` 실사용 핵심 흐름(탭 전환·입력·저장·재접속
  복원) 실측 완료. Mobile/Tablet 반응형 변형은 unit-20 자체 06 실측(47/47)으로 이미
  커버돼 중복 검증하지 않음.

## 6. 결함(Defect) 목록
- 결함 없음 — TC-D01~D09 전부 실측으로 확인(위 표 근거).

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 신규 생성한 DB 레코드: candidate 3명(에러경로용 2명 + 브라우저용 1명) + interview
  2건 + code_submission 1건 + consent 1건 — 전부 테스트 종료 직후 DELETE, 재조회 0건 확인
- 기동한 프로세스: `preview_start("backend")`(2회), `preview_start("frontend")`(1회)
  — 매번 `preview_stop`으로 종료
- 전부 `.harness-tmp/` 하위에서만 생성했는가: 해당 없음(저장소 내 임시 아티팩트 없음)
- 정리 완료 여부: 완료
- 정리 후 `git status`: `docs/harness/*` 외 코드 변경 없음(결함이 없어 코드 수정 없음)
- 강제 중단 여부: 없음

## 8. 리스크 및 잔존 이슈
- 코드 **내용**(content)이 화면에 렌더링될 때의 새니타이즈(§6.3/REQ-036)는 Monaco
  에디터가 입력 전용(HTML 렌더링 경로 없음)이라 XSS 자체가 구조적으로 불가능함을
  unit-9-note.md/traceability REQ-036 계열에서 이미 확인한 바 있음 — 이번 07에서도
  별도 리스크로 추가되지 않음.

## 9. 결론 및 판정
- [x] PASS — REQ-008의 "L1 부채" 정산 완료.

## 10. 내부 검증
- 1차(커버리지 확인): unit-9-note.md/unit-20-note.md 미검증 항목과 TC-D01~D09 1:1
  대조 — 누락 없음.
- 2차(재접속 복원의 실질 검증): "GET이 200을 반환한다"만으로 멈추지 않고, 실제로
  에디터 컴포넌트가 그 응답을 받아 Monaco에 값을 채워 넣는 것까지 스크린샷으로
  시각 확인했다 — API 계약과 프론트 소비 로직 사이의 "연결"이 실제로 동작하는지가
  07단계의 핵심 가치이므로, TC-D09를 API 레벨(TC-D08)과 분리해 별도로 실행했다.
