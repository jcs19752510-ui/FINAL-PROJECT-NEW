# 테스트 결과서 (Test Result Report) — unit-3 (REQ-013, Feature B. 면접 세션 관리)

> `templates/test-report-template.md` 사용. **속도 트랙 L1 경량판** — 5·8·10절은 미해당으로 명시, 07단계로 handoff하지 않음(ORCHESTRATOR.md 1장, `.claude/agents/06-unit-tester.md` L1 규칙). unit-1-test.md/unit-2-test.md 선례를 따름.

## 1. 개요
- 테스트 대상: unit-3 — `backend/app/api/v1/interviews.py`(`GET /interviews/{id}`, `POST /interviews/{id}/resume`, `_apply_lazy_expiry`) (REQ-013)
- 테스트 유형: 단위
- 적용 Tier: High (`docs/harness/decisions.md` 참고 — 프로젝트 전체 선언값). Tier=High과 무관하게 이 feature는 속도 트랙 L1로 진행되어 06단계는 경량판으로 수행함(두 축은 별개, ORCHESTRATOR.md 1장 도입부).
- 적용 속도 트랙: **L1 (DEC-003)**
- 테스트 목적: 5단계(`05-unit-developer`)가 방금 완료한 unit-3 구현이, unit-3-note.md §5의 정상 경로 인수조건 중 핵심 상태전이 흐름(scheduled 조회/재개차단, live 전환 후 재접속 조회, live에서의 멱등 재개, paused→live 재개)을 실제로 만족하는지 **06단계 자신이 독립적으로 새 서버 프로세스를 기동해 재현**하여 증명한다. 5단계 자체 검증 기록(unit-3-note.md §8)은 참고만 하고 그대로 승계하지 않는다.
- 관련 산출물: `docs/harness/units/unit-3-note.md`, `docs/harness/03-system-design.md` §3(INTERVIEWS 상태머신 `status=paused/expired`)/§4.2(`/resume`)/§4.1(`SESSION_EXPIRED` 410)/§5.3(가용성)/§5.4(job idempotency), `docs/harness/04-ux-design.md` [C-12] 세션 재개 화면, `docs/harness/decisions.md` DEC-026(세션 만료 24시간 임계값), `docs/harness/traceability.md` REQ-013
- 테스트 수행자(에이전트): `06-unit-tester`
- 테스트 일시: 2026-09-19 (KST)

## 2. 테스트 범위 및 제외 범위
- 범위 (In-Scope, L1 경량판 — 정상 경로 1~2케이스로 한정, 단 서로 강하게 결합된 인접 검증은 같은 TC 안에 포함):
  - TC-001: 인수조건 1·2 — `scheduled` 상태 세션에 소유자가 `GET /interviews/{id}` 호출 시 `status=scheduled`/`resumable=false` 확인 + 동일 세션에 `/resume` 호출 시 `409 VALIDATION_ERROR` 확인(재개가 성립하지 않는 상태에서 정확히 차단되는지가 뒤이은 정상 재개 케이스의 전제이므로 짝을 이루는 최소 확인으로 포함).
  - TC-002: 인수조건 3·4·5 — 동의 부여 후 `/start`로 `live` 전환 → **재접속 시뮬레이션**(같은 세션 id로 새 `GET` 호출) → `resumable=true` 확인 → `/resume`(live) 멱등 `200`/`status=live` 확인 → DB에서 `status='paused'`로 직접 변경 → `GET`으로 `paused`/`resumable=true` 확인 → `/resume` 호출 시 `200`과 함께 `status=live`로 복귀 확인까지 하나의 연속 정상 경로 플로우로 재현.
