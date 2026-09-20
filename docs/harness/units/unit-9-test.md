# 테스트 결과서 (Test Result Report) — unit-9 (REQ-008, Feature D. 라이브 코딩 환경)

> `templates/test-report-template.md` 사용. **속도 트랙 L1 경량판** — 5·8·10절은 미해당으로 명시, 07단계로 handoff하지 않음(ORCHESTRATOR.md 1장, `.claude/agents/06-unit-tester.md` L1 규칙). unit-1/2/3/4-test.md 선례를 따름.

## 1. 개요
- 테스트 대상: unit-9 — `backend/app/api/v1/code_submissions.py`(`POST`/`GET /interviews/{id}/code-submissions`), `backend/app/models/code_submission.py`, `backend/app/schemas/code_submission.py`, `frontend/app/interviews/[id]/components/CodeEditorPanel.tsx` (REQ-008)
- 테스트 유형: 단위
- 적용 Tier: High(`docs/harness/decisions.md` DEC-002 — 프로젝트 전체 선언값). Tier=High과 무관하게 이 feature는 속도 트랙 L1로 진행되어 06단계는 경량판으로 수행함(두 축은 별개, ORCHESTRATOR.md 1장 도입부).
- 적용 속도 트랙: **L1 (오케스트레이터 지정, unit-9-note.md §0)**
- 테스트 목적: 5단계(`05-unit-developer`)가 완료한 unit-9 구현이 unit-9-note.md §7의 정상 경로 인수조건(1·2·3)을 실제로 만족하는지 **06단계 자신이 독립적으로 새 서버 프로세스(및 격리 venv)를 기동해 재현**하여 증명한다. 5단계 자체 검증 기록(unit-9-note.md §6, 포트 8019 curl 로그)은 참고만 하고 그대로 승계하지 않았다 — 이번 06 세션은 별도 포트(8033)·별도 격리 venv(`.harness-tmp/venv_06_unit9`, DEC-027 준수)로 처음부터 다시 서버를 띄우고 회원가입부터 다시 실행했다.
- 관련 산출물: `docs/harness/units/unit-9-note.md`, `docs/harness/03-system-design.md` §3.1(CODE_SUBMISSIONS ERD)/§4.2(`/interviews/{id}/code-submissions` POST/GET)/§6.3(REQ-036), `docs/harness/04-ux-design.md` [C-07] 코드 에디터 패널, `docs/harness/traceability.md` REQ-008
- 테스트 수행자(에이전트): `06-unit-tester`
- 테스트 일시: 2026-09-19 (KST)

## 2. 테스트 범위 및 제외 범위
- 범위 (In-Scope, L1 경량판 — 정상 경로 1~2케이스로 한정):
  - TC-001: 인수조건 1·2 — `scheduled` 상태 세션에 같은 언어(python)로 코드를 2회 연속 제출(`201`)하고, 두 번째 제출이 첫 번째를 덮어쓰지 않고 새 행으로 append되는지, `GET /code-submissions`가 `submitted_at` 내림차순으로 정렬되어 첫 항목이 최신 제출본인지 확인.
  - TC-002: 인수조건 3 — 제출 이력이 없는 언어(`javascript`)로 `GET /code-submissions?language=javascript`를 호출하면 에러가 아니라 `200`과 빈 배열 `[]`이 반환되는지 확인.
  - 코드 리뷰(실행 없이 정적 확인, 별도 TC 아님): 인수조건 7(정보성) — `CodeEditorPanel.tsx`가 실제로 어떤 페이지에도 import되지 않았음을 `grep`으로 재확인(1개 파일에서만 매칭, unit-9-note.md §2-3 주장과 일치), 프런트 `LANGUAGE_OPTIONS`(11종)와 백엔드 `ALLOWED_LANGUAGES`(11종)가 값 단위로 정확히 일치함을 코드 대조로 확인, GET(언어 전환 시 복원)/POST(제출) 호출부·저장 상태 라벨(저장됨/저장 중/미저장/저장 실패) 존재를 코드 리뷰로 확인.
