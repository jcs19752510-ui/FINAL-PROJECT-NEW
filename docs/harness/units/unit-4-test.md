# 테스트 결과서 (Test Result Report) — unit-4 (REQ-003, Feature C. 대화형 인터뷰 엔진 — 텍스트 채팅 인터페이스)

> `templates/test-report-template.md` 사용. **속도 트랙 L1 경량판** — 5·8·10절은 미해당으로 명시, 07단계로 handoff하지 않음(ORCHESTRATOR.md 1장, `.claude/agents/06-unit-tester.md` L1 규칙). unit-1/2/3-test.md 선례를 따름.

## 1. 개요
- 테스트 대상: unit-4 — `backend/app/api/v1/interviews.py`의 `POST /interviews/{id}/turns`(텍스트 전용), `GET /interviews/{id}/transcripts`, `backend/app/api/v1/ws.py`(`/ws/interviews/{id}` WebSocket 게이트웨이), `backend/app/models/transcript.py`, `backend/app/schemas/transcript.py` (REQ-003)
- 테스트 유형: 단위
- 적용 Tier: High(`docs/harness/decisions.md` 참고 — 프로젝트 전체 선언값). Tier=High과 무관하게 이 feature는 속도 트랙 L1로 진행되어 06단계는 경량판으로 수행함(두 축은 별개, ORCHESTRATOR.md 1장 도입부).
- 적용 속도 트랙: **L1 (DEC-003)**
- 테스트 목적: 5단계(`05-unit-developer`)가 방금 완료한 unit-4 구현이, unit-4-note.md §7의 정상 경로 인수조건 중 핵심 흐름(텍스트 턴 저장/조회, WS 연결 자체)을 실제로 만족하는지 **06단계 자신이 독립적으로 새 서버 프로세스를 기동해 재현**하여 증명한다. 5단계 자체 검증 기록(unit-4-note.md §6)은 참고만 하고 그대로 승계하지 않는다 — 특히 5단계가 note §6-5에서 "브라우저 자동화 도구가 없어 실제 클릭/타이핑 상호작용은 코드 리뷰+curl로 갈음했다"고 명시적으로 밝힌 한계를, 06단계가 최소한 **실제 HTTP/WS 요청**으로 재검증(브라우저 자동화는 이번에도 사용 불가하여 여전히 미해결 부채로 남김, §2/§8 참고)한다.
- 관련 산출물: `docs/harness/units/unit-4-note.md`, `docs/harness/03-system-design.md` §3(TRANSCRIPTS ERD)/§4.2(`POST /interviews/{id}/turns`)/§4.3(WS 채널 역할 분리, 이벤트 스키마)/§6.2(DEC-023), `docs/harness/04-ux-design.md` [C-06] 면접장, `docs/harness/traceability.md` REQ-003
- 테스트 수행자(에이전트): `06-unit-tester`
- 테스트 일시: 2026-09-19 (KST)

## 2. 테스트 범위 및 제외 범위
- 범위 (In-Scope, L1 경량판 — 정상 경로 1~2케이스로 한정):
  - TC-001: 인수조건 1·2 — `live` 세션에 텍스트 턴 2회 연속 제출(`202 {job_id}`) + `GET /transcripts`로 `turn_index` 0/1 오름차순 저장·조회 확인. 한글(멀티바이트) 텍스트가 저장/응답 왕복 시 바이트 단위로 손실 없이 보존되는지까지 확인(§4 TC-001 비고 참고 — 5단계 note가 "쉘 인코딩 이슈 우회" 언급을 남겼기에 06이 직접 재확인이 필요하다고 판단해 포함).
  - TC-002: 인수조건 9(WS 연결 자체 범위) — 유효 토큰+본인 세션으로 `/ws/interviews/{id}` 연결 성공, 화이트리스트 메시지(`cancel_queue_wait`)/화이트리스트 외 타입/비-JSON 프레임을 보내도 연결이 끊기지 않는지 확인, 무효 토큰으로 연결 시도 시 거부되는지 확인(인증 성공/실패라는 하나의 연결-계약을 검증하는 짝 케이스로 TC-001과 별개 2번째 케이스에 포함 — unit-3-test.md의 TC 구성 방식과 동일 원칙).
