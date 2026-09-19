# 테스트 결과서 — unit-15 (Feature G. 규제 컴플라이언스, REQ-031~034)

## 1. 개요
- 테스트 대상: `frontend/app/interviews/[id]/consent/page.tsx`([C-04] 사전고지 화면), `frontend/app/legal/page.tsx`([C-14] 법률고지 화면), `frontend/app/mypage/page.tsx`([C-13] 동의관리 화면), `frontend/lib/complianceContent.ts`(정적 고지 문구)
- 테스트 유형: 단위 (규칙 F 재검증 — 회귀 테스트)
- 적용 Tier: Low (오케스트레이터 지시)
- 적용 속도 트랙: **L1** — 경량판. `test-report-template.md` 1·2·3·4·6·7·9절만 정식 작성, 5·8절은 "L1 경량판 — 미해당"으로 명시. 10절은 최초 라운드에서 실제로 결함(DEF-001)을 찾아낸 근거를 남기기 위해, 그리고 이번 재검증 라운드에서도 회귀 여부를 재점검한 근거를 남기기 위해 간략히 기록한다.
- 테스트 목적: 05단계가 DEF-001(High) 수정을 완료한 뒤, 06단계가 **TC-003(정적 문구 검증)만 독립 재실행**하여 `LEGAL_DISCLAIMER_TEXT`에 보관기간 임시값 문장이 실제로 포함됐는지 원문 grep으로 재확인하고, 이번 수정이 TC-001/TC-002가 검증한 로직(동의 플로우, 마이페이지 동의관리)의 범위를 벗어나지 않았음을 코드 diff/변경 파일 목록으로 확인하며, 게이트1(lint/build)을 재확인한다.
- 관련 산출물: `docs/harness/units/unit-15-note.md`(§6 인수조건, §7 재작업 변경이력), 이전 라운드 결과(FAIL, DEF-001) — 본 파일이 그 위에 덮어써 최종본이 됨, `docs/harness/03-system-design.md` §4.2/§6.2, `docs/harness/04-ux-design.md` [C-04]/[C-13]/[C-14], `docs/harness/traceability.md`(REQ-031~034)
- 테스트 수행자(에이전트): `06-unit-tester`
- 테스트 일시: **1차 라운드** 2026-09-19 15:47 KST경(FAIL, DEF-001 발견) → **2차 라운드(본 회귀 재검증)** 2026-09-19 15:5x~16:0x KST경(PASS 확정)

> 이 보고서는 "단위+통합 병합" 대상이 아니다. Feature G는 이 feature 내 작업 단위 총 개수 2개(unit-14/15), Tier Low로 병합 조건의 두 요건(마지막 단위/Low/3개 이하)은 형식상 충족하지만, 이 유닛의 속도 트랙이 **L1**이므로 오케스트레이터 지시에 따라 **07단계로 handoff하지 않고**, 대신 `docs/harness/traceability.md`의 해당 REQ-ID 비고란에 "L1 부채 — 07·(06 정식화) 08 착수 전 정산 필요"를 표시한 뒤 05단계로 돌아가 다음 작업 단위를 진행한다(L1 규칙이 Low-tier 병합 규칙보다 우선 적용됨).

