# 테스트 결과서 (Test Result Report) — unit-18 (REQ-016, Feature H. 부가 UX)

> `templates/test-report-template.md` 사용. **속도 트랙 L1 경량판** — 5·8·10절은 미해당으로 명시, 07단계로 handoff하지 않음(ORCHESTRATOR.md 1장, `.claude/agents/06-unit-tester.md` L1 규칙). unit-1/2/3-test.md 선례를 따름.

## 1. 개요
- 테스트 대상: unit-18 — `backend/app/api/v1/ops.py`(`GET /api/v1/ops/health`), `backend/app/schemas/ops.py`(`OpsHealthOut`), `frontend/app/admin/ops/page.tsx`([O-01] 운영자 모니터링 화면) (REQ-016)
- 테스트 유형: 단위
- 적용 Tier: **High**(오케스트레이터 지시 — Feature H 전체 Tier). Tier=High과 무관하게 이 feature는 속도 트랙 L1로 진행되어 06단계는 경량판으로 수행함(두 축은 별개, ORCHESTRATOR.md 1장 도입부). Tier=High이므로 06·07 병합 조건(Low 등급 전용) 자체가 성립하지 않는다 — 병합 대상 아님.
- 적용 속도 트랙: **L1 (DEC-003)**
- 테스트 목적: 5단계(`05-unit-developer`)가 방금 완료한 unit-18 구현이, unit-18-note.md §6의 정상 경로 인수조건 중 핵심 흐름(admin 인증/권한 게이트 통과 후 정상 응답, `active_sessions` 실측 반영)을 실제로 만족하는지 **06단계 자신이 독립적으로 새 서버 프로세스를 기동해 재현**하여 증명한다. 5단계 자체 검증 기록(unit-18-note.md §9)은 참고만 하고 그대로 승계하지 않는다.
- 관련 산출물: `docs/harness/units/unit-18-note.md`, `docs/harness/03-system-design.md` §4.2(`GET /ops/health`)/§7.2(Prometheus 지표: `queue_length`/`gpu_memory_used_bytes`/`error_rate`/`active_sessions`), `docs/harness/04-ux-design.md` [O-01] 운영자 모니터링 화면, `docs/harness/traceability.md` REQ-016
- 테스트 수행자(에이전트): `06-unit-tester`
- 테스트 일시: 2026-09-19 (KST)

## 2. 테스트 범위 및 제외 범위
- 범위 (In-Scope, L1 경량판 — 정상 경로 1~2케이스로 한정, 단 서로 강하게 결합된 인접 게이트 확인은 같은 TC 안에 포함):
  - TC-001: 인수조건 1·2·3 — 인증 토큰 없이 호출 시 `401`, `role=candidate` 토큰으로 호출 시 `403`, `role=admin` 토큰으로 호출 시 `200`과 4개 지표+`checked_at`+`notes`(4키) 스키마 확인. (401/403은 그 자체로 "정상 경로"는 아니지만, admin 200 응답이 실제로 역할 게이트를 통과한 결과임을 증명하는 데 필요한 최소 짝 확인으로 unit-3-test.md TC-001 선례와 동일하게 하나의 TC로 묶었다.)
  - TC-002: 인수조건 4 — candidate가 면접 세션을 생성→동의(`ai_interview_notice`)→`/start`로 `live` 전환한 뒤, admin이 `/ops/health`를 다시 호출하면 `active_sessions`가 **직전 호출 대비 정확히 1 증가**하는지 확인(절대값이 아니라 델타로 검증 — 아래 §3 "테스트 데이터" 참고, 공유 DB에 다른 병렬 작업단위가 남긴 live 세션이 존재해 절대값 0 가정이 위험하다는 것을 이번 실행에서 직접 확인했다).