- 제외 범위 (Out-of-Scope) 및 사유:
  - 인수조건 3(scheduled 409), 4(completed 409), 5(422 — 빈 문자열/누락/4001자), 6(403/401/404), 7(410 만료) — L1 규칙상 "정상 경로 1~2케이스"로 한정되며, unit-4-note.md §6에 이미 05단계가 curl로 실행 확인한 기록이 있어 06 범위에서 임의로 확장하지 않음. **아직 06단계가 독립 재현하지 않은 상태**이므로 traceability.md에 L1 부채로 남긴다.
  - 인수조건 8(브라우저로 `/interviews/{id}` 접속 → 채팅 UI → 낙관적 UI → 12초 타임아웃 안내) — 이 환경에 브라우저 자동화 도구가 연결되어 있지 않아 06단계도 실제 클릭/타이핑 상호작용을 재현할 수 없었다. 5단계의 한계(note §6-5)가 06단계에서도 해소되지 않았음을 명시적으로 인정하고, traceability.md에 미해결 부채로 별도 기록한다(§8 아래 "L1 부채" 참고).
  - 인수조건 9 중 `stage_update`/`turn_result` 실제 도착 여부 — unit-4-note.md §2-2/3/§7-9가 "AI Worker 미구현으로 이 유닛에서는 영구히 도착하지 않는 것이 정상 동작"이라고 명시했으므로, 애초에 테스트 대상 자체가 존재하지 않는다(테스트 설계 오류를 피하기 위해 의도적으로 검증 시도조차 하지 않음).
  - 큐 초과(429 QUEUE_FULL), AI_SERVICE_TIMEOUT 등 — `job_queue.py`가 스텁이라 재현 불가능한 시나리오(unit-4-note.md job_queue.py docstring 참고).

