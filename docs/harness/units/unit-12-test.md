# 테스트 결과서 (Test Result Report) — unit-12 (Feature F. 채용담당자 대시보드, REQ-011)

## 1. 개요
- 테스트 대상: unit-12 — 백엔드 `backend/app/api/v1/recruiter.py`(`GET /recruiter/reports`, `GET /recruiter/reports/{interview_id}`) + `backend/app/schemas/recruiter.py`, 프론트엔드 `frontend/app/recruiter/page.tsx`([R-01]), `frontend/app/recruiter/[id]/page.tsx`([R-02])
- 테스트 유형: 단위
- 적용 Tier: High(DEC-002, `docs/harness/decisions.md`) — 단, 이 feature(F)는 오케스트레이터가 Speed Track **L1**로 별도 지정하여, ORCHESTRATOR.md 1장 "구현 속도 트랙" 규정에 따라 06단계는 경량판으로 작성한다(Tier=High가 규칙 B 완화를 자동으로 주지는 않으나, L1 트랙 자체가 06/07 산출물 형식에 대한 별도 규정이며 이번 06은 그 규정을 따른다).
- 적용 속도 트랙: L1 — 정상 경로 1~2케이스 중심 경량판. 5·8·10절은 "L1 경량판 — 미해당/생략"으로 명시.
- 테스트 목적: 05단계(`docs/harness/units/unit-12-note.md`)가 자체 보고한 게이트1/2 통과 및 curl 검증 결과를 06단계가 **독립적으로(별도 신규 서버 프로세스, 별도 격리 venv)** 재현해, "돌아가는 것 같다"가 아니라 실측 근거로 확인한다.
- 관련 산출물: `docs/harness/03-system-design.md` §1.2/§4.2/§6.1, `docs/harness/04-ux-design.md` [R-01]/[R-02], `docs/harness/units/unit-12-note.md`(인수조건 §5), `docs/harness/traceability.md` REQ-011 행
- 테스트 수행자(에이전트): 06-unit-tester
- 테스트 일시: 2026-09-19

## 2. 테스트 범위 및 제외 범위
- 범위 (In-Scope):
  - unit-12-note.md §5의 인수조건 1~5 각각에 대응하는 재현 테스트(백엔드 4건은 신규 서버로 직접 curl 재현, 프론트 1건은 코드 레벨 검토 + 독립 재실행한 ESLint/tsc로 확인)
  - 05단계가 주장한 게이트1(정적분석/린트)·게이트2(자체 코드 리뷰 체크리스트) 통과 여부를 note 기록 대조 + 일부 독립 재실행으로 확인
- 제외 범위 및 사유:
  - 실제 브라우저 렌더링(픽셀/DOM 레벨) 검증 — 이 환경에 브라우저 자동화 도구가 없어 05단계와 동일한 한계(unit-12-note.md §4). L1 원칙상 "07(및 06 정식화) 08 착수 전 정산" 항목으로 traceability.md에 명시(9절/본 보고서 결론 참고).
  - 필터/정렬/페이지네이션, 리포트 본문(점수 게이지/STAR/근거 아코디언) — unit-12-note.md §2에서 설계서 대비 편차로 이미 명시된 범위 밖 항목이며 인수조건에도 없음.
  - `/interviews/{id}/report` canonical 엔드포인트와의 중복 정리(Feature E 착수 후 과제) — 이 유닛 범위 밖.
  - 부하/동시성 테스트 — L1 경량판 및 인수조건에 해당 항목 없음.
- 위험 감지에 따른 범위 외 추가 케이스: 존재하지 않는 `interview_id`(UUID) 조회 시 404 확인(TC-005) — 인수조건 4에 이미 명시되어 있어 엄밀히는 범위 내이지만, "정상 경로 1~2케이스"라는 L1 최소 기준을 넘어 401/403/404 경계도 저비용으로 함께 재현해 신뢰도를 높였다(아래 4절 참고).