- 제외 범위 (Out-of-Scope) 및 사유:
  - 인수조건 4(화이트리스트 외 언어 `422`), 5(인증 없음 `401`/존재하지 않는 `interview_id` `404`), 6(타인 세션 접근 `403`) — L1 규칙상 "정상 경로 1~2케이스"로 한정되며, unit-9-note.md §6-4에 이미 05단계가 curl로 실행 확인한 기록이 있어 06 범위에서 임의로 확장하지 않았다. **아직 06단계가 독립 재현하지 않은 상태**이므로 traceability.md에 L1 부채로 남긴다.
  - `CodeEditorPanel.tsx`의 실제 브라우저 렌더링/클릭·타이핑 상호작용(Monaco 마운트, 드롭다운 변경 시 실제 fetch 재실행, 저장 상태 색상 전환 등) — 이 컴포넌트가 어떤 페이지에도 배선되어 있지 않아(unit-9-note.md §2-3/§3) 06단계도 브라우저로 접근할 진입 경로가 없다. 이 환경에는 브라우저 자동화 도구도 연결되어 있지 않다(unit-4-test.md와 동일한 한계). 코드 리뷰로만 [C-07] 명세 충족 여부를 확인했고, 이는 실패로 판정하지 않는다(unit-9-note.md §7-7 지시).
  - `content` 렌더링 시점 새니타이즈(§6.3/REQ-036) — 이 유닛 책임이 아니며(unit-9-note.md §2-2), 렌더링 화면 자체가 아직 없어 검증 대상이 존재하지 않는다.