## 3. 테스트 환경
- 실행 환경: Windows 11, PostgreSQL 16(Docker, `final-project-db` 컨테이너, 포트 5544, 기존 컨테이너 재사용 — `docker ps` 확인 결과 7시간 이상 Up 상태), Python venv `.harness-tmp/venv_05_unit1`(05단계가 만든 격리 venv를 06이 재사용 — unit-4-note.md §3이 재사용 허용 명시), FastAPI 앱을 06단계가 직접 새 프로세스로 기동(포트 8027, `uvicorn app.main:app --port 8027`, PID 36124/21216(reload 모드로 워커+리로더 2프로세스) — 05단계가 검증에 쓴 포트(8024/8000)와 무관한 별도 기동으로 5단계 결과를 그대로 승계하지 않음). WS 클라이언트 재현은 별도 파이썬 스크립트(`websockets` 17.1, `.harness-tmp/u4_ws_test.py`, 테스트 후 삭제)로 수행.
- 테스트 데이터: 06단계가 이번에 새로 생성한 candidate 계정 1건(`qa06u4_cand1_<ts>@example.com`), 신규 면접 세션 1건(해당 candidate 소유). `ai_interview_notice` 동의 레코드 1건은 unit-2/3/4-note.md 안내대로 `docker exec final-project-db psql -U final_app -d final_project`로 직접 INSERT(실제 컬럼명이 note 예시와 달라 `\d consents`로 실제 스키마(`granted_at`, `revoked_at`, `ip_address`)를 먼저 확인 후 보정 — 아래 §6 결함 없음 판단에 참고 사실로 기록. 이는 unit-2/14 소관 스키마이며 unit-4 결함이 아니다).
- 전제 조건 (Preconditions): Docker Desktop 기동 상태, `final-project-db` 컨테이너 Up, `backend/.env` 존재(`DATABASE_URL=postgresql+psycopg://final_app:final_app_pw@localhost:5544/final_project`), `alembic current`가 단일 head(`8a55fda78a42`)임을 재확인(브랜칭 없음), 5단계 게이트1(린트)·게이트2(코드리뷰) 통과 확인됨 — unit-4-note.md §4(ruff/eslint(unit-4 소유 파일 한정)/tsc/build 전부 에러 0건)·§5(코드리뷰 체크리스트 6항목 전부 [x]), 06단계는 이를 note에서 확인만 하고 재검증하지 않음(원칙에 따름).

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-001 | live 세션에 텍스트 턴 2회 제출 + 이력 조회 (인수조건 1·2) | candidate1 회원가입·로그인 완료, `POST /interviews`로 세션 생성 후 동의 INSERT+`/start`로 `live` 전환 확인(job_id `cc7ad3ba-...`, `started_at` not null) | ① 한글(멀티바이트) 텍스트로 `curl -X POST http://127.0.0.1:8027/api/v1/interviews/{id}/turns`(파일 기반 body로 쉘 인코딩 이슈 우회) ② ASCII 텍스트로 동일 엔드포인트 재호출 ③ `curl GET http://127.0.0.1:8027/api/v1/interviews/{id}/transcripts` | ①: HTTP 202 + 문자열 job_id / ②: HTTP 202 + job_id / ③: HTTP 200, 배열 길이 2, `turn_index` 0(한글 텍스트)·1(ASCII 텍스트) 오름차순, 각 `speaker=user`/`input_mode=text`, 한글 원문이 바이트 단위로 손실 없이 왕복 | ①: HTTP 202, `{"job_id":"fc11f578-..."}` — 일치 / ②: HTTP 202, `{"job_id":"1b7dddb9-..."}` — 일치 / ③: HTTP 200, `[{turn_index:0, speaker:user, input_mode:text, content_text:"안녕하세요, 저는 3년차 백엔드 개발자입니다."}, {turn_index:1, speaker:user, input_mode:text, content_text:"I have 3 years of backend experience."}]` — 필드 전부 일치. 터미널 표시상 한글이 mojibake로 보여 최초 의심했으나, Python으로 요청 원문 바이트열과 응답 저장값 바이트열을 `sent.encode('utf-8') == stored.encode('utf-8')`로 직접 비교해 **완전 일치(byte-for-byte)** 확인 — 터미널 코드페이지 표시 문제였을 뿐 실제 데이터 손실은 없음을 증명 | Pass | 06단계가 직접 재현(05단계 기록 재사용 아님). "에러 없이 실행됨"이 아니라 바이트 단위 비교로 PASS 판정 |
| TC-002 | WS 연결 자체 검증 — 인증 성공/화이트리스트·정크 메시지 내구성/인증 실패 (인수조건 9, 연결 범위만) | TC-001의 candidate1 토큰 및 live 세션 id 재사용 | ① 유효 토큰으로 `ws://127.0.0.1:8027/ws/interviews/{id}?token=...` 연결 ② 연결 유지 상태에서 `{"type":"cancel_queue_wait"}`, `{"type":"not_a_real_type"}`(화이트리스트 외), `"not json at all"`(비-JSON) 순서로 전송 후 0.5초 대기, 연결 상태(`ws.state`) 확인 후 클라이언트가 정상 종료 ③ 잘못된 토큰(`token=not-a-real-token`)으로 동일 interview에 연결 시도 | ①: 핸드셰이크 성공(연결 수립) / ②: 세 메시지 모두 처리 후에도 연결이 `OPEN` 상태 유지(끊기지 않음) / ③: 서버가 인증 실패로 연결을 거부(핸드셰이크 단계에서 차단) | ①: `case_a_connected=true` — 일치 / ②: `case_a_still_open_after_whitelisted_and_junk_msgs=true` — 일치(화이트리스트 메시지·화이트리스트 외 메시지·비-JSON 프레임 어느 것도 연결을 끊지 않음, 서버 로그에도 예외 스택트레이스 없음 확인) / ③: `case_b_rejected=true`, 클라이언트가 관측한 실제 실패는 `websockets.exceptions.InvalidStatus: server rejected WebSocket connection: HTTP 403` — "연결이 거부된다"는 인수조건은 충족하나, unit-4-note.md/ws.py 코드주석이 서술하는 "`WS_1008_POLICY_VIOLATION`로 연결 거부(닫힘 코드 1008)"라는 표현과 실제 클라이언트 관측 결과(핸드셰이크 자체가 HTTP 403으로 거절됨, WS 닫힘 프레임 1008이 아님)가 다름 — Starlette/FastAPI가 `accept()` 호출 전에 `close()`를 호출하면 ASGI 서버가 WS 핸드셰이크를 HTTP 레벨에서 거절하고 지정한 close code는 클라이언트에 전달되지 않는 프레임워크 동작 때문으로 추정됨(코드 결함 아님, 보안 목적(미인증 접근 차단)은 정확히 달성됨) | Pass(관찰사항 있음, §6 참고) | 06단계가 직접 재현(05단계 기록 재사용 아님). 인수조건 9가 요구하는 것은 "연결 거부"이지 특정 WS 닫힘 코드 수신이 아니므로 AC 충족으로 판정 |