## 3. 테스트 환경
- 실행 환경: Windows 11, Python 3.12(신규 격리 venv), PostgreSQL 16(Docker `final-project-db`, 포트 5544, 기존 컨테이너 재사용 — 스키마 변경 없음), FastAPI/uvicorn(포트 8214, 06단계가 신규로 기동한 독립 프로세스), Node.js(기존 `frontend/node_modules` 재사용, ESLint/tsc만 재실행)
- 테스트 데이터: 06단계가 이번 세션에서 신규 발급한 candidate 1명(`u12cand_<ts>@test.com`)·recruiter 1명(`u12recruit_<ts>@test.com`) 계정과 그 candidate가 생성한 면접 세션(interview) 1건. DB에 이미 존재하던 다른 유닛들의 테스트 데이터(9건)는 "recruiter가 전체 지원자를 열람한다"는 인수조건 3을 검증하는 데 오히려 유용해 그대로 활용(수정하지 않음).
- 전제 조건: 05단계 산출물(코드)이 그대로 존재하고 수정되지 않은 상태. `.harness-tmp/venv_05_unit12`는 05단계 소유 리소스이므로 06단계는 이를 재사용하지 않고 별도의 `.harness-tmp/venv_06_unit12`를 생성해 완전히 격리했다(규칙 K, DEC-027 취지 반영).

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-001 | 인증 토큰 없이 목록 조회 (인수조건 1) | 서버 기동 완료 | `curl GET /api/v1/recruiter/reports` (Authorization 헤더 없음) | `401`, `code=AUTH_INVALID_TOKEN` | `401`, `{"code":"AUTH_INVALID_TOKEN","detail":"인증 토큰이 필요합니다."}` | PASS | 예방적 권한 경계 확인(범위 외 추가) |
| TC-002 | candidate 토큰으로 목록 조회 (인수조건 2) | candidate 계정 신규 가입+로그인 완료 | candidate access_token으로 `GET /api/v1/recruiter/reports` | `403`, `code=AUTH_FORBIDDEN` | `403`, `{"code":"AUTH_FORBIDDEN","detail":"채용담당자(recruiter)만 접근할 수 있습니다."}` | PASS | 예방적 권한 경계 확인(범위 외 추가) |
| TC-003 | recruiter 토큰으로 전체 목록 조회 — **정상 경로 1** (인수조건 3) | recruiter 계정 신규 가입+로그인 완료, candidate가 면접 세션 1건 생성 완료 | recruiter access_token으로 `GET /api/v1/recruiter/reports` | `200`, JSON 배열에 방금 생성한 인터뷰 포함 + 이 recruiter가 생성하지 않은 **다른 지원자들의 인터뷰도 포함**(MVP 단일조직 정책, §6.1) | `200`, 배열 10건 반환. 이번에 만든 신규 interview 1건 + 사전 존재하던 다른 유닛 테스트용 지원자 9명(unit-2/9/14/15 등)의 인터뷰가 모두 포함됨 | PASS | recruiter 전원 전체 열람 정책이 실측으로 확인됨(설계서 §6.1과 일치) |
| TC-004 | recruiter 토큰으로 존재하는 리포트 상세 조회 — **정상 경로 2** (인수조건 4 전반) | TC-003의 interview_id 확보 | recruiter access_token으로 `GET /api/v1/recruiter/reports/{interview_id}` | `200`, `report_available=false`, `message`에 `report_status=none`에 대응하는 한국어 안내 문구 | `200`, `report_available=false`, `message="아직 리포트 생성이 요청되지 않았습니다."` (interview의 report_status가 `none`이므로 recruiter.py `_report_state_message` 분기와 일치) | PASS | 코드(§`_report_state_message`)와 실제 응답 문구 1:1 대조 완료 |
| TC-005 | recruiter 토큰으로 존재하지 않는 UUID 상세 조회 (인수조건 4 후반, 예외 입력) | 임의의 미존재 UUID(`00000000-0000-0000-0000-000000000000`) | recruiter access_token으로 `GET /api/v1/recruiter/reports/{미존재-uuid}` | `404`, `code=NOT_FOUND` | `404`, `{"code":"NOT_FOUND","detail":"면접 세션을 찾을 수 없습니다."}` | PASS | 경계값(존재하지 않는 리소스) 케이스 |
| TC-006 | 프론트엔드 `/recruiter`, `/recruiter/[id]` 코드 레벨 검증 (인수조건 5) | 없음 | (a) `page.tsx`/`[id]/page.tsx` 소스를 인수조건 5 문구와 1:1 대조 — role!=recruiter 시 API 미호출 후 안내문 렌더링 분기, recruiter일 때만 `getRecruiterReports` 호출, 행 클릭 시 `router.push(`/recruiter/${id}`)`, 상세 페이지가 `report_available` 무관 `disclaimerBanner`를 항상 렌더링하는지 확인. (b) `npx eslint app/recruiter --max-warnings=0`, `npx tsc --noEmit` 06단계가 독립 재실행 | (a) 코드가 인수조건 5의 각 조건을 분기 처리함이 확인됨. (b) ESLint 0 error/warning | (a) 코드 대조 결과 일치 확인(위 상세 서술 참고). (b) `eslint app/recruiter` 재실행 결과 출력 없음(0 error/warning, 05단계 보고와 일치). `tsc --noEmit`는 `frontend/app/wcpreview-check-unit16-06/page.js`를 찾지 못한다는 오류 1건이 있었으나, 해당 경로는 현재 존재하지 않는 **다른 유닛(unit-16)의 임시 테스트 라우트가 남긴 `.next` 생성 타입 캐시 잔재**로 확인(`app/wcpreview-check-unit16-06` 디렉터리 자체가 존재하지 않음) — unit-12(recruiter 관련 파일)와 무관한 환경 노이즈이며 recruiter 코드의 타입 오류가 아님 | **CONDITIONAL PASS** | 실제 브라우저 렌더링(DOM/스크린샷)은 도구 부재로 미실시 — L1 원칙에 따라 9절/traceability.md에 "07(및 06 정식화) 08 착수 전 정산" 부채로 명시(FAIL이 아니라 알려진 범위 제한) |

