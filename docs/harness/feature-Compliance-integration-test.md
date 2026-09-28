# 테스트 결과서 (Test Result Report) — Feature 규제 컴플라이언스 통합테스트 (REQ-031~034)

> `templates/test-report-template.md` 사용. 07단계 — unit-15가 남긴 "L1 부채"(traceability.md
> REQ-031~034 비고: 인수조건 #1/#4 실브라우저 UI 자동화, #10 예외경로)를 정산한다.
> "07단계 통합테스트 부채 21건" 계속 진행분.

## 1. 개요
- 테스트 대상: `frontend/app/interviews/[id]/consent/page.tsx`([C-04] 사전고지 화면)의
  스크롤-활성화 동작과 세션 상태별 접근 제어(live 리다이렉트/completed 에러/미인증
  리다이렉트)
- 테스트 유형: 통합(07단계) — 실제 브라우저(Claude Browser pane) 사용
- 적용 Tier: Low(오케스트레이터 지시 그대로 승계)
- 테스트 목적: unit-15-test.md가 "브라우저 자동화 도구 부재"로 계속 보류해온 인수조건
  #1(고지문 끝까지 스크롤해야 필수 체크박스 활성화)과 #4(세션 상태별 접근 제어:
  live→자동 리다이렉트, completed/expired→오류 메시지, 미인증→로그인 리다이렉트)를
  이 프로젝트 최초로 실제 브라우저로 검증. 인수조건 #10(예외경로: 재철회409/존재하지
  않는id404/타인소유403)은 Feature G 07단계(DEC-086, `feature-G-integration-test.md`)가
  이미 동일 API(`consents.py`)를 대상으로 실측 완료해 중복 검증 없이 참조로 정산.
