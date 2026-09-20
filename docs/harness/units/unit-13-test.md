# 테스트 결과서 (Test Result Report) — unit-13 (Feature F. 채용담당자 대시보드, REQ-014)

## 1. 개요
- 테스트 대상: unit-13 — 백엔드 `backend/app/models/rubric_template.py`, `backend/app/schemas/rubric_template.py`, `backend/app/api/v1/recruiter.py`에 추가된 `GET/POST /recruiter/rubric-templates`, `PATCH /recruiter/rubric-templates/{id}`, Alembic `d3f7a2c9e1b4_v7_rubric_templates`, 프론트엔드 `frontend/app/recruiter/rubric-templates/page.tsx`([R-03])
- 테스트 유형: 단위
- 적용 Tier: High(DEC-002) — 단, 이 feature(F)는 오케스트레이터가 Speed Track **L1**로 지정, ORCHESTRATOR.md 1장 규정에 따라 06단계는 경량판으로 작성한다.
- 적용 속도 트랙: L1 — 정상 경로 1~2케이스 중심 경량판. 5·8·10절은 "L1 경량판 — 미해당/생략"으로 명시.
- 테스트 목적: 05단계(`docs/harness/units/unit-13-note.md`)가 자체 보고한 게이트1/2 통과 및 curl 검증 결과를, 06단계가 **독립적으로(별도 신규 서버 프로세스, 별도 격리 venv, 별도 신규 계정)** 재현해 실측 근거로 확인한다. 5단계 자체 보고를 그대로 승계하지 않는다.
- 관련 산출물: `docs/harness/03-system-design.md` §3.1(RUBRIC_TEMPLATES)/§4.2(`/recruiter/rubric-templates`)/§6.1(RBAC), `docs/harness/04-ux-design.md` [R-03], `docs/harness/units/unit-13-note.md`(인수조건 §5), `docs/harness/traceability.md` REQ-014 행
- 테스트 수행자(에이전트): 06-unit-tester
- 테스트 일시: 2026-09-19

## 2. 테스트 범위 및 제외 범위
- 범위 (In-Scope):
  - unit-13-note.md §5의 인수조건 1~7(백엔드)을 06단계가 신규로 기동한 독립 서버(포트 8299)와 신규 발급 계정(recruiter1/recruiter2/candidate1)으로 직접 curl 재현.
  - 인수조건 8(프론트엔드)은 소스 코드를 인수조건 문구와 1:1 대조 + 06단계가 독립 재실행한 `npx eslint`/`npx tsc --noEmit`으로 확인(브라우저 자동화 도구 부재로 실제 렌더링은 제외).
  - 05단계가 주장한 게이트1(ruff)을 06단계가 독립 재실행해 확인.
- 제외 범위 및 사유:
  - 실제 브라우저 렌더링(DOM/스크린샷) — 이 환경에 브라우저 자동화 도구가 없어 05단계와 동일한 한계(unit-13-note.md §4). L1 원칙상 "07(및 06 정식화) 08 착수 전 정산" 항목으로 traceability.md에 명시.
  - `weight` 합계(100) 검증, 시스템 기본 템플릿 시드 데이터 생성, `/recruiter/questions` — unit-13-note.md §2/§4에서 이미 설계서 대비 편차/후속 인수인계로 명시된 범위 밖 항목이며 인수조건에도 없음.
  - 부하/동시성 테스트 — L1 경량판 및 인수조건에 해당 항목 없음.
- 위험 감지에 따른 범위 외 추가 케이스: (1) `criteria` 빈 배열, (2) `weight` 범위초과(150), (3) `name` 빈 문자열 — 세 건 모두 인수조건에 명시되어 있지 않으나, 05단계 note §7이 "Pydantic Field 제약으로 서버 측 검증"을 주장한 부분을 06단계가 저비용으로 직접 재현해 검증했다(아래 4절 참고).