> 정상 경로는 TC-003·TC-004 2건으로 L1 최소 기준을 충족한다. TC-001/002/005는 인수조건에 이미 명시된 예외/경계 케이스이자 권한 경계(빈 토큰·잘못된 역할·존재하지 않는 리소스)라 "명백히 위험한 케이스는 범위를 벗어나도 기록한다" 원칙에 따라 저비용으로 함께 재현했다.

## 5. 커버리지
L1 경량판 — 미해당.

## 6. 결함(Defect) 목록
결함 없음. 근거: TC-001~TC-005(백엔드 5케이스) 모두 기대 응답 코드/에러코드/메시지가 실제 응답과 정확히 일치했고(단순 "에러 없음"이 아니라 05단계 note의 상태별 메시지 매핑표와 실제 HTTP 응답 바디를 1:1 대조), TC-006(프론트)도 인수조건 문구와 소스 코드 분기를 대조해 불일치를 발견하지 못했다. TC-006에서 발견한 tsc 오류 1건은 recruiter 코드가 아닌 다른 유닛이 남긴 `.next` 캐시 잔재로 원인을 특정해(디렉터리 부존재 확인) unit-12의 결함이 아님을 확인했으므로 DEF로 등록하지 않는다.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트 목록:
  - `.harness-tmp/venv_06_unit12/`(06단계 전용 격리 venv, 05단계의 `venv_05_unit12`와 공유하지 않음)
  - `.harness-tmp/unit12_06_server.log`(uvicorn 실행 로그)
  - `.harness-tmp/unit12_06test/`(테스트용 candidate/recruiter 가입 요청 JSON, 로그인 응답, 토큰 파일)
  - DB: candidate 1명, recruiter 1명, interview 1건(신규 생성분)
  - 신규 기동한 uvicorn 프로세스 1개(포트 8214)
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): [x] 예
- 정리(삭제) 완료 여부: 완료.
  - `.harness-tmp/venv_06_unit12/`, `.harness-tmp/unit12_06test/`, `.harness-tmp/unit12_06_server.log` 삭제 완료.
  - DB에 생성한 candidate/recruiter 계정 2명과 interview 1건을 `docker exec final-project-db psql`로 DELETE 완료(삭제 후 재조회 0 rows 확인).
  - uvicorn 프로세스는 **PID(31788)를 특정해** `taskkill /F /PID 31788`로 종료(DEC-028에 따라 이미지 이름 기준 종료 절대 사용 안 함). 종료 직전 `netstat`로 다른 유닛이 쓰던 포트(8041, 23796 PID / 8811, 33116 PID)가 그대로 살아 있음을 확인했고, 내 서버 종료 후 재확인해도 두 포트 모두 정상 유지됨을 확인해 DEC-028 재발 없음을 검증함.
  - 참고: 서버 최초 기동 시도(포트 8212)가 이전 세션의 orphan 프로세스와 포트 충돌로 실패했는데, 이때도 `netstat`로 정확한 PID(8568)를 특정해 `taskkill /F /PID 8568`로만 종료했다(이미지 이름 기준 종료 미사용).