- 제외 범위 (Out-of-Scope) 및 사유:
  - 인수조건 6(만료 판정 후 410 SESSION_EXPIRED), 7(completed 상태 409), 8(수평 권한 상승 403), 9(토큰 없음 401, 존재하지 않는 id 404) — L1 규칙상 "정상 경로 1~2케이스"로 한정되며, unit-3-note.md §5·§8에 이미 05단계가 curl로 실행 확인한 기록(인수조건 1~9 전부)이 있어 06 범위에서 임의로 확장하지 않음. 단, 이 항목들은 **아직 06단계가 독립 재현하지 않은 상태**이므로 8절 상당 리스크로 traceability.md에 남긴다.
  - `GET /interviews/{id}/code-submissions`, `GET /interviews/{id}/whiteboard` — unit-3-note.md §1·§3(편차 #2)에서 이번 유닛 구현 범위 자체에서 명시적으로 제외(unit-9/unit-17 책임)되었으므로 테스트 대상도 아니다.
  - `live→paused` 자동 전이 메커니즘(하트비트/WS 접속 감지) — 이번 유닛이 신설하지 않았음(DEC-026), 테스트 대상 자체가 존재하지 않는다. `paused` 상태는 unit-3-note.md §4 안내대로 DB 직접 조작으로만 재현했다(운영 경로 아님).
  - 실제 turn/코드/화이트보드 콘텐츠 복원 — TRANSCRIPTS/CODE_SUBMISSIONS/WHITEBOARD_SNAPSHOTS 모델이 없는 이후 유닛(unit-4/9/17) 범위, unit-3-note.md §4에서 이미 혼동하지 말 것으로 명시.

## 3. 테스트 환경
- 실행 환경: Windows 11, PostgreSQL 16(Docker, `final-project-db` 컨테이너, 포트 5544, unit-1·2·3-note.md와 동일 컨테이너 재사용 — 6시간 이상 계속 Up 상태 확인), Python venv `.harness-tmp/venv_05_unit1`(05단계가 만든 격리 venv를 06이 재사용 — unit-1-note.md/unit-2-note.md/unit-3-note.md §4가 명시적으로 재사용을 허용), FastAPI 앱을 06단계가 직접 새 프로세스로 기동(포트 8023, uvicorn, PID 39424 — 05단계가 검증에 쓴 포트/프로세스와 무관한 별도 기동으로 5단계 결과를 그대로 승계하지 않음).
- 테스트 데이터: 06단계가 이번에 새로 생성한 계정 2건 — `qa06u3_cand1_<ts>@example.com`, `qa06u3_cand2_<ts>@example.com`(둘 다 candidate. cand2는 이번 TC 범위(§2)에서는 실제로 호출에 사용하지 않았으나 §2 제외범위 항목의 후속 06 정식화 시 수평권한 테스트용으로 함께 등록해 두었다 — 이번 판정에는 영향 없음). 신규 면접 세션 1건(candidate1 소유). `ai_interview_notice` 동의 레코드 1건은 unit-2/3-note.md 안내대로 `docker exec final-project-db psql -U final_app -d final_project`로 직접 INSERT(POST /consents API가 아직 없음).
- 전제 조건 (Preconditions): Docker Desktop 기동 상태, `final-project-db` 컨테이너 Up, `backend/.env` 존재(`DATABASE_URL=postgresql+psycopg://final_app:final_app_pw@localhost:5544/final_project`), 5단계 게이트1(린트)·게이트2(코드리뷰) 통과 확인됨 — unit-3-note.md §6(`ruff check app alembic/env.py` 에러 0건)·§7(코드리뷰 체크리스트 6항목 전부 [x]), 06단계는 이를 note에서 확인만 하고 재검증하지 않음(원칙에 따름).

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-001 | scheduled 상태 조회 + 재개 차단 (인수조건 1·2) | candidate1 회원가입·로그인 완료, `POST /interviews`로 세션 생성(scheduled) | ① `curl http://127.0.0.1:8023/api/v1/interviews/{id} -H "Authorization: Bearer <candidate1_token>"` ② `curl -X POST http://127.0.0.1:8023/api/v1/interviews/{id}/resume -H "Authorization: Bearer <candidate1_token>"` | ①: HTTP 200, `status=scheduled`, `resumable=false` / ②: HTTP 409, `code=VALIDATION_ERROR` | ①: HTTP 200, 바디 `{"id":"ef0b5db8-...","status":"scheduled","report_status":"none","started_at":null,...,"resumable":false}` — 일치 / ②: HTTP 409, 바디 `{"...","detail":"live 또는 paused 상태의 세션만 재개할 수 있습니다 (현재 상태: scheduled).","code":"VALIDATION_ERROR"}` — 일치 | Pass | 06단계가 직접 재현. 05단계 기록 재사용 아님 |
| TC-002 | live 전환 → 재접속 조회 → 멱등 재개 → paused→live 재개 (인수조건 3·4·5) | TC-001에서 생성한 candidate1 소유 interview(`ef0b5db8-...`), `ai_interview_notice` 동의 DB 직접 INSERT 완료 | ① `curl -X POST .../interviews/{id}/start -H "Authorization: Bearer <candidate1_token>"` ② (재접속 시뮬레이션) 새 `curl GET .../interviews/{id}` ③ `curl -X POST .../interviews/{id}/resume`(live 상태) ④ `docker exec final-project-db psql ... -c "UPDATE interviews SET status='paused' WHERE id='{id}';"` ⑤ `curl GET .../interviews/{id}` ⑥ `curl -X POST .../interviews/{id}/resume`(paused 상태) | ①: HTTP 202, `interview.status=live`, `started_at` not null / ②: HTTP 200, `status=live`, `resumable=true` / ③: HTTP 200, `status=live`(변화 없음, 멱등) / ④: UPDATE 성공 / ⑤: HTTP 200, `status=paused`, `resumable=true` / ⑥: HTTP 200, `status=live`로 전환 | ①: HTTP 202, 바디 `{"job_id":"efae9784-...","interview":{...,"status":"live","started_at":"2026-09-18T22:33:42.453306Z",...}}` — 일치 / ②: HTTP 200, 바디에 `"status":"live","resumable":true` — 일치 / ③: HTTP 200, 바디 `"status":"live","resumable":true`(변화 없음) — 멱등 확인 일치 / ④: `UPDATE 1` — 성공 / ⑤: HTTP 200, 바디 `"status":"paused","resumable":true` — 일치 / ⑥: HTTP 200, 바디 `"status":"live","resumable":true` — paused→live 전환 확인, 일치 | Pass | 06단계가 직접 재현. 05단계 기록 재사용 아님. 동의 INSERT/paused 강제 설정은 unit-3-note.md §4 안내를 그대로 따름(운영 경로 아님, 개발/테스트 전용) |

> L1 경량판(정상 경로 1~2케이스)이므로 경계값/예외 입력 케이스(만료 410, completed 409, 수평 권한 상승 403, 인증 없음 401, 존재하지 않는 id 404)는 위 §2 제외범위에 사유와 함께 명시했다(5단계가 이미 실행한 기록은 있으나 06이 독립 재현하지 않았음을 traceability.md에 리스크로 기록).

## 5. 커버리지
L1 경량판 — 미해당.

## 6. 결함(Defect) 목록
결함 없음. 근거: TC-001·TC-002 각각 예상 결과(HTTP 상태 코드, 에러 코드, 응답 바디 필드값 — status/resumable/started_at/job_id)를 사전에 정의하고, 실제 curl 및 psql 실행 결과와 필드 단위로 1:1 대조하여 전부 일치함을 확인했다("에러 없이 실행됨"이 아니라 필드 단위 비교로 PASS 판정). `scheduled`에서의 재개 차단(409)이 정확히 발동하는 것, `live` 재접속 조회 시 `resumable=true`가 정확히 파생되는 것, `/resume`이 `live`에서 멱등하게 동작하는 것, `paused`에서 실제로 `live`로 상태가 전환되는 것까지 전부 실제 값으로 확인했다.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트 목록:
  - `.harness-tmp/u3_email1.txt`, `.harness-tmp/u3_email2.txt`, `.harness-tmp/u3_reg1.json`, `.harness-tmp/u3_reg2.json`, `.harness-tmp/u3_login1.json`, `.harness-tmp/u3_token1.txt`, `.harness-tmp/u3_cand1_id.txt`, `.harness-tmp/u3_interview.json`, `.harness-tmp/u3_interview_id.txt` (테스트 실행용 스크래치 파일)
  - `.harness-tmp/uvicorn_06_unit3.log` (06단계가 직접 기동한 서버 프로세스 로그, 포트 8023)
  - 재사용(신규 생성 아님): `.harness-tmp/venv_05_unit1` — 05단계가 만든 venv를 그대로 재사용(unit-3-note.md §4에서 재사용 허용 명시). 06단계가 신규로 만든 것이 아니므로 삭제 대상으로 삼지 않음(다음 단계도 재사용 가능한 공용 산출물).
  - 세션 시작 시점에 이미 `.harness-tmp/`에 존재하던 unit-1 세션 잔여물(`cookies.txt`, `cookies2.txt`, `login_resp.json`, `nextdev.log`, `reg_korean.json`, `uvicorn_unit1.log`)은 이번 세션이 생성한 것이 아니고 강제 중단(TaskStop 등) 흔적도 아니므로(unit-1-test.md/unit-2-test.md에서도 동일하게 확인된 기존 잔존물) 그대로 두었다.
  - 신규 생성한 DB 레코드: candidate1/candidate2 계정 2건, interview 1건, consents 1건(모두 테스트 데이터, 재생성 가능) — `final-project-db` 컨테이너 자체는 다음 단위가 이어서 쓰므로 유지(unit-1·2-test.md와 동일 방침).
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): [x] 예
- 정리(삭제) 완료 여부: 완료. `u3_email1.txt`, `u3_email2.txt`, `u3_reg1.json`, `u3_reg2.json`, `u3_login1.json`, `u3_token1.txt`, `u3_cand1_id.txt`, `u3_interview.json`, `u3_interview_id.txt`, `uvicorn_06_unit3.log` 전부 삭제함. 06단계가 기동한 uvicorn 프로세스(PID 39424, 포트 8023)는 정리 전 `Stop-Process -Force`로 종료 확인(종료 후 `curl`이 연결 실패(exit code non-zero, http_code 000)로 응답, 서버 다운 확인). DB에 생성한 candidate1/2 계정, interview, consent 레코드는 각각 `DELETE`로 정리 완료(`DELETE 1`/`DELETE 1`/`DELETE 2` 결과 확인).
- 정리 후 `git status` 실행 결과 (그대로 첨부):
```
On branch PROD
nothing to commit, working tree clean
```
  (참고: 이 세션 시작 시점의 git status 스냅샷은 다수의 modified/untracked 항목을 포함하고 있었으나, 06단계 작업 도중 별도 커밋 `d8d3ee0`(작성자 정찬성, 2026-09-19 07:34:01, 메시지 "파이널 프로젝트 신규 프로그램")이 생성되어 그 항목들이 커밋 상태로 전환되었다 — 이 커밋은 06단계 세션이 `git add`/`git commit`을 실행해 만든 것이 아니다(이번 세션은 git 쓰기 명령을 전혀 실행하지 않았다). 즉 working tree가 clean한 것은 06단계가 만든 테스트 아티팩트가 전부 정리되어 남은 diff가 없다는 의미이고, 그 이전의 커밋되지 않은 변경 이력 자체는 이 06 세션과 무관한 외부 요인으로 정리(커밋)되었다.)
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: [x] 없음
- **Teardown 완료 확인됨 — 9절 PASS 판정의 전제조건 충족.**