- 제외 범위 (Out-of-Scope) 및 사유:
  - 인수조건 5(프론트엔드 `/admin/ops` 화면 — candidate/recruiter 접근 시 권한없음 안내, admin 접근 시 스켈레톤→카드 렌더링) — L1 규칙상 "정상 경로 1~2케이스"로 한정되며, 06단계 환경에 브라우저 자동화 도구(Playwright 등 MCP)가 연동되어 있지 않아 실제 화면 렌더링을 독립 재현할 수 없다(unit-18-note.md §6도 동일 사유로 05단계 자체 검증에서 브라우저 스크린샷까지는 확인하지 않았음을 명시함). 대신 코드 레벨로 `frontend/lib/api.ts`의 `OpsHealthOut` 타입·`getOpsHealth()` 호출부가 백엔드 `OpsHealthOut` 스키마(필드명·타입)와 1:1 일치함을 확인했고(§4 TC-003 참고), `npx tsc --noEmit`/`eslint`를 06단계가 직접 재실행해 타입/린트 오류가 없음을 재확인했다(§9 게이트 참고). 화면 실 렌더링 검증은 07 부채로 남긴다.
  - 큐/GPU/에러율 지표가 실측치로 바뀌는 시점 — unit-18-note.md §2·§5에 이미 명시된 대로 근거 시스템(Celery/Redis 큐, GPU Worker, Prometheus)이 코드베이스에 없어 이번 유닛의 정상 동작 범위 자체가 "항상 0"이다. 값이 0인 것 자체가 결함이 아님을 이번 06단계도 TC-001/TC-002 응답에서 직접 확인했다(아래 §4).
  - 존재하지 않는 리소스 조회, 동시성/부하 — 이 엔드포인트는 경로 파라미터가 없는 단일 GET이라 해당 없음(unit-18-note.md §8와 동일 판단).

## 3. 테스트 환경
- 실행 환경: Windows 11, PostgreSQL 16(Docker, `final-project-db` 컨테이너, 포트 5544, 기존 유닛들과 동일 컨테이너 재사용), Python venv `.harness-tmp/venv_05_unit1`(05단계가 만든 격리 venv를 06이 재사용 — unit-18-note.md §5가 재사용을 명시), FastAPI 앱을 06단계가 직접 새 프로세스로 기동(포트 8060, uvicorn — 05단계가 검증에 쓴 포트 8040과 무관한 별도 기동으로 5단계 결과를 그대로 승계하지 않음).
- 테스트 데이터: 06단계가 이번에 새로 생성한 계정 2건 — `u18cand_<ts>@test.com`(candidate), `u18admin_<ts>@test.com`(recruiter로 가입 후 `UPDATE users SET role='admin'`으로 DB에서 직접 승격 — unit-18-note.md §5 안내대로, admin 자가입 경로가 unit-1 범위에 없음). 신규 면접 세션 1건(candidate 소유), `ai_interview_notice` 동의 1건(unit-14가 이미 구현해 둔 `POST /consents` API 호출로 생성 — DB 직접 INSERT 아님, unit-2/3와 달리 unit-14 완료 후에는 API 경로가 존재함).
  - **중요 관찰**: 테스트 시작 시점에 이미 다른 병렬 작업단위가 만든 것으로 보이는 live 상태 interview 1건이 DB에 존재해 `active_sessions` 베이스라인이 0이 아니라 1이었다(`docker exec final-project-db psql ... "SELECT id, candidate_id, status FROM interviews WHERE status='live'"`로 확인, 해당 interview는 이번 유닛이 만든 것이 아니므로 삭제하지 않았음). 이 때문에 TC-002는 절대값(`active_sessions=1`)이 아니라 **직전 호출 대비 델타(+1)**로 검증 기준을 설계했다 — 절대값으로 검증했다면 공유 DB 상태에 따라 우연히 통과/실패가 갈리는 취약한 테스트가 될 뻔했다(2차 내부검증에서 재확인, §10 참고).
