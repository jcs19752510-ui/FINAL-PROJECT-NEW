# 테스트 결과서 (Test Result Report) — unit-2 (REQ-002, Feature B. 면접 세션 관리)

> `templates/test-report-template.md` 사용. **속도 트랙 L1 경량판** — 5·8·10절은 미해당으로 명시, 07단계로 handoff하지 않음(ORCHESTRATOR.md 1장, `.claude/agents/06-unit-tester.md` L1 규칙). unit-1-test.md 선례를 따름.

## 1. 개요
- 테스트 대상: unit-2 — `backend/app/api/v1/interviews.py`(`POST /interviews`, `POST /interviews/{id}/start`, `POST /interviews/{id}/end`), `backend/app/models/interview.py`, `backend/app/models/consent.py` (REQ-002)
- 테스트 유형: 단위
- 적용 Tier: High (`docs/harness/decisions.md` 참고 — 프로젝트 전체 선언값). Tier=High과 무관하게 이 feature는 속도 트랙 L1로 진행되어 06단계는 경량판으로 수행함(두 축은 별개, ORCHESTRATOR.md 1장 도입부).
- 적용 속도 트랙: **L1 (DEC-003)**
- 테스트 목적: 5단계(`05-unit-developer`)가 방금 완료한 unit-2 구현이, unit-2-note.md §4의 정상 경로 인수조건 중 핵심 상태전이 흐름(세션 생성, 역할 게이트, 동의 게이트, start→live, end→completed)을 실제로 만족하는지 **06단계 자신이 독립적으로 새 서버 프로세스를 기동해 재현**하여 증명한다. 5단계 자체 검증 기록(unit-2-note.md §7, a~j 상당)은 참고만 하고 그대로 승계하지 않는다.
- 관련 산출물: `docs/harness/units/unit-2-note.md`, `docs/harness/03-system-design.md` §3(INTERVIEWS 상태머신)/§4.2(`/interviews` API)/§6.1(RBAC)/§6.2(DEC-023 동의 게이트), `docs/harness/04-ux-design.md` [C-03]~[C-06]/[C-09], `docs/harness/traceability.md` REQ-002
- 테스트 수행자(에이전트): `06-unit-tester`
- 테스트 일시: 2026-09-19 (KST)

## 2. 테스트 범위 및 제외 범위
- 범위 (In-Scope, L1 경량판 — 정상 경로 1~2케이스로 한정, 단 서로 강하게 결합된 인접 검증은 같은 TC 안에 포함):
  - TC-001: 인수조건 1·2 — candidate의 세션 생성 성공(201, scheduled/none) + recruiter의 생성 시도 차단(403 AUTH_FORBIDDEN, 수직 권한 게이트가 정상 동작해야 나머지 흐름의 전제가 성립하므로 생성 성공 케이스와 짝을 이루는 최소 확인으로 포함).
  - TC-002: 인수조건 3·4·7 — 동의 없는 상태에서 `/start` 차단(403 CONSENT_REQUIRED_NOTICE) → DB에 동의 INSERT → `/start` 재시도 성공(202, live) → `/end` 성공(202, completed, report_status=queued)까지 하나의 연속 정상 경로 플로우로 재현.
- 제외 범위 (Out-of-Scope) 및 사유:
  - 인수조건 5·6·8(중복 시작/종료 409, 수평 권한 상승 403), 9(토큰 없음 401, 존재하지 않는 id 404) — L1 규칙상 "정상 경로 1~2케이스"로 한정되며, unit-2-note.md §4·§7에 이미 05단계가 curl로 실행 확인한 기록(a~j)이 있어 06 범위에서 임의로 확장하지 않음. 단, 이 항목들은 **아직 06단계가 독립 재현하지 않은 상태**이므로 8절 상당 리스크로 traceability.md에 남긴다.
  - `GET /interviews`(목록 조회), `/resume`, `/report/regenerate`, WebSocket 기반 `turn_result`/`report_ready` 수신 — unit-2-note.md §1·§2-6·§3에서 이번 유닛 구현 범위 자체에서 명시적으로 제외되었으므로 테스트 대상도 아님.
  - `biometric_voice` 동의 검사 — DEC-023에 따라 `/start`가 절대 검사하지 않는 항목(unit-14/15 범위)이라 테스트 대상 아님.