## 3. 테스트 환경
- 실행 환경: Windows 11, PostgreSQL 16(Docker, `final-project-db` 컨테이너, 포트 5544, 15시간 이상 Up 상태인 기존 컨테이너 재사용), Python venv `.harness-tmp/venv_06_unit9`(이번 06 세션이 **새로 생성**한 격리 venv — DEC-027에 따라 05단계가 만든 `venv_05_unit9`를 재사용하지 않고 독립적으로 새로 구성). FastAPI 앱을 06단계가 직접 새 프로세스로 기동(포트 8033, `uvicorn app.main:app --port 8033`, PID 40828 — 05단계가 검증에 쓴 포트(8019)와 무관한 별도 기동).
- **환경 이슈 관찰(unit-9 소관 아님, §6에도 기록)**: `venv_06_unit9`에 `backend/requirements.txt`를 그대로 설치한 뒤 서버를 기동하려 하니 `ModuleNotFoundError: No module named 'faster_whisper'`로 즉시 부팅 실패했다. 원인은 `backend/app/api/v1/interviews.py`(unit-2~4 소유)가 최근(이번 06 세션 진행 중에도 `git status`상 `backend/requirements.txt`가 동시에 "modified"로 나타남) `app.services.stt_engine`(unit-5, 병렬 진행 중)을 import하도록 바뀌었고, `code_submissions.py`가 `main.py`를 통해 그 모듈 체인을 공유하기 때문이다. unit-9 자신의 코드와는 무관한 병렬 유닛(unit-5)의 미완결 의존성이 앱 전체의 기동을 막고 있는 상태였다. 06단계 자신의 재현 의무(서버를 실제로 띄워 검증)를 지키기 위해, 이 환경 이슈를 `venv_06_unit9`(unit-9 전용, 다른 유닛과 공유 안 함)에 `pip install faster-whisper`로 보강해 앱을 정상 기동시켰다 — unit-9 코드는 전혀 수정하지 않았고, faster-whisper 자체를 기능적으로 테스트하지도 않았다(단지 import 가능하게만 함). 이 사실은 unit-9의 결함이 아니므로 §6 결함 목록에는 올리지 않되, 오케스트레이터/unit-5 담당자가 인지해야 할 공유 환경 이슈로 여기 기록한다.
- 테스트 데이터: 06단계가 이번에 새로 생성한 candidate 계정 2건(`qa06u9_cand1_<ts>@example.com`, `qa06u9_cand2_<ts>@example.com` — 2번째 계정은 unit-9 자체 테스트에는 사용하지 않았고 예비로 만들었으나 실제로는 미사용, 아래 §7 정리 대상에 포함), 신규 면접 세션 1건(candidate1 소유, `scheduled` 상태 그대로 — code-submissions는 세션 상태를 검사하지 않으므로 `/start` 불필요, unit-9-note.md §3 "선행 조건" 참고).
- 전제 조건 (Preconditions): Docker Desktop 기동 상태, `final-project-db` 컨테이너 Up, `backend/.env` 존재(`DATABASE_URL=postgresql+psycopg://final_app:final_app_pw@localhost:5544/final_project`), `alembic current`가 `b84a71b986c5 (head)`임을 재확인(재마이그레이션 불필요), 5단계 게이트1(린트)·게이트2(코드리뷰) 통과 확인됨 — unit-9-note.md §4(`ruff check .`/`npx eslint`/`npx tsc --noEmit` 전부 에러 0건)·§5(코드리뷰 체크리스트 6항목 전부 [x]), 06단계는 이를 note에서 확인만 하고 재검증하지 않음(원칙에 따름).

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-001 | 같은 세션·같은 언어로 코드 2회 제출 + append-only + 최신순 정렬 조회 (인수조건 1·2) | candidate1 회원가입·로그인 완료, `POST /interviews`로 세션 생성(`scheduled`, `id=35bfe52e-...`) | ① `curl -X POST http://127.0.0.1:8033/api/v1/interviews/{id}/code-submissions -d '{"language":"python","content":"print(1)"}'` ② 1초 대기 후 동일 엔드포인트에 `{"language":"python","content":"print(2)"}` 재호출 ③ `curl GET http://127.0.0.1:8033/api/v1/interviews/{id}/code-submissions` | ①·②: 각각 `201`과 `id`/`interview_id`/`language`/`content`/`submitted_at` 필드 포함 응답 / ③: `200`, 배열 길이 2(덮어쓰지 않고 append), `submitted_at` 내림차순 정렬로 첫 항목이 `print(2)`(최신), 두 번째가 `print(1)` | ①: `201`, `{"id":"56c713fc-...","interview_id":"35bfe52e-...","language":"python","content":"print(1)","submitted_at":"2026-09-19T06:39:24.06Z"}` — 일치 / ②: `201`, `{"id":"28dadea4-...","content":"print(2)","submitted_at":"2026-09-19T06:39:32.02Z"}` — 일치(별도 새 `id`, 첫 제출과 다른 행) / ③: `200`, `[{"id":"28dadea4-...","content":"print(2)",...},{"id":"56c713fc-...","content":"print(1)",...}]` — 배열 길이 2, 첫 항목이 더 늦은 `submitted_at`(06:39:32 > 06:39:24)의 `print(2)` — 일치 | Pass | 06단계가 직접 재현(05단계 기록 재사용 아님, 별도 포트/venv/계정). "에러 없이 실행됨"이 아니라 `id`가 서로 다르고 `submitted_at` 순서가 실제로 내림차순임을 필드 단위로 대조해 PASS 판정 |
| TC-002 | 제출 이력 없는 언어로 필터 조회 시 빈 배열(에러 아님) (인수조건 3) | TC-001의 candidate1 토큰·세션 재사용(해당 세션은 `python`만 제출됨, `javascript` 제출 이력 없음) | `curl -X GET "http://127.0.0.1:8033/api/v1/interviews/{id}/code-submissions?language=javascript"` | `200`과 빈 배열 `[]`(404/422 등 에러가 아님) | `200`, 응답 바디 `[]` — 일치 | Pass | 06단계가 직접 재현. HTTP 상태코드와 바디를 모두 확인해 "빈 배열=에러 아님"을 증명(상태코드만 보고 판정하지 않음) |

> L1 경량판(정상 경로 1~2케이스)이므로 경계값/예외 입력 케이스(화이트리스트 외 언어 422, 인증없음 401/존재하지않는 id 404, 타인세션 403)는 위 §2 제외범위에 사유와 함께 명시했다(5단계가 이미 실행한 기록은 있으나 06이 독립 재현하지 않았음을 traceability.md에 리스크로 기록).

## 5. 커버리지
L1 경량판 — 미해당.

## 6. 결함(Defect) 목록
결함 없음. 근거: TC-001·TC-002 각각 예상 결과(HTTP 상태 코드, 응답 바디의 `id`/`content`/`submitted_at` 필드값, 배열 길이·정렬 순서)를 사전에 정의하고, 실제 curl 실행 결과와 필드 단위로 1:1 대조하여 전부 일치함을 확인했다("에러 없이 실행됨"이 아니라 필드 단위 비교로 PASS 판정). 두 제출의 `id`가 서로 다르다는 것과 `submitted_at` 타임스탬프의 대소 비교로 "덮어쓰지 않고 append"와 "내림차순 정렬"을 각각 독립적으로 증명했다.