- 전제 조건 (Preconditions): Docker Desktop 기동 상태, `final-project-db` 컨테이너 Up, `backend/.env` 존재, 5단계 게이트1(린트)·게이트2(코드리뷰) 통과 확인 — unit-18-note.md §7(`ruff check` 에러 0건, `npm run lint`/`tsc --noEmit` 통과)·§8(코드리뷰 체크리스트 6항목 전부 [x])에서 확인했고, **06단계가 이를 note 확인에 그치지 않고 직접 재실행해 재확인함**(`ruff check app/api/v1/ops.py app/schemas/ops.py app/main.py` → All checks passed / `npx tsc --noEmit` → 에러 0건 / `npx eslint app/admin/ops/page.tsx lib/api.ts` → 위반 0건, §9 게이트).

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-001 | 인증/권한 게이트 + admin 정상 응답 스키마 (인수조건 1·2·3) | candidate 계정, admin 승격 계정 각각 회원가입·로그인 완료 | ① `curl http://127.0.0.1:8060/api/v1/ops/health`(토큰 없음) ② 동일 URL, `Authorization: Bearer <candidate_token>` ③ 동일 URL, `Authorization: Bearer <admin_token>` | ①: HTTP 401, `code=AUTH_INVALID_TOKEN` / ②: HTTP 403, `code=AUTH_FORBIDDEN` / ③: HTTP 200, 바디에 `queue_length=0`, `gpu_memory_used_bytes=0`, `error_rate=0.0`, `active_sessions`(정수), `checked_at`(ISO 문자열), `notes`(4개 키: queue_length/gpu_memory_used_bytes/error_rate/active_sessions 전부 존재) | ①: HTTP 401, 바디 `{"code":"AUTH_INVALID_TOKEN","detail":"인증 토큰이 필요합니다.","status":401}` — 일치 / ②: HTTP 403, 바디 `{"code":"AUTH_FORBIDDEN","detail":"관리자(admin)만 접근할 수 있습니다.","status":403}` — 일치 / ③: HTTP 200, 바디 `{"queue_length":0,"gpu_memory_used_bytes":0,"error_rate":0.0,"active_sessions":1,"checked_at":"2026-09-18T23:03:05.255107Z","notes":{"queue_length":"...","gpu_memory_used_bytes":"...","error_rate":"...","active_sessions":"INTERVIEWS.status='live' 실측값."}}` — 필드/타입/notes 4키 전부 일치 | Pass | 06단계가 직접 재현(포트 8060). 05단계 기록(unit-18-note.md §9, 포트 8040) 재사용 아님. `active_sessions=1`은 §3에 기록한 병렬 작업단위 잔여 live 세션 1건 때문 — 이 유닛의 결함이 아님(TC-002에서 델타로 재검증) |
| TC-002 | `active_sessions` 실측 반영 — 세션 생성→동의→start 후 델타 확인 (인수조건 4) | TC-001의 candidate 계정, `POST /interviews`로 세션 생성 완료(scheduled) | ① `curl -H "Authorization: Bearer <admin_token>" .../ops/health` (베이스라인, TC-001 ③ 결과 재사용 가능하나 델타 기준점으로 명시 기록) → `active_sessions=1` ② `curl -X POST .../consents -d '{"consent_type":"ai_interview_notice"}'`(candidate) ③ `curl -X POST .../interviews/{id}/start`(candidate) ④ `curl -H "Authorization: Bearer <admin_token>" .../ops/health` (재호출) | ④의 `active_sessions`가 ①보다 정확히 1 큰 값(=2)이어야 하고, `queue_length`/`gpu_memory_used_bytes`/`error_rate`는 여전히 0/0/0.0이어야 한다 | ②: HTTP 201, consent 생성 확인 / ③: HTTP 202, `interview.status="live"`, `started_at` not null 확인 / ④: HTTP 200, `active_sessions=2`(①의 1에서 정확히 +1) — 일치. `queue_length=0`, `gpu_memory_used_bytes=0`, `error_rate=0.0` 그대로 — 일치 | Pass | 06단계가 직접 재현. `INTERVIEWS.status='live'` COUNT가 실제 DB 상태 변화를 그대로 반영함을 실측으로 증명(하드코딩된 값이 아님) |
| TC-003 (참고, 코드 리뷰 — 실행형 테스트 아님) | 프론트-백엔드 타입 계약 일치 (인수조건 5의 부분 대체, §2 제외범위 참고) | 없음(정적 코드 대조) | `frontend/lib/api.ts`의 `OpsHealthOut` 인터페이스 필드명/타입을 `backend/app/schemas/ops.py`의 `OpsHealthOut` Pydantic 모델과 1:1 대조 | 필드명·타입(queue_length: number/int, gpu_memory_used_bytes: number/int, error_rate: number/float, active_sessions: number/int, checked_at: string/datetime, notes: Record<string,string>/dict[str,str])이 모두 일치해야 함 | 6개 필드 전부 이름·타입 일치 확인. `getOpsHealth()`가 `Authorization: Bearer <token>` 헤더로 `/ops/health`를 호출하는 것도 백엔드 `get_current_user`(Bearer 토큰 기대)와 일치 | Pass(코드 리뷰 근거) | 브라우저 렌더링(스켈레톤/에러배지/역할가드 화면)까지는 검증하지 못함 — §2 제외범위·§8 상당 리스크로 명시, 07 부채로 이관 |