- 관련 산출물: `docs/harness/units/unit-15-note.md`/`unit-15-test.md`, `docs/harness/decisions.md`
  DEC-087, `docs/harness/feature-G-integration-test.md`(인수조건 #10 근거)
- 테스트 수행자(에이전트): 본 세션(07-integration-tester 역할 수행)
- 테스트 일시: 2026-09-28

## 2. 테스트 범위 및 제외 범위
- 범위: 인수조건 #1(스크롤-활성화), #4(live/completed/미인증 3가지 접근 제어 분기)
- 제외 범위 및 사유: 인수조건 #10은 Feature G 07단계가 동일 API를 이미 실측 완료 —
  중복 검증 금지 원칙(`.claude/agents/07-integration-tester.md`)에 따라 참조로 정산.
  `paused` 상태 접근 시 동작은 unit-15-note.md 인수조건 목록에 명시되지 않아 범위 밖
  (Feature B 07단계가 이미 세션 상태전이 자체는 검증 완료).

## 3. 테스트 환경
- 로컬 backend(uvicorn, 포트 8000)+frontend(Next.js, 포트 3000), 둘 다 `preview_start`로
  기동, Claude 내장 브라우저(Browser pane)로 실제 클릭/스크롤/네비게이션 수행
- 테스트 데이터: `itReg-browser-*` candidate 1명 + interview 3건(scheduled/live/completed,
  live는 1차 세션에서 이미 검증 완료된 별도 계정 데이터, 사용량 한도로 세션이 끊겨
  completed/scheduled는 2차 세션에서 새 계정으로 재검증) — 전부 테스트 종료 후 DB에서 삭제

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|-----------|-----------|-----------|-----------|------|
| TC-C01 | 고지문 스크롤 전 필수 동의 체크박스 비활성화(인수조건 #1 전반) | `scheduled` 세션의 `/consent` 페이지 로드 직후 DOM에서 체크박스 `disabled` 속성 확인 | 필수 체크박스 `disabled=true` | `disabled=true` 확인(선택 동의 체크박스는 `disabled=false`로 정상 구분) | PASS | |
| TC-C02 | 고지문 끝까지 스크롤 시 체크박스 활성화(인수조건 #1 본체) | 고지문 영역(`aria-label="AI 면접 사전고지 전문"`)을 `scrollHeight`까지 스크롤 후 `scroll` 이벤트 발생시켜 `handleNoticeScroll` 트리거 | 필수 체크박스 `disabled=false`로 전환 | `disabled=false` 확인, 체크 가능 상태로 전환됨을 직접 클릭(`checked=true`)으로 재확인 | PASS | 최초 시도 시 `scrollTop` 속성만 직접 대입해서는 React의 `onScroll` 핸들러가 트리거되지 않아(합성 스크롤 이벤트 미발생) 상태가 갱신되지 않는 현상을 관측 — 명시적으로 `scroll` 이벤트를 `dispatchEvent`한 뒤에야 정상 반영됨을 확인. **이는 테스트 도구(JS 직접 조작)의 한계이지 애플리케이션 결함이 아님** — 실제 사용자의 마우스 휠/터치 스크롤은 항상 네이티브 `scroll` 이벤트를 동반하므로 실사용 환경에서는 문제 없음(아래 8절에도 명시) |
| TC-C03 | live 상태 세션의 `/consent` 접근 시 자동 리다이렉트(인수조건 #4 전반) | `live` 상태 interview의 `/interviews/{id}/consent` URL로 직접 네비게이션 | `/interviews/{id}`(면접장 화면)로 자동 리다이렉트, "LIVE" 상태·질문 준비 중 UI 표시 | URL이 `/consent` 접미사 없이 `/interviews/{id}`로 정확히 변경됨, 실제 면접장 화면("면접장", "LIVE", "AI 면접관이 첫 질문을 준비하고 있습니다...") 렌더링 확인 | PASS | |
| TC-C04 | completed 상태 세션의 `/consent` 접근 시 오류 메시지(인수조건 #4 후반) | `completed` 상태 interview의 `/interviews/{id}/consent` URL로 직접 네비게이션 | "이미 종료/만료" 취지 오류 메시지 + 홈 복귀 링크, 페이지 자체는 정상 렌더링(크래시 없음) | 실제 화면 텍스트: "이 세션은 이미 종료되었거나 만료되어 사전고지 동의를 진행할 수 없습니다." + "홈으로 돌아가기" 링크 정확히 표시 | PASS | |
| TC-C05 | 미인증 상태 접근 시 로그인 리다이렉트(인수조건 #4 마지막 조건) | `sessionStorage`/`localStorage` 클리어(로그아웃 시뮬레이션) 후 `/interviews/{id}/consent`로 네비게이션 | `/login`으로 자동 리다이렉트 | URL이 정확히 `/login`으로 변경, 로그인 폼 렌더링 확인 | PASS | |
| TC-C06(참조) | 예외경로(재철회409/존재하지않는id404/타인소유403) — 인수조건 #10 | Feature G 07단계(DEC-086) 참조 | 동일 API(`consents.py`)에 대해 이미 실측 완료 | `docs/harness/feature-G-integration-test.md` TC-G03~G05 PASS | PASS(참조) | 중복 검증 없이 동일 결과 승계 — 검증 대상 코드가 완전히 동일(같은 라우터·같은 엔드포인트)하므로 재현 없이 참조 |

## 5. 커버리지
- unit-15-note.md 인수조건 #1, #4(3개 분기), #10(참조) 전부 커버 — REQ-031~034가
  공유하는 07 부채 목록 100% 정산.

## 6. 결함(Defect) 목록
- 결함 없음 — TC-C01~C06 전부 실측/참조로 확인(위 표 근거). TC-C02의 "직접 scrollTop
  대입만으로는 이벤트 미발생" 관측은 결함이 아니라 테스트 방법론 상 유의사항으로만
  기록(6절이 아니라 표 자체에 명시, §8에도 재확인).

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 신규 생성한 DB 레코드: candidate 계정(2개 세션에 걸쳐 총 2명, 사용량 한도로 세션이
  끊겨 재시딩) + interview 4건(scheduled 2, live 1, completed 1) — 전부 테스트 종료
  직후 DELETE, 재조회로 0건 확인
- 기동한 프로세스: `preview_start("backend")`, `preview_start("frontend")` 2세션에
  걸쳐 반복 — 매번 `preview_stop`으로 종료 확인
- 전부 `.harness-tmp/` 하위에서만 생성했는가: 해당 없음(저장소 내 임시 아티팩트 없음)
- 정리 완료 여부: 완료
- 정리 후 `git status`: `docs/harness/*` 외 코드 변경 없음(결함이 없어 코드 수정 없음)
- 이번 테스트 도중 강제 중단 여부: **있음** — 세션 도중 사용량 한도에 도달해 TC-C03
  확인 직후 작업이 중단됐다(브라우저 서버는 즉시 정지, DB 테스트 데이터는 정리 완료
  상태로 남김). 재개 시 규칙 K에 따라 잔여 아티팩트 여부를 먼저 재확인했고(`.harness-tmp/`
  및 DB 잔여 계정 재조회, 둘 다 0건), TC-C04/C05는 새 세션·새 서버 프로세스로 처음부터
  다시 검증했다.

## 8. 리스크 및 잔존 이슈
- TC-C02에서 관측한 "JS로 `scrollTop`만 대입하면 React `onScroll`이 반응하지 않는다"는
  현상은 실제 사용자의 스크롤 조작(마우스 휠/트랙패드/터치)에는 영향이 없다 — 브라우저가
  사용자 제스처로 스크롤할 때는 항상 네이티브 `scroll` 이벤트가 동반되기 때문이다.
  자동화 테스트 도구로 재검증할 때는 이 특성을 기억해 `dispatchEvent`를 명시적으로
  호출해야 한다(후속 회귀 테스트 작성 시 참고).

## 9. 결론 및 판정
- [x] PASS — REQ-031~034의 "L1 부채"(인수조건 #1/#4/#10) 정산 완료.

## 10. 내부 검증
- 1차(커버리지 확인): unit-15-note.md가 미검증으로 남긴 인수조건 #1/#4/#10과
  TC-C01~C06을 1:1 대조 — 누락 없음.
- 2차(중단 후 재개 시 무결성 재검토, 규칙 K 3번): 사용량 한도로 세션이 중단된 뒤
  재개하면서, 이전 세션이 남긴 부분 결과(TC-C01/C02, live 계정)를 그대로 신뢰하지
  않고 — 이전 세션에서 실제로 관측했던 원본 도구 출력(disabled 속성 값, URL 변경
  결과)을 그대로 재인용하되, 중단 이후 작업(completed/미인증 시나리오)은 처음부터
  새 계정·새 서버로 재현해 이전 세션의 미완료 부분과 혼동하지 않도록 했다. DB/서버
  프로세스 잔존 여부도 재개 직후 다시 확인했다(§7).