## 3. 테스트 환경
- 실행 환경: Windows 11, Python 3.12(신규 격리 venv `.harness-tmp/venv_06_unit13`), PostgreSQL 16(Docker `final-project-db`, 포트 5544, 기존 컨테이너 재사용 — `alembic current`로 head(`d3f7a2c9e1b4`) 확인, 스키마 변경 없음), FastAPI/uvicorn(포트 8299, 06단계가 신규로 기동한 독립 프로세스, PID 18928), Node.js(기존 `frontend/node_modules` 재사용, ESLint/tsc만 재실행)
- 테스트 데이터: 06단계가 이번 세션에서 신규 발급한 recruiter 2명(`u13r1_<ts>@test.com`, `u13r2_<ts>@test.com`), candidate 1명(`u13c1_<ts>@test.com`), recruiter1이 생성한 rubric_template 1건("백엔드 신입 평가", 한글 페이로드로 라운드트립 검증).
- 전제 조건: 05단계 산출물(코드)이 그대로 존재하고 수정되지 않은 상태. `.harness-tmp/venv_05_unit13`는 05단계 소유 리소스이므로 06단계는 이를 재사용하지 않고 별도의 `.harness-tmp/venv_06_unit13`을 생성해 완전히 격리했다(규칙 K, DEC-027 준수). 세션 시작 시 `.harness-tmp/`를 확인해 이전 06 실행이 남긴 잔여물이 없음을 확인했다(강제 중단 이력 없음).

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-001 | 인증 토큰 없이 목록 조회 (인수조건 1) | 서버 기동 완료 | `curl GET /api/v1/recruiter/rubric-templates` (Authorization 헤더 없음) | `401` | `401`, `{"code":"AUTH_INVALID_TOKEN","detail":"인증 토큰이 필요합니다."}` | PASS | |
| TC-002a | candidate 토큰으로 GET (인수조건 2) | candidate 계정 신규 가입+로그인 완료 | candidate 토큰으로 `GET /recruiter/rubric-templates` | `403 AUTH_FORBIDDEN` | `403`, `{"code":"AUTH_FORBIDDEN","detail":"채용담당자(recruiter)만 접근할 수 있습니다."}` | PASS | |
| TC-002b | candidate 토큰으로 POST (인수조건 2) | 상동 | candidate 토큰으로 `POST /recruiter/rubric-templates`(정상 페이로드) | `403 AUTH_FORBIDDEN` | `403`, 동일 코드/메시지 | PASS | |
| TC-003 | recruiter1 토큰으로 신규 템플릿 생성 — **정상 경로 1** (인수조건 3) | recruiter1 계정 신규 가입+로그인 완료 | recruiter1 토큰으로 `POST /recruiter/rubric-templates` `{"name":"백엔드 신입 평가","criteria":[{"name":"문제해결력","weight":40,"description":"알고리즘/설계 역량"},{"name":"커뮤니케이션","weight":30,"description":"의사소통"}]}` | `201`, `recruiter_id`가 recruiter1의 id로 채워진 객체 반환 | `201`, `recruiter_id="bc61b102-..."`가 회원가입 응답에서 확인한 recruiter1의 id와 정확히 일치. 한글 `name`/`criteria` 필드도 요청값과 바이트 단위로 동일하게 반환됨 | PASS | |
| TC-004 | recruiter1 토큰으로 목록 재조회 — **정상 경로 2** (인수조건 4) | TC-003 완료 | recruiter1 토큰으로 `GET /recruiter/rubric-templates` | `200`, 방금 만든 템플릿이 목록에 포함 | `200`, 배열 1건(count=1) 반환, id가 TC-003의 생성 id와 일치(Python으로 직접 비교 확인) | PASS | 시스템 기본 템플릿이 0건이라 목록에 recruiter1 소유 템플릿 1건만 존재 — unit-13-note.md §2/§4가 밝힌 "시드 데이터 부재"와 일치하는 실측 |
| TC-005 | recruiter1 토큰으로 본인 템플릿 PATCH (인수조건 5) | TC-003 완료 | recruiter1 토큰으로 `PATCH /recruiter/rubric-templates/{id}` `{"name":"백엔드 신입 평가(개정)","criteria":[{"name":"문제해결력","weight":50,"description":"알고리즘/설계 역량 강화"}]}` | `200`, 갱신된 name/criteria 반환 | `200`, `name="백엔드 신입 평가(개정)"`, `criteria`가 weight 50/설명 변경분 그대로 반영 | PASS | |
| TC-006 | recruiter2 토큰으로 recruiter1의 템플릿 PATCH 시도 (인수조건 6 전반) | recruiter2 계정 신규 가입+로그인 완료, TC-005의 template id 확보 | recruiter2 토큰으로 `PATCH /recruiter/rubric-templates/{recruiter1의 id}` | `403 AUTH_FORBIDDEN` | `403`, `{"code":"AUTH_FORBIDDEN","detail":"본인이 만든 템플릿만 수정할 수 있습니다..."}` | PASS | |
| TC-006b | recruiter2 토큰으로 목록 조회 시 recruiter1 템플릿 비노출 (인수조건 6 후반, 개인소유 원칙) | 상동 | recruiter2 토큰으로 `GET /recruiter/rubric-templates` | `200`, 빈 배열(recruiter1의 템플릿 미노출) | `200 []` | PASS | 소유권 격리가 실측으로 확인됨(설계서 §3.1 ERD 주석과 일치) |
| TC-007 | 존재하지 않는 UUID로 PATCH (인수조건 7, 경계값) | 없음(임의 미존재 UUID `00000000-0000-0000-0000-000000000000`) | recruiter1 토큰으로 `PATCH /recruiter/rubric-templates/{미존재-uuid}` | `404 NOT_FOUND` | `404`, `{"code":"NOT_FOUND","detail":"템플릿을 찾을 수 없습니다."}` | PASS | |
| TC-008 | 프론트엔드 `/recruiter/rubric-templates` 코드 레벨 검증 + 정적분석 (인수조건 8) | 없음 | (a) `page.tsx` 소스를 인수조건 8 문구와 1:1 대조 — `user.role !== "recruiter"`일 때 "권한이 없습니다" 렌더링 후 `reload()`(API 호출)를 호출하는 `useEffect`가 role 가드로 실행되지 않음을 확인, recruiter일 때 목록/빈 상태 문구+편집 폼 렌더링 분기 확인. `frontend/app/recruiter/page.tsx`에 "질문지/루브릭 관리" 링크 존재 확인. (b) 06단계가 `npx eslint app/recruiter lib/api.ts --max-warnings=0`, `npx tsc --noEmit` 독립 재실행 | (a) 코드가 인수조건 8의 각 조건을 분기 처리함이 확인됨. (b) 둘 다 오류/경고 0건 | (a) 코드 대조 결과 일치 확인(위 상세 서술 참고, `page.tsx` L164-178 role 가드, L76-80 useEffect가 role 가드 이후에만 `reload()` 호출하는 구조 재확인). (b) ESLint 0 error/warning, `tsc --noEmit` 0 error(unit-12-test.md가 보고한 `.next` 캐시 노이즈도 이번 실행에서는 재현되지 않음, 환경 정리됨) | PASS(코드/정적분석 한정) | 실제 브라우저 렌더링(DOM/상호작용)은 도구 부재로 미실시 — L1 원칙에 따라 traceability.md에 부채로 명시(9절 참고) |
| TC-EX1 | 위험 케이스: `criteria` 빈 배열 (범위 외 추가) | recruiter1 로그인 완료 | recruiter1 토큰으로 `POST /recruiter/rubric-templates` `{"name":"빈기준","criteria":[]}` | `422`, criteria 최소개수(1) 위반 | `422`, `code=VALIDATION_ERROR`, `criteria` 필드 `min_length` 위반 메시지 | PASS | note §7 "criteria 1~20개 Pydantic 검증" 주장을 실측 확인 |
| TC-EX2 | 위험 케이스: `weight` 범위초과(150) (범위 외 추가) | 상동 | `POST` `{"name":"가중치초과","criteria":[{"name":"x","weight":150,"description":""}]}` | `422`, weight `le=100` 위반 | `422`, `code=VALIDATION_ERROR`, `weight` 필드 `less_than_equal(100)` 위반 메시지 | PASS | |
| TC-EX3 | 위험 케이스: `name` 빈 문자열 (범위 외 추가) | 상동 | `POST` `{"name":"","criteria":[{"name":"x","weight":10,"description":""}]}` | `422`, name 최소길이(1) 위반 | `422`, `code=VALIDATION_ERROR`, `name` 필드 `string_too_short` 위반 메시지 | PASS | |