> L1 경량판(정상 경로 1~2케이스)이므로 경계값/예외 입력 케이스(scheduled/completed 409, 422, 403/401/404, 410 만료)와 브라우저 UI 흐름(인수조건 8)은 위 §2 제외범위에 사유와 함께 명시했다(5단계가 이미 실행한 기록은 있으나 06이 독립 재현하지 않았음을 traceability.md에 리스크로 기록).

## 5. 커버리지
L1 경량판 — 미해당.

## 6. 결함(Defect) 목록
결함 없음. 근거: TC-001·TC-002 각각 예상 결과(HTTP 상태 코드, 응답 바디 필드값 — job_id/turn_index/speaker/input_mode/content_text, WS 연결 상태)를 사전에 정의하고, 실제 curl/WS 클라이언트 실행 결과와 필드 단위로 1:1 대조하여 전부 일치함을 확인했다("에러 없이 실행됨"이 아니라 필드 단위 비교로 PASS 판정). 특히 한글 텍스트가 저장/응답 왕복 과정에서 손상되는 것처럼 보인 현상(터미널 표시상 mojibake)을 의심스러운 결과로 간주해 즉시 바이트 단위 비교로 재검증했고, 실제로는 데이터 손실이 전혀 없음(터미널 코드페이지 표시 문제)을 증명했다 — "돌아가는 것 같다"가 아니라 근거로 확인함.