> L1 경량판(정상 경로 1~2케이스 + 짝을 이루는 게이트 확인)이므로 그 외 경계값/예외 입력 케이스(예: 만료된 토큰, 잘못된 형식의 Authorization 헤더, DB 연결 장애 시 502 등)는 이번 유닛 인수조건에 없고 05단계도 다루지 않았다 — 임의 확장하지 않되, 위 §3에서 발견한 "공유 DB 베이스라인 비0" 관찰은 인수조건 범위 밖이라도 테스트 설계 자체의 안전성에 영향을 주는 위험 요소라 판단해 기록하고 대응(델타 검증으로 전환)했다.

## 5. 커버리지
L1 경량판 — 미해당.

## 6. 결함(Defect) 목록
결함 없음. 근거: TC-001~TC-002 각각 예상 결과(HTTP 상태 코드, 에러 코드, 응답 바디 필드값·타입·개수)를 사전에 정의하고, 실제 curl 실행 결과와 필드 단위로 1:1 대조하여 전부 일치함을 확인했다("에러 없이 실행됨"이 아니라 필드 단위 비교로 PASS 판정). 인증 없음(401)·권한 없음(403)·정상 admin 응답(200, 4개 지표+notes 4키)·`active_sessions`의 실측 델타 반영(+1)까지 전부 실제 값으로 확인했다. TC-003(코드 리뷰)에서도 프론트-백엔드 타입 계약 불일치를 발견하지 못했다.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트 목록:
  - `.harness-tmp/u18_cand_reg.json`, `u18_admin_reg.json`, `u18_cand_login.json`, `u18_admin_login.json`, `u18_cand_token.txt`, `u18_admin_token.txt`, `u18_cand_email.txt`, `u18_admin_email.txt`, `u18_interview_create.json`, `u18_interview_id.txt`, `u18_ops_baseline.json`, `u18_ops_after_start.json` (테스트 실행용 스크래치 파일)
  - `.harness-tmp/uvicorn_06_unit18.log` (06단계가 직접 기동한 서버 프로세스 로그, 포트 8060)
  - 재사용(신규 생성 아님): `.harness-tmp/venv_05_unit1` — 05단계가 만든 venv를 그대로 재사용(unit-18-note.md §5에서 재사용 허용 명시). 06단계가 신규로 만든 것이 아니므로 삭제 대상으로 삼지 않음.
  - 신규 생성한 DB 레코드: candidate/admin 계정 2건, interview 1건, consent 1건(모두 테스트 데이터, 재생성 가능) — `final-project-db` 컨테이너 자체는 다른 병렬 작업단위가 계속 쓰므로 유지.
  - **범위 외 발견물(이번 세션이 만든 것이 아님, 참고 기록)**: 정리 과정에서 `frontend/tsconfig.tsbuildinfo`(untracked, 06단계의 `npx tsc --noEmit` 실행 중 생성된 것으로 추정되는 빌드 캐시)를 발견해 규칙 K 취지에 따라 함께 삭제했다. `frontend/next-env.d.ts`(modified)와 `frontend/app/__wcpreview-check/`(untracked, 웹캠 프리뷰 관련 — REQ-015/unit-16으로 추정)는 이번 세션이 실행한 명령(curl/psql/ruff/tsc --noEmit/eslint)으로는 생성될 수 없는 산출물(`next dev`/`next build` 등을 이번 세션은 한 번도 실행하지 않음)이라 판단해, 다른 병렬 작업단위의 진행 중 산출물로 보고 삭제하지 않았다.
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): [x] 예
- 정리(삭제) 완료 여부: 완료. 위에 나열한 `.harness-tmp/u18_*` 스크래치 파일과 `uvicorn_06_unit18.log`을 전부 삭제함. 06단계가 기동한 uvicorn 프로세스(포트 8060)는 `taskkill /F /PID`로 종료 확인(종료 후 `curl`이 연결 실패, http_code=000으로 응답). DB에 생성한 candidate/admin 계정, interview, consent 레코드는 각각 `DELETE`로 정리 완료(`DELETE 1`/`DELETE 1`/`DELETE 2` 결과 확인, 이후 `SELECT count(*) FROM users WHERE email LIKE 'u18%'` → 0 재확인). `frontend/tsconfig.tsbuildinfo`도 삭제 완료.
- 정리 후 `git status` 실행 결과 (그대로 첨부):
```
 M backend/alembic/env.py
 M backend/app/api/v1/interviews.py
 M backend/app/main.py
 M backend/app/services/job_queue.py
 M docs/harness/traceability.md
 M frontend/app/globals.css
 M frontend/lib/api.ts
 M frontend/next-env.d.ts
?? backend/alembic/versions/0df1434883f2_v3_transcripts.py
?? backend/alembic/versions/8a55fda78a42_v4_deletion_requests.py
?? backend/alembic/versions/b84a71b986c5_v6_code_submissions.py
?? backend/alembic/versions/c1a2f5e9b7d3_v5_whiteboard_snapshots.py
?? backend/app/api/v1/code_submissions.py
?? backend/app/api/v1/consents.py
?? backend/app/api/v1/ops.py
?? backend/app/api/v1/whiteboard.py
?? backend/app/api/v1/ws.py
?? backend/app/models/code_submission.py
?? backend/app/models/deletion_request.py
?? backend/app/models/transcript.py
?? backend/app/models/whiteboard.py
?? backend/app/schemas/code_submission.py
?? backend/app/schemas/consent.py
?? backend/app/schemas/ops.py
?? backend/app/schemas/transcript.py
?? backend/app/schemas/whiteboard.py
?? docs/harness/units/unit-14-note.md
?? docs/harness/units/unit-14-test.md
?? docs/harness/units/unit-18-note.md
?? docs/harness/units/unit-3-test.md
?? docs/harness/units/unit-4-note.md
?? frontend/app/__wcpreview-check/
?? frontend/app/admin/
?? frontend/app/interviews/
?? frontend/components/
```
  (참고: 위 목록 중 이번 unit-18 06단계 세션이 만든 항목은 `frontend/lib/api.ts`(M, 05단계 산출물)·`backend/app/api/v1/ops.py`·`backend/app/schemas/ops.py`·`frontend/app/admin/`(둘 다 ?? , 05단계 산출물)·`docs/harness/traceability.md`(M, 이번 06 세션이 §10에서 갱신)뿐이다. 나머지(`code_submissions.py`, `whiteboard.py`, `consents.py`, `ws.py`, `frontend/app/interviews/`, `frontend/components/`, `frontend/app/__wcpreview-check/`, `unit-14-note.md`, `unit-14-test.md`, `unit-3-test.md`, `unit-4-note.md`, `frontend/next-env.d.ts` 등)는 unit-3/4/9/14/16/17 등 다른 병렬 작업단위가 동시에 진행하며 만든 산출물로, 이번 unit-18 테스트 세션과 무관하다 — unit-18이 담당하지 않는 파일을 임의로 되돌리거나 삭제하지 않았다.)
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: [x] 없음
- **Teardown 완료 확인됨 — 9절 PASS 판정의 전제조건 충족.**