## 3. 테스트 환경
- 실행 환경: Windows 11, PostgreSQL 16(Docker, `final-project-db` 컨테이너, 포트 5544, unit-2-note.md와 동일 컨테이너 재사용 — `alembic current` 재확인 결과 `fdd74cee7615 (head)` 리비전 적용 확인됨), Python venv `.harness-tmp/venv_05_unit1`(05단계가 만든 격리 venv를 06이 재사용 — unit-1-note.md/unit-2-note.md §3가 명시적으로 재사용을 허용), FastAPI 앱을 06단계가 직접 새 프로세스로 기동(포트 8021, uvicorn, PID 8744 — 05단계가 검증에 쓴 8020번 프로세스와 무관한 별도 기동으로 5단계 결과를 그대로 승계하지 않음).
- 테스트 데이터: 06단계가 이번에 새로 생성한 계정 2건 — `qa06u2_cand1_<ts>@example.com`(candidate), `qa06u2_rec1_<ts>@example.com`(recruiter). 신규 면접 세션 1건(candidate1 소유). `ai_interview_notice` 동의 레코드 1건은 unit-2-note.md §3 안내대로 `docker exec final-project-db psql -U final_app -d final_project`로 직접 INSERT(POST /consents API가 아직 없음, §2-2 편차).
- 전제 조건 (Preconditions): Docker Desktop 기동 상태, `final-project-db` 컨테이너 Up, `backend/.env` 존재(`DATABASE_URL=postgresql+psycopg://final_app:final_app_pw@localhost:5544/final_project`), 5단계 게이트1(린트)·게이트2(코드리뷰) 통과 확인됨 — unit-2-note.md §5(`ruff check app alembic/env.py` 에러 0건)·§6(코드리뷰 체크리스트 6항목 전부 [x]), 06단계는 이를 note에서 확인만 하고 재검증하지 않음(원칙에 따름).

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-001 | 세션 생성 정상 경로 + 역할 게이트 (인수조건 1·2) | candidate1/recruiter1 회원가입·로그인 완료, 각자 access token 보유 | ① `curl -X POST http://127.0.0.1:8021/api/v1/interviews -H "Authorization: Bearer <recruiter1_token>"` ② `curl -X POST http://127.0.0.1:8021/api/v1/interviews -H "Authorization: Bearer <candidate1_token>"` | ①: HTTP 403, `code=AUTH_FORBIDDEN` / ②: HTTP 201, `status=scheduled`, `report_status=none`, `candidate_id`가 candidate1의 id와 일치 | ①: HTTP 403, 바디 `{"type":"about:blank","title":"Forbidden","status":403,"detail":"지원자(candidate)만 면접 세션을 생성할 수 있습니다.","code":"AUTH_FORBIDDEN"}` — 예상과 일치 / ②: HTTP 201, 바디 `{"id":"81c0dfdb-5917-4025-b697-ec91f0581252","candidate_id":"e7f36a8f-2982-46b9-a27e-10f22fb5eeb6","recruiter_id":null,"rubric_template_id":null,"status":"scheduled","report_status":"none",...}` — candidate_id가 로그인한 candidate1(`e7f36a8f-...`)과 정확히 일치, status/report_status 예상값과 일치 | Pass | 06단계가 직접 재현. 05단계 기록 재사용 아님 |
| TC-002 | 동의 게이트 → 시작 → 종료 정상 경로 (인수조건 3·4·7) | TC-001에서 생성한 candidate1 소유 interview(`81c0dfdb-...`), 아직 동의 레코드 없음 | ① `curl -X POST .../interviews/{id}/start -H "Authorization: Bearer <candidate1_token>"`(동의 전) ② `docker exec final-project-db psql -U final_app -d final_project -c "INSERT INTO consents (id,user_id,consent_type,granted_at) VALUES (gen_random_uuid(),'<candidate1_id>','ai_interview_notice',now());"` ③ 동일 `/start` 재호출 ④ `curl -X POST .../interviews/{id}/end -H "Authorization: Bearer <candidate1_token>"` | ①: HTTP 403, `code=CONSENT_REQUIRED_NOTICE` / ②: INSERT 성공 / ③: HTTP 202, `job_id` 문자열 존재, `interview.status=live`, `interview.started_at` not null / ④: HTTP 202, `job_id` 존재, `interview.status=completed`, `interview.report_status=queued`, `interview.ended_at` not null | ①: HTTP 403, 바디 `{"...","detail":"AI 면접 진행/평가 사실에 대한 사전고지 동의가 필요합니다.","code":"CONSENT_REQUIRED_NOTICE"}` — 일치 / ②: `INSERT 0 1` — 성공 / ③: HTTP 202, 바디 `{"job_id":"bae09fd9-7a68-4d6a-a2f2-4a81e7365513","message":"AI가 첫 질문을 준비 중입니다","interview":{...,"status":"live","started_at":"2026-09-18T17:28:57.043372Z",...}}` — job_id 존재(uuid4 문자열), status=live, started_at not null 전부 일치 / ④: HTTP 202, 바디 `{"job_id":"9d81b6c7-933c-457b-b24e-82360b809d38","interview":{...,"status":"completed","report_status":"queued","ended_at":"2026-09-18T17:28:57.113410Z",...}}` — job_id 존재, status=completed, report_status=queued, ended_at not null 전부 일치 | Pass | 06단계가 직접 재현. 05단계 기록 재사용 아님. 동의 INSERT는 unit-2-note.md §3 안내를 그대로 따름(운영 경로 아님, 개발/테스트 전용) |