관찰사항(결함 아님, 정보 공유 목적): TC-002 ③에서 WS 인증 실패 시 클라이언트가 실제로 관측하는 것은 unit-4-note.md/`ws.py` 코드주석이 서술한 "WS_1008_POLICY_VIOLATION 닫힘 코드"가 아니라 "HTTP 403 핸드셰이크 거절"이다(Starlette/FastAPI가 `accept()` 이전에 `close()`를 호출하면 발생하는 프레임워크 동작). 인수조건 9가 요구하는 보안 목표("본인 소유가 아니거나 미인증이면 연결이 거부된다")는 정확히 달성되므로 결함으로 분류하지 않았으나, 코드 주석/설계 설명의 정확도 개선 여지가 있어 05단계에 참고 정보로 공유한다(재작업 요청 아님, PASS 판정에 영향 없음).

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트 목록:
  - `.harness-tmp/u4_ts.txt`, `u4_email1.txt`, `u4_reg1.json`, `u4_login1.json`, `u4_token1.txt`, `u4_cand1_id.txt`, `u4_interview.json`, `u4_interview_id.txt`, `u4_start.json`, `u4_turn1_body.json`, `u4_turn1_resp.json`, `u4_turn2_resp.json`, `u4_transcripts.json`, `u4_ws_test.py`, `uvicorn_06_unit4.log` (테스트 실행용 스크래치 파일/로그)
  - 재사용(신규 생성 아님): `.harness-tmp/venv_05_unit1` — 05단계가 만든 venv를 그대로 재사용(unit-4-note.md §3에서 재사용 허용 명시).
  - 신규 생성한 DB 레코드: candidate1 계정 1건, interview 1건, consent 1건, transcript 2건(모두 테스트 데이터, 재생성 가능) — `final-project-db` 컨테이너 자체는 다음 단위가 이어서 쓰므로 유지(unit-1/2/3-test.md와 동일 방침).
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): [x] 예
- 정리(삭제) 완료 여부: 완료(단, 아래 특이사항 참고). uvicorn 프로세스(PID 36124/21216, 포트 8027)는 정리 전 `Stop-Process -Force`로 종료 확인(종료 후 `curl`이 연결 실패(`http_code=000`)로 응답, 서버 다운 확인). DB에 생성한 candidate1 계정/interview/consent/transcript(2건) 레코드는 각각 `DELETE`로 정리 완료(`DELETE 2`/`DELETE 1`/`DELETE 1`/`DELETE 1` 결과 확인, 자식 레코드인 transcript부터 순서대로 삭제해 FK 오류 없음). 이후 위에 나열한 개별 임시 파일들을 `rm -f`로 삭제하려던 시점에 **`.harness-tmp/` 디렉토리 전체가 이미 사라져 있음을 발견**했다 — `ls`/PowerShell `Get-ChildItem` 양쪽 모두 디렉토리 자체가 존재하지 않음을 확인. 이 세션은 `.harness-tmp/` 디렉토리 자체를 삭제하는 명령을 실행한 적이 없다(개별 파일 `rm -f`만 실행). `git status`(아래)에 unit-14/code_submissions/whiteboard 등 이 세션이 만들지 않은 다수의 병렬 작업 산출물이 동시에 나타나는 것으로 보아, 동시에 진행 중인 다른 에이전트 세션이 자신의 정리 작업(예: 디렉토리 단위 정리) 과정에서 공유된 `.harness-tmp/`(unit-1이 만든 venv 포함, 여러 유닛이 공용으로 재사용 중이던 디렉토리) 전체를 함께 제거한 것으로 추정된다 — 이 06 세션이 유발한 것이 아니다. 결과적으로 이 세션이 만든 임시 파일은 물론 디렉토리 자체가 통째로 사라져 "정리 완료" 상태(잔여물 없음)는 달성되었으나, 다른 병렬 유닛이 재사용 중이던 `venv_05_unit1` 등 공용 자산까지 함께 사라진 점은 06단계 범위를 넘는 **환경 이슈로 오케스트레이터에 보고가 필요**하다(unit-4 자체의 PASS 판정과는 무관 — unit-4 소관 코드/DB 정리는 이 사건 이전에 이미 완료되어 있었다).
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
	modified:   docs/harness/traceability.md
	modified:   frontend/app/globals.css
	modified:   frontend/lib/api.ts
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
	backend/app/api/v1/whiteboard.py
	backend/app/api/v1/ws.py
	backend/app/models/code_submission.py
	backend/app/models/deletion_request.py
	backend/app/models/transcript.py
	backend/app/models/whiteboard.py
	backend/app/schemas/code_submission.py
	backend/app/schemas/consent.py
	backend/app/schemas/ops.py
	backend/app/schemas/transcript.py
	backend/app/schemas/whiteboard.py
	docs/harness/units/unit-14-note.md
	docs/harness/units/unit-14-test.md
	docs/harness/units/unit-18-note.md
	docs/harness/units/unit-3-test.md
	docs/harness/units/unit-4-note.md
	frontend/app/admin/
	frontend/app/interviews/
	frontend/components/