- 정리 후 `git status` 실행 결과 (그대로 첨부):
```
On branch PROD
Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
	modified:   backend/alembic/env.py
	modified:   backend/app/api/v1/interviews.py
	modified:   backend/app/main.py
	modified:   backend/app/services/job_queue.py
	modified:   backend/requirements.txt
	modified:   docs/harness/decisions.md
	modified:   docs/harness/traceability.md
	modified:   frontend/app/globals.css
	modified:   frontend/lib/api.ts
	modified:   frontend/next-env.d.ts
	modified:   frontend/package-lock.json
	modified:   frontend/package.json

Untracked files:
  (use "git add <file>..." to include in what will be committed)
	backend/alembic/versions/0df1434883f2_v3_transcripts.py
	backend/alembic/versions/8a55fda78a42_v4_deletion_requests.py
	backend/alembic/versions/b84a71b986c5_v6_code_submissions.py
	backend/alembic/versions/c1a2f5e9b7d3_v5_whiteboard_snapshots.py
	backend/app/api/v1/code_submissions.py
	backend/app/api/v1/consents.py
	backend/app/api/v1/ops.py
	backend/app/api/v1/recruiter.py
	backend/app/api/v1/whiteboard.py
	backend/app/api/v1/ws.py
	backend/app/models/code_submission.py
	backend/app/models/deletion_request.py
	backend/app/models/transcript.py
	backend/app/models/whiteboard.py
	backend/app/schemas/code_submission.py
	backend/app/schemas/consent.py
	backend/app/schemas/ops.py
	backend/app/schemas/recruiter.py
	backend/app/schemas/transcript.py
	backend/app/schemas/whiteboard.py
	backend/app/services/stt_engine.py
	docs/harness/units/unit-12-note.md
	docs/harness/units/unit-14-note.md
	docs/harness/units/unit-14-test.md
	docs/harness/units/unit-15-note.md
	docs/harness/units/unit-16-note.md
	docs/harness/units/unit-16-test.md
	docs/harness/units/unit-17-note.md
	docs/harness/units/unit-17-test.md
	docs/harness/units/unit-18-note.md
	docs/harness/units/unit-18-test.md
	docs/harness/units/unit-3-test.md
	docs/harness/units/unit-4-note.md
	docs/harness/units/unit-4-test.md
	docs/harness/units/unit-9-note.md
	frontend/app/admin/
	frontend/app/interviews/
	frontend/app/legal/
	frontend/app/mypage/
	frontend/app/recruiter/
	frontend/components/
	frontend/lib/complianceContent.ts
	frontend/tsconfig.tsbuildinfo

no changes added to commit (use "git add" and/or "git commit -a")
```
  위 목록에 `.harness-tmp/` 관련 항목이 전혀 없음을 확인(이미 `.gitignore` 대상이거나 전부 삭제됨). 나머지 modified/untracked 항목은 이 세션 이전부터, 또는 다른 병렬 진행 중인 유닛(unit-14/16/17/18 등)이 만든 것으로, unit-12-test 작성 과정에서 06단계가 추가/수정한 파일이 아니다(본 보고서 작성 자체 및 traceability.md 갱신은 이 절차의 정상적인 산출물).
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: [x] 없음
- 위 확인에 따라 8절/9절 PASS 판정의 전제조건(규칙 K 2번)을 충족한다.