> L1 경량판(정상 경로 1~2케이스)이므로 경계값/예외 입력 케이스(중복 시작/종료, 수평 권한 상승, 인증 없음, 존재하지 않는 id)는 위 §2 제외범위에 사유와 함께 명시했다(5단계가 이미 실행한 기록은 있으나 06이 독립 재현하지 않았음을 traceability.md에 리스크로 기록).

## 5. 커버리지
L1 경량판 — 미해당.

## 6. 결함(Defect) 목록
결함 없음. 근거: TC-001·TC-002 각각 예상 결과(HTTP 상태 코드, 에러 코드, 응답 바디 필드값 — status/report_status/candidate_id/job_id/started_at/ended_at)를 사전에 정의하고, 실제 curl 및 psql 실행 결과와 필드 단위로 1:1 대조하여 전부 일치함을 확인했다("에러 없이 실행됨"이 아니라 필드 단위 비교로 PASS 판정). 동의 게이트 전/후 `/start` 응답이 각각 403→202로 정확히 전환되는 것과, `/end` 이후 `report_status=queued`로 전이되는 것까지 실제 값으로 확인했다.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트 목록:
  - `.harness-tmp/u2_email1.txt`, `.harness-tmp/u2_email2.txt`, `.harness-tmp/u2_token1.txt`, `.harness-tmp/u2_token2.txt`, `.harness-tmp/u2_cand1_id.txt`, `.harness-tmp/u2_interview_id.txt` (테스트 실행용 스크래치 파일)
  - `.harness-tmp/uvicorn_06_unit2.log` (06단계가 직접 기동한 서버 프로세스 로그, 포트 8021)
  - 재사용(신규 생성 아님): `.harness-tmp/venv_05_unit1` — 05단계가 만든 venv를 그대로 재사용(unit-2-note.md §3에서 재사용 허용 명시). 06단계가 신규로 만든 것이 아니므로 삭제 대상으로 삼지 않음(다음 단계도 재사용 가능한 공용 산출물).
  - 신규 생성한 DB 레코드: candidate1/recruiter1 계정 2건, interview 1건, consents 1건(모두 테스트 데이터, 재생성 가능) — `final-project-db` 컨테이너 자체는 다음 단위가 이어서 쓰므로 유지(unit-1-test.md와 동일 방침). 애플리케이션 데이터이므로 규칙K 정리 대상은 아니지만 참고를 위해 기록.
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): [x] 예
- 정리(삭제) 완료 여부: 완료. `u2_email1.txt`, `u2_email2.txt`, `u2_token1.txt`, `u2_token2.txt`, `u2_cand1_id.txt`, `u2_interview_id.txt`, `uvicorn_06_unit2.log` 전부 삭제함. 06단계가 기동한 uvicorn 프로세스(PID 8744, 포트 8021)는 정리 전 `Stop-Process -Force`로 종료 확인(종료 후 `curl`이 exit code 7/연결 거부로 응답, 서버 다운 확인).
- 정리 후 `git status` 실행 결과 (그대로 첨부):
```
On branch PROD
Changes not staged for commit:
  (use "git add/rm <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
	modified:   .gitignore
	deleted:    "00 파이널 프로젝트 계획서/AI_모의면접_프로젝트_전체흐름도.mermaid"
	modified:   docs/harness/01-trend-analysis.md
	modified:   docs/harness/decisions.md

Untracked files:
  (use "git add <file>..." to include in what will be committed)
	"00 파이널 프로젝트 계획서/AI_모의면접_프로젝트_전체흐름도.md"
	backend/
	docs/harness/02-planning.md
	docs/harness/03-system-design.md
	docs/harness/04-ux-design.md
	docs/harness/traceability.md
	docs/harness/units/
	docs/harness/verify-log_01-trend-analysis.md
	docs/harness/verify-log_02-planning.md
	docs/harness/verify-log_03-system-design.md
	docs/harness/verify-log_04-ux-design.md
	frontend/

no changes added to commit (use "git add" and/or "git commit -a")
```
  (이 세션 시작 시점의 git status 스냅샷과 동일 — `.harness-tmp/`는 `.gitignore`에 등록되어 있어 위 목록에 나타나지 않으며, 06단계 작업으로 인한 신규 추적대상 변경 없음. `docs/harness/units/`는 unit-2-test.md 신규 작성으로 이미 untracked 상태였던 디렉터리 그대로.)
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: [x] 없음
- **Teardown 완료 확인됨 — 9절 PASS 판정의 전제조건 충족.**