no changes added to commit (use "git add" and/or "git commit -a")
```
  (참고: 이 목록 중 `.harness-tmp/`는 `.gitignore`에 의해 애초에 git 추적 대상이 아니므로 위 디렉토리 소실 사건은 git status에 나타나지 않는다. 위 목록에 보이는 modified/untracked 항목은 unit-4 소관 변경분(`interviews.py`, `main.py`, `job_queue.py`, `ws.py`, `transcript.py`, `schemas/transcript.py`, `frontend/app/interviews/`, `frontend/lib/api.ts`, `globals.css` 등)과, 이 세션이 만들지 않은 다른 병렬 작업 단위의 진행 중 산출물(unit-14/18, code_submissions, whiteboard, ops, consents 등)이 섞여 있다 — unit-4-note.md §3 "병렬 작업 알림"과 동일한 맥락이며, 이번 06 세션이 그 파일들을 만들거나 건드리지 않았다. 이 세션이 만든 테스트 전용 아티팩트는 `.harness-tmp/` 소실로 인해 결과적으로 전부 제거된 상태다.)
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: [x] 없음(단, 위와 같이 동시 진행 중인 **다른** 세션에 의한 것으로 추정되는 외부 디렉토리 소실 이벤트를 관찰했다 — 이 세션 자체는 중단 없이 끝까지 수행되었다).
- **Teardown 완료 확인됨(결과적으로 잔여물 없음) — 9절 PASS 판정의 전제조건 충족. 단, `.harness-tmp/` 공유 디렉토리 소실 건은 오케스트레이터/다른 병렬 유닛 담당자에게 별도 공유가 필요한 환경 이슈로 기록해 둔다.**

## 8. 리스크 및 잔존 이슈
L1 경량판 — 미해당(단, 아래 07 부채 사실은 규칙에 따라 이 절이 아니라 `docs/harness/traceability.md`에 기록함).

참고(경량판 범위 밖 정보, 판정에는 영향 없음): 인수조건 3~7(scheduled/completed 409, 422, 403/401/404, 410 만료)과 인수조건 8(브라우저 실사용 UI 흐름 — 낙관적 UI, 12초 타임아웃 안내 전환)은 이번 06단계가 독립 재현하지 않았고, 5단계 자체 실행 기록(unit-4-note.md §6)만 존재하는 상태다. 특히 인수조건 8은 이 환경에 브라우저 자동화 도구가 없어 06단계도 5단계와 동일한 한계에 부딪혔다 — 07(또는 06 정식화) 단계가 반드시 실제 브라우저(또는 headless 브라우저 자동화 도구)로 재현해야 한다. WS `stage_update`/`turn_result` 미도착은 unit-7(LLM) 미구현에 따른 설계상 정상 동작이라 결함이 아니다. `.harness-tmp/` 공유 디렉토리가 병렬 세션 도중 통째로 소실된 환경 이슈(§7)도 이후 단계가 인지해야 할 사항으로 함께 남긴다. 이후 07(및 L1 06 정식화) 정산 시 06단계가 직접 재현해야 할 항목이다.

## 9. 결론 및 판정
- [x] PASS — 다음 단계(05단계로 복귀, 다음 작업단위 진행) 가능 (7절 Teardown 확인 완료됨)
- [ ] CONDITIONAL PASS
- [ ] FAIL

**L1 규칙에 따른 후속 처리**: 이 unit-4-test.md는 07단계로 handoff하지 않는다. 대신 `docs/harness/traceability.md` REQ-003 행의 "단위테스트" 컬럼과 비고란을 갱신하고, 05단계로 돌아가 다음 작업 단위를 진행한다.

## 10. 내부 검증 (최소 2회)
L1 경량판 — 검증 생략(ORCHESTRATOR.md 1장, 내부검증 규칙B 생략 가능 조항 적용). 단, 아래는 생략 조항 하에서도 QA 원칙상 실시한 자체 재점검 기록이다:
- 1차 점검: 인수조건 1·2·9(연결 범위)에 대응하는 테스트 케이스가 TC-001/TC-002로 1:1 존재하는지, 예상 결과가 unit-4-note.md §7과 03-system-design §4.2/§4.3에 근거하는지 확인 — 모두 일치.
- 2차 점검: "이 결과를 다음 단계(07 정식화)에 넘겨도 되는가"를 의심하며 재검토 — 한글 텍스트 왕복이 mojibake처럼 보인 결과를 그대로 PASS 처리하지 않고 바이트 비교로 재확인한 것, WS 인증 실패 시 코드주석과 실제 관측이 다른 것을 발견해 관찰사항으로 남긴 것이 이 재검토의 산출물이다. 두 가지 모두 놓쳤다면 다음 단계에 잘못된 확신을 넘겼을 수 있는 경계 조건이었다.