관찰사항(unit-9 결함 아님, 정보 공유 목적, §3에도 기록): 이번 세션 시작 시점에 `backend/requirements.txt`에 `faster-whisper`가 아직 없는 상태에서 `app/api/v1/interviews.py`가 이미 `app.services.stt_engine`을 import하도록 바뀌어 있어, `venv_06_unit9`에 `requirements.txt`만 설치하면 앱 전체가 부팅 실패했다(병렬 진행 중인 unit-5의 미완결 의존성). unit-9 코드와는 무관하지만 code_submissions.py도 같은 `main.py`를 통해 부팅 체인을 공유하므로 06단계의 독립 재현 의무를 이행하기 위해 `venv_06_unit9`(unit-9 전용)에 `faster-whisper`를 추가 설치해 우회했다. 오케스트레이터가 병렬 유닛 간 공유 파일(`interviews.py`, `main.py`, `requirements.txt`) 동시 편집으로 인한 이런 부팅 실패가 다른 병렬 06 세션에도 반복될 수 있음을 인지할 필요가 있다.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트 목록:
  - `.harness-tmp/venv_06_unit9/`(이번 06 세션이 새로 생성한 격리 venv, DEC-027 준수 — 다른 유닛과 공유 안 함)
  - `.harness-tmp/u9_ts.txt`, `u9_email1.txt`, `u9_email2.txt`, `u9_reg1.json`, `u9_reg2.json`, `u9_login1.json`, `u9_login2.json`, `u9_token1.txt`, `u9_token2.txt`, `u9_interview.json`, `u9_interview_id.txt`, `u9_sub1.json`, `u9_sub2.json`, `u9_list_all.json`, `u9_list_js.json`, `unit9_06_server.log` (테스트 실행용 스크래치 파일/로그)
  - 신규 생성한 DB 레코드: candidate 계정 2건(candidate2는 예비 생성 후 미사용), interview 1건, code_submissions 2건(모두 테스트 데이터, 재생성 가능) — `final-project-db` 컨테이너 자체는 다음 단위가 이어서 쓰므로 유지(unit-1/2/3/4-test.md와 동일 방침).
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): [x] 예
- 정리(삭제) 완료 여부: 완료. uvicorn 프로세스(PID 40828, 포트 8033)는 `Stop-Process -Force`로 종료 확인(종료 후 `curl`이 연결 실패(`http_code=000`)로 응답, 서버 다운 확인). DB에 생성한 candidate 계정 2건/interview 1건/code_submissions 2건은 각각 `DELETE`로 정리 완료(`DELETE 2`(code_submissions)/`DELETE 1`(interviews)/`DELETE 2`(users) 결과 확인, 자식 레코드(code_submissions)부터 순서대로 삭제해 FK 오류 없음). `.harness-tmp/venv_06_unit9/`와 위에 나열한 개별 임시 파일들은 `rm -rf`/`rm -f`로 삭제 완료, 삭제 후 `ls .harness-tmp`로 잔여물이 없음을 확인(다른 병렬 유닛들의 자산 — `venv_05_unit5`, `venv_05_unit12`, `venv_06_unit12`, `u5_*`, `unit12_*` 등 — 은 이 세션이 만든 것이 아니므로 건드리지 않았다).
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