## 8. 리스크 및 잔존 이슈
L1 경량판 — 미해당(단, 아래 07 부채 사실은 규칙에 따라 이 절이 아니라 `docs/harness/traceability.md`에 기록함).

참고(경량판 범위 밖 정보, 판정에는 영향 없음): 인수조건 5(프론트엔드 `/admin/ops` 화면의 실제 렌더링 — 권한없음 안내, 스켈레톤, 지표 카드, 갱신실패 배지)는 이번 06단계가 브라우저 자동화 도구 부재로 독립 재현하지 않았고, 코드 레벨 타입 일치(TC-003)만 확인했다. 이후 07(및 L1 06 정식화) 정산 시 06단계가 Playwright 등으로 직접 재현해야 할 항목이다. 아울러 공유 개발 DB에 여러 병렬 작업단위의 live 세션이 누적되고 있다는 관찰(§3)도 07/08 단계에서 테스트 데이터 격리 정책을 점검할 때 참고할 사항으로 남긴다.

## 9. 결론 및 판정
- [x] PASS — 다음 단계(05단계로 복귀, 다음 작업 단위 진행) 가능 (7절 Teardown 확인 완료됨)
- [ ] CONDITIONAL PASS
- [ ] FAIL

**L1 규칙에 따른 후속 처리**: 이 unit-18-test.md는 07단계로 handoff하지 않는다. 대신 `docs/harness/traceability.md` REQ-016 행의 "단위테스트" 컬럼과 비고란을 갱신하고, 05단계로 돌아가 다음 작업 단위를 진행한다.