## 8. 리스크 및 잔존 이슈
L1 경량판 — 미해당(단, 아래 07 부채 사실은 규칙에 따라 이 절이 아니라 `docs/harness/traceability.md`에 기록함).

참고(경량판 범위 밖 정보, 판정에는 영향 없음): 인수조건 6·7·8·9(만료 410, completed 상태 409, 수평 권한 상승 403, 인증 없음 401, 존재하지 않는 id 404)는 이번 06단계가 독립 재현하지 않았고, 5단계 자체 실행 기록(unit-3-note.md §8)만 존재하는 상태다. `code-submissions`/`whiteboard` GET 미구현(unit-9/17 책임), `paused` 자동 전이 메커니즘 미구현(DEC-026)도 함께 traceability.md에 남긴다. 이후 07(및 L1 06 정식화) 정산 시 06단계가 직접 재현해야 할 항목이다.

## 9. 결론 및 판정
- [x] PASS — 다음 단계(05단계로 복귀, 다음 작업단위 진행) 가능 (7절 Teardown 확인 완료됨)
- [ ] CONDITIONAL PASS
- [ ] FAIL

**L1 규칙에 따른 후속 처리**: 이 unit-3-test.md는 07단계로 handoff하지 않는다. 대신 `docs/harness/traceability.md` REQ-013 행의 "단위테스트" 컬럼과 비고란을 갱신하고, 05단계로 돌아가 다음 작업 단위를 진행한다.

## 10. 내부 검증 (최소 2회)
L1 경량판 — 검증 생략(ORCHESTRATOR.md 1장, 내부검증 규칙B 생략 가능 조항 적용).