## 2. 테스트 범위 및 제외 범위
- 범위 (In-Scope, 이번 회귀 재검증 라운드):
  - **TC-003 재실행(필수)**: `frontend/lib/complianceContent.ts`의 `LEGAL_DISCLAIMER_TEXT`에 "180"/"임시값" 관련 문구가 실제로 포함되는지 원문 grep으로 직접 재확인(인수조건 #9).
  - **회귀 범위 확인**: 이번 05단계 수정이 TC-001(사전고지 동의 플로우)·TC-002(마이페이지 동의관리)가 검증한 로직을 건드리지 않았음을, 변경 파일 목록(`git status`)과 파일 mtime 대조로 확인. note §7이 "이 파일 외 다른 파일은 수정하지 않았다"고 자체 기록한 내용을 06단계가 독립적으로 재검증.
  - **게이트1 재확인**: `npm run lint`, `npx tsc --noEmit`, `npm run build`를 06단계가 이번 세션에서 다시 독립 실행.
- 이번 라운드에서 재실행하지 않은 것(사유):
  - TC-001(사전고지 동의 실통합), TC-002(마이페이지 동의관리 실통합) — 1차 라운드(FAIL 이전)에서 이미 PASS로 확정되었고(§4 참고, 실제 API 호출·응답 필드값 대조까지 완료), 이번 수정 대상(`complianceContent.ts`의 `LEGAL_DISCLAIMER_TEXT` 문자열 상수 1개)이 두 TC가 검증한 백엔드 API 연동 로직·프런트 핸들러 로직과 전혀 겹치지 않음을 diff 범위로 확인했으므로 재실행 불필요(오케스트레이터 지시).
  - 그 외 1차 라운드에서 이미 Out-of-Scope로 명시한 항목(인수조건 #1/#4 UI 자동화, #10 예외경로 — L1 부채)은 이번 라운드에도 동일하게 범위 밖.

## 3. 테스트 환경
- 실행 환경: Windows 11, Git Bash, `frontend/` 디렉터리에서 `npm run lint`(ESLint) / `npx tsc --noEmit` / `npm run build`(Next.js 16.3.5, Turbopack) 직접 실행. Node v24.14.0, npm 11.9.0.
- 이번 재검증 라운드는 **정적 문구 대조 + 정적 분석 게이트**만 다루므로 별도 backend 서버(uvicorn)·DB·격리 venv를 새로 기동하지 않았다(TC-001/TC-002를 재실행하지 않으므로 1차 라운드가 이미 만든 `.harness-tmp/venv_06_unit15` 등은 애초에 재사용 대상이 아니며, 1차 라운드 §7에서 이미 정리·삭제 완료된 상태를 유지).
- 전제 조건: `frontend/lib/complianceContent.ts`가 05단계 재작업(unit-15-note.md §7, 2026-09-19)으로 수정된 상태.

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-001 | 사전고지 동의 → 세션 시작 실통합(인수조건 #2,#3,#4 데이터전제) | (1차 라운드에서 검증 완료) | (재실행 안 함 — §2 참고) | — | 1차 라운드에서 이미 실제 API 6단계 시퀀스(조회→403게이트→동의2건→start 202→재조회)로 재현, 응답 상태코드·필드값 전부 대조 완료 | **PASS (이월, 재실행 불필요)** | 이번 수정(`LEGAL_DISCLAIMER_TEXT` 문자열 추가)이 `consent/page.tsx`의 핸들러 로직·`api.ts`의 `createConsent`/`startInterview` 호출부와 무관함을 `git status`(수정 파일: `complianceContent.ts` 1개뿐)와 파일 mtime(`consent/page.tsx` 최종 수정 08:12, 이번 수정 시각 15:50 이전)으로 확인 |
| TC-002 | 마이페이지 동의관리 실통합(인수조건 #6,#7,#8) | (1차 라운드에서 검증 완료) | (재실행 안 함 — §2 참고) | — | 1차 라운드에서 이미 실제 API 6단계 시퀀스(계정조회→동의목록→철회→재조회→삭제요청→이력조회)로 재현, 응답 필드값(`revoked_at` null/not-null 전이 등) 전부 대조 완료 | **PASS (이월, 재실행 불필요)** | `mypage/page.tsx` 최종 수정 시각(15:32:01)이 이번 DEF-001 수정 시작 시점(`complianceContent.ts` 수정 15:50:08)보다 앞서며, 그 15:32 시점 변경은 1차 라운드 FAIL 판정(15:47) 이전의 기존 구현분(lint 수정, note §0 기록)이므로 이번 재작업과 무관함을 확인 |
| TC-003 | **정적 컴플라이언스 문구 원문 재대조(인수조건 #9) — 회귀 재검증 본체** | `frontend/lib/complianceContent.ts`가 05단계 재작업(2026-09-19)으로 수정된 상태 | `grep -n "180\|임시값" frontend/lib/complianceContent.ts`를 06단계가 직접 실행해 `PRE_NOTICE_TEXT`(12~41행)와 `LEGAL_DISCLAIMER_TEXT`(43~60행) 두 구간 모두에서 매치가 나오는지 원문으로 확인 | `PRE_NOTICE_TEXT` 구간과 `LEGAL_DISCLAIMER_TEXT` 구간 양쪽에서 "180" 또는 "임시값" 매치가 각각 1건 이상 나와야 함(인수조건 #9: 두 문구 **모두** 포함) | 실제 grep 결과: `7:...보관기간(180일)...`, `8:..."법률자문 확인 필요" 임시값...`(파일 상단 주석), `10:export const RETENTION_DAYS_PROVISIONAL = 180;`, `29:...보관기간은 아직 법률자문을 거치지 않은 임시값입니다...`(`PRE_NOTICE_TEXT` 내부), `30:...확정 전까지 이 화면은 이 임시값을 그대로 노출합니다...`(`PRE_NOTICE_TEXT` 내부), `59:...${RETENTION_DAYS_PROVISIONAL}일은 아직 법률자문을 거치지 않은 임시값이며,`(**`LEGAL_DISCLAIMER_TEXT` 내부, 신규 추가분**) — `LEGAL_DISCLAIMER_TEXT` 구간(43~60행)에서 이전 라운드(0건)와 달리 59행이 새로 매치됨을 확인. 라인 번호 기준으로 파일을 직접 재열람(Read)해 59~60행이 `LEGAL_DISCLAIMER_TEXT`의 마지막 문단(58~60행, "현재 안내 중인 보관기간 ${RETENTION_DAYS_PROVISIONAL}일은 아직 법률자문을 거치지 않은 임시값이며, 실제 운영 정책은 추후 법률 검토 후 확정됩니다.") 안에 위치함을 라인 단위로 검증 | **PASS** | `${RETENTION_DAYS_PROVISIONAL}`는 템플릿 리터럴 변수 참조이며 런타임에 `180`으로 치환되어 렌더링됨(10행에서 `RETENTION_DAYS_PROVISIONAL = 180`으로 확정, `PRE_NOTICE_TEXT`도 동일 패턴(27행)을 이미 사용 중이므로 동일 근거로 유효) — 소스 문자열이 리터럴 "180"이 아니라 변수 참조라는 이유로 조건 미충족이라 보지 않는다. 인수조건 #5(3개 문구: "AI는 보조 도구", "법적 효력 없음", "전문가 자문 권고")는 1차 라운드에서 이미 PASS 확인했고 이번 수정이 해당 문장들을 삭제/변경하지 않았음을 원문 재확인(45~55행 그대로 유지) |

- 게이트1 재확인(06단계 독립 재실행):
  - `npm run lint` → **0 errors, 1 warning**(`app/interviews/new/page.tsx`의 `<a>` 태그 경고 — unit-15 범위 밖 기존 파일, 1차 라운드와 동일 warning으로 회귀 없음 확인).
  - `npx tsc --noEmit` → **에러 없음**(exit code 0).
  - `npm run build` → **성공**. 라우트 구성 1차 라운드와 동일: `/legal`(○ Static), `/mypage`(○ Static), `/interviews/[id]/consent`(ƒ Dynamic) 모두 정상 생성, 신규 에러/경고 없음.

## 5. 커버리지
L1 경량판 — 미해당.

## 6. 결함(Defect) 목록
| ID | 설명 | 재현 절차 | 심각도(Critical/High/Medium/Low) | 상태(Open/Fixed/Deferred) | 조치 내용 |
|----|------|-----------|-----------------------------------|----------------------------|-----------|
| DEF-001 | `frontend/lib/complianceContent.ts`의 `LEGAL_DISCLAIMER_TEXT`(법률/컴플라이언스 고지, `/legal` 화면)에 "보관기간 180일은 법률자문 미확정 임시값"이라는 취지의 문장이 전혀 없어 인수조건 #9(사전고지·법률고지 문구 **모두** 포함) 미충족 — 1차 라운드(2026-09-19 15:47경)에서 발견 | 1) `frontend/lib/complianceContent.ts` 열기 2) `LEGAL_DISCLAIMER_TEXT`(당시 43~58행) 원문에서 "180"/"임시값" 검색 → 0건(1차 라운드 재현) | High | **Fixed** | 05단계가 `LEGAL_DISCLAIMER_TEXT` 마지막 문단(58~60행)에 "현재 안내 중인 보관기간 ${RETENTION_DAYS_PROVISIONAL}일은 아직 법률자문을 거치지 않은 임시값이며, 실제 운영 정책은 추후 법률 검토 후 확정됩니다."를 추가(unit-15-note.md §7). 06단계가 본 회귀 재검증(§4 TC-003)에서 `grep -n "180\|임시값"` 재실행 결과 59행이 신규 매치됨을 직접 확인해 수정 완료를 검증했다. 다른 파일은 수정되지 않았음을 `git status`(변경분: `complianceContent.ts` 1개)로 재확인 — 부수 효과(side effect) 없음. |

- 결함 1건(DEF-001), **Fixed로 확정**. 신규 결함 0건.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 회귀 재검증(2차 라운드)에서 생성한 임시 아티팩트:
  - `.harness-tmp/lint_06_unit15_reverify.log`, `.harness-tmp/tsc_06_unit15_reverify.log`, `.harness-tmp/build_06_unit15_reverify.log`(게이트1 재실행 로그 캡처용, 이 재검증 세션 전용) — 검증 완료 직후 3개 파일 모두 삭제 완료.
  - 별도 venv/서버 프로세스/DB는 이번 라운드에서 신규 생성하지 않았다(TC-001/TC-002 미재실행이므로 불필요, §3 참고).
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): [x] 예.
- 정리(삭제) 완료 여부: 완료. `ls .harness-tmp/`로 위 3개 로그 파일이 더 이상 존재하지 않음을 확인(디렉터리에 남은 항목은 모두 unit-5/9/12/13 등 다른 작업 단위가 생성한 것으로 이번 유닛 소관이 아니며 임의로 건드리지 않았다).
- 새로 기동한 백그라운드 프로세스(uvicorn 등)는 없으므로 PID 기준 종료 대상도 없음(규칙 K/DEC-028 해당 없음, 이번 라운드는 정적 분석·문자열 대조만 수행).
- 정리 후 `git status` 확인: `.harness-tmp/`는 `.gitignore`(7행)에 의해 추적되지 않음(`git check-ignore -v .harness-tmp/` 확인). 이번 라운드가 실제로 수정한 추적 대상 파일은 `docs/harness/units/unit-15-test.md`(본 파일, 갱신)와 `docs/harness/traceability.md`(REQ-031~034 갱신) 2개뿐이며, `frontend/lib/complianceContent.ts`는 05단계가 이미 수정을 마친 상태(untracked `??`)를 06단계가 읽기만 했다 — 06단계 세션 자체가 만든 새 미정리 아티팩트는 없다.
- 이번 재검증 도중 강제 중단(TaskStop 등)이 있었는가: [x] 없음.

## 8. 리스크 및 잔존 이슈
L1 경량판 — 미해당. (단, 인수조건 #10(예외경로: 재철회 409/존재하지 않는 id 404/타인 소유 403) 및 인수조건 #1/#4의 실제 브라우저 UI 자동화 검증은 1차 라운드와 동일하게 여전히 미수행 — "L1 부채 — 07(및 06 정식화) 08 착수 전 정산 필요"로 traceability.md에 이월)

## 9. 결론 및 판정
- [x] **PASS**
- [ ] CONDITIONAL PASS
- [ ] FAIL

판정 근거:
- DEF-001(High)이 05단계 재작업으로 수정되었고, 06단계가 TC-003을 원문 grep으로 독립 재실행해 `LEGAL_DISCLAIMER_TEXT`에 보관기간 임시값 문장(59행)이 실제로 존재함을 확인했다(§4). "에러 없이 실행됨"이 아니라 인수조건 #9가 요구하는 문자열 내용 자체가 소스에 존재함을 라인 단위로 대조해 PASS 판정한다.
- TC-001/TC-002는 1차 라운드에서 이미 실제 API 통합으로 PASS 확정되었고, 이번 수정이 그 범위(백엔드 연동 로직, 프런트 핸들러)를 건드리지 않았음을 `git status`(수정 파일 1개)와 mtime 대조로 재확인했으므로 재실행 없이 PASS를 유지한다.
- 게이트1(`npm run lint` 0 errors / `tsc --noEmit` 0 errors / `npm run build` 성공)을 06단계가 이번 세션에서 독립적으로 재실행해 회귀가 없음을 확인했다.
- 신규 결함 0건, 기존 결함(DEF-001) 1건 모두 Fixed. 테스트 환경 정리(Teardown, 규칙 K) 완료.
- **L1 규칙에 따라 07단계(통합테스트)로 handoff하지 않는다.** `docs/harness/traceability.md`의 REQ-031~034 "단위테스트" 컬럼을 PASS로, "비고" 컬럼을 "L1 부채 — 07·(06 정식화) 08 착수 전 정산 필요"로 갱신한 뒤, 05단계로 돌아가 다음 작업 단위를 진행하도록 인계한다.

## 10. 내부 검증 (최소 2회)
- 1차(인수조건 커버리지 확인, 회귀 재검증 관점): DEF-001이 지적한 유일한 미충족 인수조건(#9)에 대해서만 재검증이 필요했고, TC-003 재실행으로 `LEGAL_DISCLAIMER_TEXT`·`PRE_NOTICE_TEXT` 양쪽 모두에서 "180"/"임시값" 취지 문장이 실존함을 원문 grep+라인 단위 Read로 확인했다 — 인수조건 #9 커버리지 100%. 나머지 인수조건(#1~#8)은 1차 라운드에서 이미 PASS 확정되었고 이번 수정 범위 밖이므로 재검증 대상이 아니다(diff 범위 확인으로 뒷받침).
- 2차(과신 경계 재검토): "복구된 문장이 인수조건 문구와 문자 그대로 일치하는가, 혹은 형식만 갖추고 실질이 다른가"를 의심했다. 실제로 추가된 문장(58~60행)은 `${RETENTION_DAYS_PROVISIONAL}`이라는 변수 참조 형태라 grep에서 리터럴 "180"이 직접 매치되지 않고 "임시값"만 매치되는 점을 발견했으나, `PRE_NOTICE_TEXT`의 기존 PASS 처리 문장(27행)도 동일하게 변수 참조 형태이며 인수조건 #9 자체가 "값의 정확성이 아니라 임시값임을 숨기지 않는다"는 취지(unit-15-note.md §2)이므로 변수 참조를 리터럴로 치환한 렌더링 결과(180)가 실제로 노출된다는 점까지 확인해 PASS로 판단했다 — "grep에 매치됐다"에서 멈추지 않고 "왜 매치됐는지, 값이 실제로 무엇으로 렌더링되는지"까지 재검토했다. 추가로 이번 수정이 인수조건 #5(3개 문구)가 요구하는 기존 문장을 실수로 삭제/변형하지 않았는지도 원문 재대조해 회귀 없음을 확인했다.