## 8. 리스크 및 잔존 이슈
L1 경량판 — 미해당(단, 아래 07 부채 사실은 규칙에 따라 이 절이 아니라 `docs/harness/traceability.md`에 기록함).

참고(경량판 범위 밖 정보, 판정에는 영향 없음): 인수조건 5·6·8·9(중복 시작/종료 409, 수평 권한 상승 403, 인증 없음 401, 존재하지 않는 id 404)와 `GET /interviews` 미구현 사실(unit-2-note.md §2-6)은 이번 06단계가 독립 재현하지 않았고, 5단계 자체 실행 기록(unit-2-note.md §7)만 존재하는 상태다. 이후 07(및 L1 06 정식화) 정산 시 06단계가 직접 재현해야 할 항목으로 traceability.md에 남긴다.

## 9. 결론 및 판정
- [x] PASS — 다음 단계(05단계로 복귀, 다음 작업단위 진행) 가능 (7절 Teardown 확인 완료됨)
- [ ] CONDITIONAL PASS
- [ ] FAIL

**L1 규칙에 따른 후속 처리**: 이 unit-2-test.md는 07단계로 handoff하지 않는다. 대신 `docs/harness/traceability.md` REQ-002 행의 "단위테스트" 컬럼과 비고란을 갱신하고, 05단계로 돌아가 다음 작업 단위를 진행한다.

## 10. 내부 검증 (최소 2회)
L1 경량판 — 검증 생략(ORCHESTRATOR.md 1장, 내부검증 규칙B 생략 가능 조항 적용).