> 정상 경로는 TC-003·TC-004·TC-005 3건(L1 최소 기준인 1~2건을 초과해 확보 — 생성/조회/수정의 최소 CRUD 흐름 전체가 정상 경로 성격이라 판단해 포함)으로 L1 최소 기준을 충족한다. TC-001/002/006/006b/007은 인수조건에 이미 명시된 예외/경계/권한 케이스라 함께 재현했다. TC-EX1~3은 인수조건에는 없으나 05단계 note가 "서버 측 검증이 최종 방어선"이라 주장한 부분을 저비용으로 직접 확인해 신뢰도를 높였다.

## 5. 커버리지
L1 경량판 — 미해당.

## 6. 결함(Defect) 목록
결함 없음. 근거: TC-001~TC-007(백엔드 7케이스, 인수조건 1~7 전건 1:1 대응) 모두 기대 HTTP 상태코드/에러코드/메시지/응답 필드값(recruiter_id, name, criteria)이 실제 응답과 정확히 일치했다(단순 "에러 없음"이 아니라 회원가입 응답에서 확보한 실제 UUID와 API 응답의 recruiter_id를 직접 대조, 한글 페이로드 라운드트립을 바이트 단위로 확인). TC-008(프론트)은 인수조건 문구와 소스 코드 분기를 대조해 불일치를 발견하지 못했고, ESLint/tsc 모두 독립 재실행에서 0 error/warning이었다. TC-EX1~3(범위 외 위험 케이스)도 모두 예상한 422 검증 오류로 정확히 매핑되어 결함을 발견하지 못했다.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트 목록:
  - `.harness-tmp/venv_06_unit13/`(06단계 전용 격리 venv, 05단계의 `venv_05_unit13`와 공유하지 않음, DEC-027)
  - `.harness-tmp/unit13_06_server.log`(uvicorn 실행 로그)
  - `.harness-tmp/unit13_06test/`(테스트용 recruiter1/recruiter2/candidate1 가입·로그인 요청/응답 JSON, 토큰 파일, curl 응답 캡처 파일)
  - DB: recruiter 2명, candidate 1명, rubric_template 1건(신규 생성분)
  - 신규 기동한 uvicorn 프로세스 1개(포트 8299, PID 18928)
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): [x] 예
- 정리(삭제) 완료 여부: 완료.
  - `.harness-tmp/venv_06_unit13/`, `.harness-tmp/unit13_06test/`, `.harness-tmp/unit13_06_server.log` 삭제 완료(삭제 후 `ls .harness-tmp/`로 재확인, 남은 항목은 모두 다른 유닛/단계 소유).
  - DB에 생성한 recruiter 2명/candidate 1명 계정과 rubric_template 1건을 `docker exec final-project-db psql`로 DELETE 완료(삭제 후 `SELECT count(*)` 재조회 모두 0 확인).
  - uvicorn 프로세스는 기동 시 로그로 확인한 **정확한 PID(18928)만** `taskkill //F //PID 18928`로 종료(DEC-028 준수, 이미지 이름 기준 종료 미사용). 종료 후 `netstat`로 포트 8299에 LISTENING 항목이 없음(TIME_WAIT 잔여 연결만 존재, 정상), 다른 병렬 유닛 소유로 추정되는 python.exe 프로세스(PID 23796)가 종료 전후 그대로 살아있음을 `tasklist`로 확인해 DEC-028 재발 없음을 검증함.
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
	backend/alembic/versions/d3f7a2c9e1b4_v7_rubric_templates.py
	backend/app/api/v1/code_submissions.py
	backend/app/api/v1/consents.py
	backend/app/api/v1/ops.py
	backend/app/api/v1/recruiter.py
	backend/app/api/v1/whiteboard.py
	backend/app/api/v1/ws.py
	backend/app/models/code_submission.py
	backend/app/models/deletion_request.py
	backend/app/models/rubric_template.py
	backend/app/models/transcript.py
	backend/app/models/whiteboard.py
	backend/app/schemas/code_submission.py
	backend/app/schemas/consent.py
	backend/app/schemas/ops.py
	backend/app/schemas/recruiter.py
	backend/app/schemas/rubric_template.py
	backend/app/schemas/transcript.py
	backend/app/schemas/whiteboard.py
	backend/app/services/stt_engine.py
	docs/harness/units/unit-12-note.md
	docs/harness/units/unit-12-test.md
	docs/harness/units/unit-13-note.md
	docs/harness/units/unit-14-note.md
	docs/harness/units/unit-14-test.md
	docs/harness/units/unit-15-note.md
	docs/harness/units/unit-15-test.md
	docs/harness/units/unit-16-note.md
	docs/harness/units/unit-16-test.md
	docs/harness/units/unit-17-note.md
	docs/harness/units/unit-17-test.md
	docs/harness/units/unit-18-note.md
	docs/harness/units/unit-18-test.md
	docs/harness/units/unit-3-test.md
	docs/harness/units/unit-4-note.md
	docs/harness/units/unit-4-test.md
	docs/harness/units/unit-5-note.md
	docs/harness/units/unit-5-test.md
	docs/harness/units/unit-9-note.md
	docs/harness/units/unit-9-test.md
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
  위 목록에 `.harness-tmp/` 관련 항목이 전혀 없음을 확인. `docs/harness/units/unit-13-test.md`(이번 산출물)는 git status에는 아직 미표시 상태로 캡처됐으나(파일 작성 직전 시점 캡처), 이는 이번 절차의 정상적인 산출물이다. 나머지 modified/untracked 항목은 이 세션 이전부터, 또는 다른 병렬 진행 중인 유닛이 만든 것으로 unit-13-test 작성 과정에서 06단계가 추가/수정한 파일이 아니다.
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: [x] 없음
- 위 확인에 따라 8절/9절 PASS 판정의 전제조건(규칙 K 2번)을 충족한다.