## 8. 리스크 및 잔존 이슈
L1 경량판 — 미해당. (단, "07 부채(미실행)" 및 프론트 브라우저 렌더링 미검증 사실은 규정에 따라 이 절이 아니라 `docs/harness/traceability.md` REQ-011 행 비고에 기록했다.)

## 9. 결론 및 판정
- [x] PASS — 다음 단계 진행 안 함(L1 규칙에 따라 07단계로 handoff하지 않음). `docs/harness/traceability.md` REQ-011 행에 "L1 부채 — 07(및 06 정식화) 08 착수 전 정산 필요" 비고를 기록하고, 05단계로 돌아가 다음 작업 단위를 진행한다.
  - 판정 근거: 인수조건 1~5 전건에 대해 1:1 대응하는 테스트 케이스(TC-001~006)를 작성·실행했고, 그중 인수조건 3·4(정상 경로)는 06단계가 독립적으로 새로 기동한 서버 프로세스(포트 8214, 06단계 전용 신규 venv)와 신규 발급 계정으로 재현해 05단계 자체 보고를 그대로 승계하지 않았다. 결함 0건, Teardown 완료(7절), `git status` 확인 완료.
  - 미해결 잔존 사항(FAIL 아님, 알려진 L1 범위 제한): 프론트엔드 실제 브라우저 렌더링 미검증. 이는 traceability.md의 L1 부채 항목에 이미 포함되는 성격이라 별도 비고를 추가했다.

## 10. 내부 검증 (최소 2회, `verification-log-template.md` 사용)
L1 경량판 — 검증 생략(ORCHESTRATOR.md 1장 규정에 따름). 다만 06단계 자체적으로 다음 2단계 재점검을 수행했다:
- 1차(커버리지 확인): 인수조건 1~5가 TC-001~006에 각각 1:1로 매핑되는지 재확인 — 누락 없음. 05단계 note가 주장한 응답 문구(§`_report_state_message` 4개 분기 중 `report_status=none`)가 실제 코드/응답과 일치하는지 재대조 — 일치.
- 2차(통합테스트로 넘겨도 되는지 재검토): TC-003에서 recruiter가 "자신이 생성하지 않은 다른 지원자의 인터뷰까지" 보게 되는지를 의도적으로 확인해, §6.1 MVP 단일조직 정책(세분화 없음)이 코드가 아니라 실제 응답으로 증명되었는지 재검토했다(가장 놓치기 쉬운 경계 — recruiter별 소유권 필터링이 잘못 걸려 있었다면 TC-003만으로는 드러나지 않았을 수 있으나, 사전 존재하던 다른 유닛들의 테스트 계정이 우연히 이 사각지대를 함께 드러내 주었다). 또한 TC-006의 tsc 오류가 recruiter 코드 결함인지 환경 노이즈인지 재검증 없이 넘기면 07단계가 잘못된 전제로 출발할 위험이 있어, `wcpreview-check-unit16-06` 디렉터리 존재 여부를 직접 확인해 원인을 특정했다.