## 10. 내부 검증 (최소 2회)
L1 경량판 — 검증 생략(ORCHESTRATOR.md 1장, 내부검증 규칙B 생략 가능 조항 적용). 다만 아래 두 차례는 최소한의 자기 점검으로 실제 수행했다:
- 1차 검증(인수조건 커버리지·근거): unit-18-note.md §6의 인수조건 1~5 중, L1 범위인 1~4(401/403/200/active_sessions 증가)는 TC-001·TC-002로 1:1 커버했고, 5(프론트 렌더링)는 §2/§8에 제외 사유와 함께 명시했다(임의 누락이 아님). TC-001/TC-002의 예상 결과는 unit-18-note.md §2(지표별 실측/스텁 경계표)와 03-system-design §7.2·04-ux-design [O-01]에 근거해 사전에 정의한 것이며, 실행 후에 짜맞춘 것이 아니다.
- 2차 검증(다음 단계로 넘겨도 되는가 / 놓친 경계 조건 재검토): TC-002 설계 초기에는 "admin 승격 직후 `active_sessions=0`"을 기대값으로 잡으려 했으나, 실제 실행 중 공유 DB에 이미 병렬 작업단위의 live 세션이 있어 베이스라인이 1이었음을 발견 — 절대값 검증은 이 공유 환경에서 거짓 실패/거짓 성공을 유발할 수 있는 취약한 설계였다고 판단해 즉시 델타(직전 호출 대비 +1) 검증으로 재설계했다(§3·§4 TC-002에 반영). 이 재검토가 없었다면 "0→1 확인"이라는 05단계 자체 기록을 그대로 승계하는 것과 다르지 않았을 것이다. 07단계로 넘길 때 남는 주요 미검증 경계는 프론트 렌더링(§8)과, 이번에 관찰한 "공유 DB 테스트 데이터 격리 부재"이며 둘 다 8절/9절 표기 및 이 결론에 명시했으므로 놓치지 않고 이관된다.
- 검증 로그 파일 경로: 별도 `verification-log-template.md` 파일을 생성하지 않고(L1 경량판, 검증 생략 조항 적용) 본 절과 §3·§4에 검증 내역을 직접 서술로 남김.