## 8. 리스크 및 잔존 이슈
L1 경량판 — 미해당. (단, "07 부채(미실행)" 및 프론트 브라우저 렌더링 미검증 사실은 규정에 따라 이 절이 아니라 `docs/harness/traceability.md` REQ-014 행 비고에 기록했다.)

## 9. 결론 및 판정
- [x] PASS — 다음 단계 진행 안 함(L1 규칙에 따라 07단계로 handoff하지 않음). `docs/harness/traceability.md` REQ-014 행에 "L1 부채 — 07(및 06 정식화) 08 착수 전 정산 필요" 비고를 기록하고, 05단계로 돌아가 다음 작업 단위를 진행한다.
  - 판정 근거: 인수조건 1~8 전건에 대해 1:1 대응하는 테스트 케이스(TC-001~008)를 작성·실행했고, 그중 인수조건 3·4·5(정상 경로: 생성/조회/수정)는 06단계가 독립적으로 새로 기동한 서버 프로세스(포트 8299, 06단계 전용 신규 venv)와 신규 발급 계정(recruiter1/recruiter2/candidate1)으로 재현해 05단계 자체 보고를 그대로 승계하지 않았다. 범위 외 위험 케이스(TC-EX1~3, 422 검증)도 추가로 확인했다. 결함 0건, Teardown 완료(7절), `git status` 확인 완료.
  - 게이트 확인: 05단계가 note §6에서 주장한 ruff/eslint/tsc 통과를 06단계가 독립 재실행으로 재확인(모두 0 error/warning) — 5단계로 되돌릴 사유 없음.
  - 미해결 잔존 사항(FAIL 아님, 알려진 L1 범위 제한): 프론트엔드 실제 브라우저 렌더링 미검증. `weight` 합계(100) 검증 부재, 시스템 기본 템플릿 시드 데이터 부재는 unit-13-note.md가 이미 밝힌 설계 범위이며 이번 06단계에서도 재확인했다.