no changes added to commit (use "git add" and/or "git commit -a")
```
  (참고: 위 목록에 보이는 modified/untracked 항목 전부가 이 06 세션이 만든 것은 아니다. 이 세션이 실제로 만들거나 건드린 것은 `docs/harness/units/unit-9-test.md`(이번에 신규 작성)와, 뒤이어 갱신할 `docs/harness/traceability.md`뿐이다. `backend/requirements.txt`(unit-5), `backend/app/services/stt_engine.py`, `unit-12/14/15/16/17/18-note.md` 등은 병렬로 동시 진행 중인 다른 유닛 세션들의 산출물이며(unit-4-test.md §7의 동일한 관찰과 같은 맥락), 이 06 세션이 만들거나 수정하지 않았다. `.harness-tmp/`는 `.gitignore`로 애초에 git 추적 대상이 아니므로 이 세션이 만들고 지운 venv/스크래치 파일은 위 목록에 나타나지 않는다.)
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: [x] 없음(이 세션 자체는 중단 없이 끝까지 수행되었다. 다만 §3/§6에 기록한 것처럼, 병렬로 진행 중인 다른 세션(unit-5)이 공유 파일(`interviews.py`/`requirements.txt`)을 동시에 수정 중이라 서버 부팅이 일시적으로 막혔던 환경 이슈를 관찰·우회했다).
- **Teardown 완료 확인됨(잔여물 없음) — 9절 PASS 판정의 전제조건 충족.**

## 8. 리스크 및 잔존 이슈
L1 경량판 — 미해당(단, 아래 07 부채 사실은 규칙에 따라 이 절이 아니라 `docs/harness/traceability.md`에 기록함).

참고(경량판 범위 밖 정보, 판정에는 영향 없음): 인수조건 4(화이트리스트 외 언어 422), 5(인증없음 401/존재하지않는 id 404), 6(타인 세션 403)은 이번 06단계가 독립 재현하지 않았고, 5단계 자체 실행 기록(unit-9-note.md §6-4)만 존재하는 상태다. `CodeEditorPanel.tsx`의 실제 브라우저 상호작용도 이 환경에 브라우저 자동화 도구가 없어 06단계가 재현하지 못했다(unit-4-test.md와 동일한 환경 제약). `content` 렌더링 시점 새니타이즈(§6.3/REQ-036)는 이 유닛 범위가 아니며, 추후 recruiter 대시보드 등이 이 값을 렌더링하는 시점에 반드시 적용해야 한다는 점도 함께 남긴다. 병렬 유닛(unit-5)의 `stt_engine` 의존성 미완결로 앱 부팅이 일시적으로 막혔던 환경 이슈(§3/§6)도 이후 단계가 인지해야 할 사항이다. 이후 07(및 L1 06 정식화) 정산 시 06단계가 직접 재현해야 할 항목이다.

## 9. 결론 및 판정
- [x] PASS — 다음 단계(05단계로 복귀, 다음 작업단위 진행) 가능 (7절 Teardown 확인 완료됨)
- [ ] CONDITIONAL PASS
- [ ] FAIL

**L1 규칙에 따른 후속 처리**: 이 unit-9-test.md는 07단계로 handoff하지 않는다. 대신 `docs/harness/traceability.md` REQ-008 행의 "단위테스트" 컬럼과 비고란에 "L1 부채 — 07(및 06 정식화) 08 착수 전 정산 필요"를 기록하고, 05단계로 돌아가 다음 작업 단위를 진행한다.

## 10. 내부 검증 (최소 2회)
L1 경량판 — 검증 생략(ORCHESTRATOR.md 1장, 내부검증 규칙B 생략 가능 조항 적용). 단, 아래는 생략 조항 하에서도 QA 원칙상 실시한 자체 재점검 기록이다:
- 1차 점검: 인수조건 1·2·3(정상 경로 범위)에 대응하는 테스트 케이스가 TC-001/TC-002로 1:1 존재하는지, 예상 결과가 unit-9-note.md §7과 03-system-design §4.2/§3.1에 근거하는지 확인 — 모두 일치. 인수조건 7(정보성, 컴포넌트 미배선)도 코드 리뷰로 별도 확인(§2 참고).
- 2차 점검: "이 결과를 다음 단계(07 정식화)에 넘겨도 되는가"를 의심하며 재검토 — TC-001에서 두 제출의 `id`가 서로 다른지(단순히 "덮어쓴 것을 응답만 다르게 보여주는 착시"가 아닌지)와 `submitted_at`의 실제 대소 비교(문자열 비교가 아닌 시각 순서)를 명시적으로 대조한 것, TC-002에서 상태코드 `200`뿐 아니라 바디가 정확히 `[]`인지(예: `null`이나 다른 형태가 아닌지)까지 확인한 것이 이 재검토의 산출물이다. 또한 앱 부팅 실패(faster_whisper 누락)를 "우회 성공"으로 조용히 넘기지 않고 원인(병렬 유닛의 공유 파일 동시 편집)을 명확히 규명해 unit-9 결함과 혼동되지 않게 기록한 것도 이 재검토에서 나온 조치다.