## 10. 내부 검증 (최소 2회, `verification-log-template.md` 사용)
L1 경량판 — 검증 생략(ORCHESTRATOR.md 1장 규정에 따름). 다만 06단계 자체적으로 다음 2단계 재점검을 수행했다:
- 1차(커버리지 확인): 인수조건 1~8이 TC-001~008에 각각 1:1로 매핑되는지 재확인 — 누락 없음. 05단계 note가 주장한 응답 필드(recruiter_id, is_system_default, criteria 라운드트립)가 실제 코드/응답과 일치하는지 재대조 — 일치. 05단계 note §6/§7이 주장한 정적분석 게이트 통과 여부도 06단계가 독립 재실행으로 재확인(승계가 아니라 재현) — 확인됨.
- 2차(통합테스트로 넘겨도 되는지, 즉 07 부채로 안전하게 보류해도 되는지 재검토): TC-006/TC-006b에서 recruiter2가 recruiter1의 템플릿을 PATCH하지 못하고 목록에서도 보이지 않는지를 의도적으로 두 각도(수정 시도 차단 + 목록 비노출)로 함께 확인해, "개인 소유" 원칙(unit-13-note.md §2 목록 조회 소유권 해석)이 코드가 아니라 실제 응답으로 증명되었는지 재검토했다(가장 놓치기 쉬운 경계 — 소유권 필터링이 목록에만 걸리고 PATCH 권한 체크가 빠져 있었다면 TC-006b만으로는 드러나지 않았을 수 있고, 반대로 PATCH만 막고 목록에 노출됐다면 TC-006만으로는 드러나지 않았을 것). 또한 TC-EX1~3(422 검증)을 재검토해, 05단계 note가 "Pydantic Field 제약이 최종 방어선"이라 주장한 부분이 실제로 프론트 클라이언트 검증에만 의존하지 않고 서버에서도 독립적으로 걸리는지 확인했다(클라이언트 우회 시나리오에 대한 방어 확인).
