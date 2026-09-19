# 테스트 결과서 (Test Result Report) — unit-17 (REQ-017, Feature H. 부가 UX)

> `templates/test-report-template.md` 사용. **속도 트랙 L1 경량판** — 5·8·10절은 미해당으로 명시, 07단계로 handoff하지 않음(ORCHESTRATOR.md 1장, `.claude/agents/06-unit-tester.md` L1 규칙). unit-1/2/3/18-test.md 선례를 따름.

## 1. 개요
- 테스트 대상: unit-17 — `backend/app/models/whiteboard.py`(`WhiteboardSnapshot`), `backend/app/schemas/whiteboard.py`, `backend/app/api/v1/whiteboard.py`(`PUT`/`GET /interviews/{id}/whiteboard`), Alembic `c1a2f5e9b7d3_v5_whiteboard_snapshots`, `frontend/app/interviews/[id]/components/WhiteboardCanvas.tsx`(독립 컴포넌트, 메인 화면 미삽입) (REQ-017)
- 테스트 유형: 단위
- 적용 Tier: **High**(오케스트레이터 지시 — Feature H 전체 Tier). Tier=High과 무관하게 이 feature는 속도 트랙 L1로 진행되어 06단계는 경량판으로 수행함(두 축은 별개, ORCHESTRATOR.md 1장 도입부). Tier=High이므로 06·07 병합 조건(Low 등급 전용) 자체가 성립하지 않는다 — 병합 대상 아님.
- 적용 속도 트랙: **L1 (DEC-003)**
- 테스트 목적: 5단계(`05-unit-developer`)가 완료한 unit-17 구현이, `unit-17-note.md` §5의 인수조건 중 정상 경로(인수조건 1~4)를 실제로 만족하는지 **06단계 자신이 독립적으로 새 서버 프로세스(격리 venv, DEC-027)를 기동해 재현**하여 증명한다. 5단계 자체 검증 기록(unit-17-note.md §4, 포트 8050)은 참고만 하고 그대로 승계하지 않는다. 아울러 5단계 보고가 API rate limit로 중도 종료되었다는 오케스트레이터 안내에 따라, note에 기술된 코드와 디스크상 실제 파일이 일치하는지도 이번 06단계에서 직접 대조 확인했다.
- 관련 산출물: `docs/harness/units/unit-17-note.md`, `docs/harness/03-system-design.md` §3(ERD `WHITEBOARD_SNAPSHOTS`)/§4.2(`PUT`/`GET /interviews/{id}/whiteboard`, DEC-024 갭4), `docs/harness/04-ux-design.md` [C-08] 화이트보드 캔버스 패널, `docs/harness/traceability.md` REQ-017, `docs/harness/decisions.md` DEC-008(REQ-021 Out-of-Scope)/DEC-027(격리 venv)
- 테스트 수행자(에이전트): `06-unit-tester`
- 테스트 일시: 2026-09-19 (KST)

### note-코드 일치 확인 (사전 점검)
- `unit-17-note.md`에 기술된 파일 목록(`backend/app/models/whiteboard.py`, `backend/app/schemas/whiteboard.py`, `backend/app/api/v1/whiteboard.py`, `frontend/app/interviews/[id]/components/WhiteboardCanvas.tsx`, `backend/app/main.py`의 라우터 등록 1줄)이 모두 디스크에 실제로 존재함을 `Read`로 직접 확인했다.
- 모델은 ERD 원문대로 `id`/`interview_id`/`canvas_json`(JSONB)/`created_at` 4개 컬럼만 가짐, note §1 서술과 일치.
- 라우터는 `PUT`(새 스냅샷 행 추가)/`GET`(최신 행 조회, 없으면 `None`)으로 구현되어 note §1 "설계서 대비 해석 결정"과 일치. `_get_own_interview`가 `interviews.py`를 import하지 않고 파일 내부에 독립 재구현되어 있음도 코드로 확인(404/403 순서까지 note 서술과 일치).
- 스키마의 `MAX_STROKES=2000`/`MAX_POINTS_PER_STROKE=5000`/`width: (0,64]`/`color` 32자 제한이 note §1 게이트2 서술과 일치.
- 프론트 컴포넌트는 `interviewId`/`accessToken` 유무에 따라 초기 상태를 `loading`/`ready`로 분기하고, 저장 버튼 `disabled={!canSave || ...}`(`canSave = Boolean(interviewId && accessToken)`)로 구현되어 note §1/§5 인수조건 6 서술과 일치. `backend/app/main.py`에 `whiteboard_router` 등록 1줄도 실제로 존재함을 확인(`app.include_router(whiteboard_router, prefix="/api/v1")`).
- **결론: note와 실제 코드는 완전히 일치한다.** rate limit로 보고 텍스트가 끊긴 것과 무관하게 산출물 자체는 온전했다.

## 2. 테스트 범위 및 제외 범위
- 범위 (In-Scope, L1 경량판 — 정상 경로 1~2케이스로 한정, 단 서로 강하게 결합된 흐름은 같은 TC 안에 포함):
  - TC-001: 인수조건 1 — 저장 전 `GET /interviews/{id}/whiteboard`가 `200`과 본문 `null`을 반환하는지.
  - TC-002: 인수조건 2·3 — `PUT`으로 stroke 1개 저장 → `GET`으로 즉시 반영 확인 → 다시 `PUT`으로 다른 색상/굵기/점 3개짜리 stroke 저장(새 `id` 발급 확인) → `GET`이 **가장 최근 스냅샷만** 반환하는지, 그리고 이전 스냅샷 행이 DB에는 그대로 남아있는지(이력 테이블 설계 검증).
- 제외 범위 (Out-of-Scope) 및 사유:
  - 인수조건 4(401/403/404)·5(422 경계값) — L1 규칙(unit-17-note.md §5 인수조건 8)에 따라 정상 경로 1~2케이스로 한정하고, 이 두 인수조건은 5단계가 이미 curl로 직접 재현한 기록(unit-17-note.md §4 항목 8~11)이 존재하므로 06단계는 새로 재현하지 않고 그대로 인용한다. 07단계(또는 06 정식화) 정산 시 06단계가 독립적으로 재현해야 할 항목으로 남긴다.
  - 인수조건 6(프론트 `WhiteboardCanvas` 컴포넌트의 저장 버튼 활성/비활성, 상태 텍스트) — 06단계 환경에 브라우저 자동화 도구(Playwright 등)가 연동되어 있지 않아 실제 렌더링/클릭 상호작용을 독립 재현할 수 없다(unit-18-test.md와 동일 사유). 대신 위 "note-코드 일치 확인"에서 소스 코드 레벨로 `canSave` 로직과 상태 분기(`loading`/`ready`/`saving`/`saved`/`error`)를 직접 대조 확인했다(§1 참고). 실제 브라우저 렌더링 검증은 07 부채로 이관한다.
  - 인수조건 7(AI 비전 분석 코드 미포함) — 실행형 테스트 대상이 아니라 코드 리뷰(grep)로 확인. `backend/app/api/v1/whiteboard.py`, `frontend/.../WhiteboardCanvas.tsx`에서 `vision|image|analy|gpt-4v|recognit|classif` 패턴 검색 결과 0건(§4 참고).
  - 동시성/부하 테스트 — 인수조건에 명시되지 않았고 L1 범위 밖.

## 3. 테스트 환경
- 실행 환경: Windows 11, PostgreSQL 16(Docker, `final-project-db` 컨테이너, 포트 5544, 기존 유닛들과 동일 컨테이너 재사용), Python venv `.harness-tmp/venv_06_unit17`(**DEC-027에 따라 06단계가 이번에 새로 만든 독립 venv — 다른 유닛과 공유하지 않음**), FastAPI 앱을 06단계가 직접 새 프로세스로 기동(포트 8071 — 5단계가 검증에 쓴 포트 8050과 무관한 별도 기동으로 5단계 결과를 그대로 승계하지 않음).
- 테스트 데이터: 06단계가 이번에 새로 생성한 candidate 계정 1건(`u17cand_<ts>@test.com`), 신규 면접 세션 1건(해당 candidate 소유, `scheduled` 상태 그대로 사용 — whiteboard API는 세션 상태와 무관하게 소유권만 검사).
- 전제 조건 (Preconditions): Docker Desktop 기동 상태, `final-project-db` 컨테이너 Up(사전 확인), `backend/.env` 존재, `alembic heads` 단일 head(`b84a71b986c5`) 확인(unit-17의 `c1a2f5e9b7d3`가 그 아래에 정상 체이닝되어 있음을 직접 확인), 5단계 게이트1(린트)·게이트2(코드리뷰) 통과 확인 — unit-17-note.md §6에서 확인했고, **06단계가 note 확인에 그치지 않고 직접 재실행해 재확인함**: `ruff check app/models/whiteboard.py app/schemas/whiteboard.py app/api/v1/whiteboard.py app/main.py` → "All checks passed!", `npx eslint "app/interviews/[id]/components/WhiteboardCanvas.tsx" lib/api.ts` → 위반 0건(§4 게이트 재확인 참고).

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-001 | 저장 전 GET은 200+null (인수조건 1) | candidate 회원가입·로그인, 면접 세션 1건 생성(`scheduled`) | `curl -H "Authorization: Bearer <token>" http://127.0.0.1:8071/api/v1/interviews/{id}/whiteboard` | HTTP `200`, 응답 본문 `null`(404 아님) | HTTP `200`, 본문 `null` — 일치 | Pass | 06단계가 직접 재현(포트 8071). 5단계 기록(포트 8050) 재사용 아님 |
| TC-002 | PUT 저장→GET 즉시반영→재PUT→GET 최신만 반환, 이력은 DB에 보존 (인수조건 2·3) | TC-001과 동일 세션 | ① `PUT .../whiteboard` `{"strokes":[{"points":[{"x":1,"y":2},{"x":3,"y":4}],"color":"#000000","width":2}]}` ② `GET .../whiteboard` ③ `PUT .../whiteboard` `{"strokes":[{"points":[{"x":10,"y":20},{"x":30,"y":40},{"x":50,"y":60}],"color":"#ef4444","width":5}]}` ④ `GET .../whiteboard` ⑤ `docker exec ... psql`로 `whiteboard_snapshots` 테이블에서 해당 interview_id의 행 수 직접 확인 | ①: `200`, `id`/`interview_id`/`strokes`(1개 stroke)/`created_at` 포함 / ②: ①과 동일 내용 / ③: `200`, ①과 **다른 새 `id`** 발급, strokes(점 3개, 색상 `#ef4444`, width 5) / ④: ③의 스냅샷만 반환(①의 내용이 아님) / ⑤: 행이 2개 남아있어야 함(이력 삭제 안 됨) | ①: `200`, `id=1e0d228d-...`, strokes 1개(`(1,2)`,`(3,4)`, `#000000`, width 2) — 일치 / ②: ①과 완전히 동일한 내용 반환 — 일치 / ③: `200`, `id=c87638e2-...`(①과 다른 새 id) — 일치 / ④: `id=c87638e2-...`(③과 동일), strokes가 점 3개·`#ef4444`·width 5 — ①의 내용이 아님, 최신만 반환 확인 — 일치 / ⑤: `psql` 조회 결과 `1e0d228d-...`, `c87638e2-...` 2개 행 모두 존재(서로 다른 `created_at`) — 일치, "PUT=새 행 추가, GET=최신 우선"이라는 note의 해석 결정이 실제 DB 상태로 증명됨 | Pass | 06단계가 직접 재현. 이력 테이블 설계(§1 note 해석 결정)를 DB 레벨까지 내려가 검증한 것이 이번 06단계의 추가 확인 사항(5단계 curl 기록에는 DB 직접 조회가 없었음) |
| TC-003 (참고, 코드 리뷰 — 실행형 테스트 아님) | AI 비전 분석 코드 미포함 (인수조건 7) | 없음(정적 코드 검색) | `Grep`으로 `backend/app/api/v1/whiteboard.py`, `frontend/.../WhiteboardCanvas.tsx`에서 `vision|image|analy|gpt-4v|recognit|classif`(대소문자 무시) 검색 | 매치 0건이어야 함(DEC-008/REQ-021 Out-of-Scope 준수) | 두 파일 모두 매치 0건("No files found") | Pass | 코드 리뷰 근거 |
| TC-004 (참고, 게이트 재확인 — 실행형 테스트 아님) | 5단계 게이트1(린트) 재확인 | 격리 venv(`.harness-tmp/venv_06_unit17`)에 `backend/requirements.txt` 설치 완료, frontend는 기존 `node_modules` 재사용 | `ruff check app/models/whiteboard.py app/schemas/whiteboard.py app/api/v1/whiteboard.py app/main.py` / `npx eslint "app/interviews/[id]/components/WhiteboardCanvas.tsx" lib/api.ts` | 둘 다 위반 0건 | ruff: "All checks passed!" / eslint: 출력 없음(위반 0건) | Pass | note가 주장한 게이트1 통과를 06단계가 직접 재실행해 재확인(note 서술만 믿지 않음) |

> L1 경량판(정상 경로 1~2케이스)이므로 인수조건 4(401/403/404)·5(422 경계값)는 이번 06단계가 독립 재현하지 않았다 — §2에 명시한 대로 5단계 자체 기록(unit-17-note.md §4 항목 8~11)을 인용하며, 이는 인수조건 8이 명시적으로 허용한 처리다. 임의로 범위를 넓히지 않되, TC-002 ⑤(DB 직접 조회)는 인수조건에 명시되지 않았지만 note의 핵심 설계 해석("이력은 남고 조회는 최신만")이 API 응답만으로는 완전히 증명되지 않는(스냅샷이 실제로 UPDATE가 아니라 INSERT인지 API 레벨에서는 간접 추론만 가능한) 위험 요소라 판단해 06단계가 자체적으로 추가한 확인이다.

## 5. 커버리지
L1 경량판 — 미해당.

## 6. 결함(Defect) 목록
결함 없음. 근거: TC-001~TC-002는 각각 예상 결과(HTTP 상태 코드, 응답 본문의 정확한 필드값·`id` 동일/상이 여부)를 사전에 정의하고, 실제 curl 실행 결과 및 DB 직접 조회 결과와 필드 단위로 1:1 대조하여 전부 일치함을 확인했다("에러 없이 실행됨"이 아니라 필드 단위 비교로 PASS 판정). TC-003(코드 리뷰)에서 AI 비전 분석 코드 혼입을 발견하지 못했고, TC-004(게이트 재확인)에서도 린트 위반을 발견하지 못했다. §1 "note-코드 일치 확인"에서도 note 서술과 실제 코드 사이의 불일치를 발견하지 못했다.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트 목록:
  - `.harness-tmp/venv_06_unit17/`(신규 격리 venv, DEC-027 준수 — 다른 유닛과 공유하지 않음)
  - `.harness-tmp/u17_cand_email.txt`, `u17_cand_reg.json`, `u17_cand_login.json`, `u17_cand_token.txt`, `u17_interview_create.json`, `u17_interview_id.txt`, `u17_get_before.json`, `u17_put1.json`, `u17_get_after1.json`, `u17_put2.json`, `u17_get_after2.json`(테스트 실행용 스크래치 파일)
  - `.harness-tmp/uvicorn_06_unit17.log`(06단계가 직접 기동한 서버 프로세스 로그, 포트 8071)
  - 신규 생성한 DB 레코드: candidate 계정 1건, interview 1건, whiteboard_snapshots 2건(모두 테스트 데이터, 재생성 가능) — `final-project-db` 컨테이너 자체는 다른 병렬 작업단위가 계속 쓰므로 유지.
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): [x] 예
- 정리(삭제) 완료 여부: 완료. 위에 나열한 `.harness-tmp/u17_*` 스크래치 파일, `uvicorn_06_unit17.log`, `venv_06_unit17/` 디렉터리 전체를 삭제함. 06단계가 기동한 uvicorn 프로세스(포트 8071, PID 35116)는 `taskkill //F //PID`로 종료 확인(종료 후 `curl`이 연결 실패, http_code=000으로 응답). DB에 생성한 whiteboard_snapshots 2건, interview 1건, candidate 계정 1건은 각각 `DELETE`로 정리 완료(`DELETE 2`/`DELETE 1`/`DELETE 1` 결과 확인, 이후 `SELECT count(*) FROM users WHERE email LIKE 'u17%'` → 0 재확인).
  - 세션 도중 강제 중단(TaskStop)이 이전에 있었다는 정황은 없었으나, 오케스트레이터 안내대로 5단계 보고가 rate limit로 중단된 이력이 있어 `.harness-tmp/` 잔여물부터 확인했다 — 확인 결과 `venv_05_unit17` 등 unit-17 관련 잔여물은 이미 없었고(unit-17-note.md §3에 기록된 대로 05단계 자신이 검증 후 정리함), 다른 유닛의 venv(`venv_05_unit12`, `venv_05_unit9`)만 남아있어 손대지 않았다.
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
	docs/harness/units/unit-14-note.md
	docs/harness/units/unit-14-test.md
	docs/harness/units/unit-16-note.md
	docs/harness/units/unit-17-note.md
	docs/harness/units/unit-18-note.md
	docs/harness/units/unit-18-test.md
	docs/harness/units/unit-3-test.md
	docs/harness/units/unit-4-note.md
	docs/harness/units/unit-4-test.md
	frontend/app/__lint_repro/
	frontend/app/admin/
	frontend/app/interviews/
	frontend/app/legal/
	frontend/app/mypage/
	frontend/app/recruiter/
	frontend/app/wcpreview-check-unit16-06/
	frontend/components/
	frontend/lib/complianceContent.ts
	frontend/tsconfig.tsbuildinfo

no changes added to commit (use "git add" and/or "git commit -a")
```
  (참고: `.harness-tmp/`는 gitignore 대상이라 위 목록에 나타나지 않는다 — 그 안의 잔여물 유무는 위 항목에서 직접 `ls`로 확인했다. 위 목록 중 이번 unit-17 06단계 세션이 만든 항목은 `docs/harness/units/unit-17-test.md`(이 파일)와 `docs/harness/traceability.md`(M, 이번 06 세션이 REQ-017 행을 갱신)뿐이다. 나머지(`code_submissions.py`, `consents.py`, `ops.py`, `recruiter.py`, `ws.py`, `frontend/app/recruiter/`, `frontend/app/__lint_repro/`, `frontend/tsconfig.tsbuildinfo`, `unit-14/16/18-note.md` 등)는 다른 병렬 작업단위가 이 세션과 동시에 진행하며 만든 산출물로, 이번 unit-17 테스트 세션이 생성/실행한 명령(curl/psql/ruff/eslint/taskkill)으로는 생성될 수 없는 것들이라 판단해 임의로 되돌리거나 삭제하지 않았다.)
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: [x] 없음 (단, 위에서 서술한 대로 이전 5단계 세션의 중단 이력에 대비해 `.harness-tmp/` 잔여물을 사전 점검함)
- **Teardown 완료 확인됨 — 9절 PASS 판정의 전제조건 충족.**

## 8. 리스크 및 잔존 이슈
L1 경량판 — 미해당(단, 아래 07 부채 사실은 규칙에 따라 이 절이 아니라 `docs/harness/traceability.md`에 기록함).

참고(경량판 범위 밖 정보, 판정에는 영향 없음): 인수조건 4(401/403/404)·5(422 경계값)·6(프론트 컴포넌트 실제 렌더링/클릭 상호작용)은 이번 06단계가 독립 재현하지 않았고, 4·5는 5단계 자체 curl 기록만, 6은 코드 레벨 대조(§1)만 확인했다. 07(및 L1 06 정식화) 정산 시 06단계가 직접 재현해야 할 항목이다.

## 9. 결론 및 판정
- [x] PASS — 다음 단계(05단계로 복귀, 다음 작업 단위 진행) 가능 (7절 Teardown 확인 완료됨)
- [ ] CONDITIONAL PASS
- [ ] FAIL

**L1 규칙에 따른 후속 처리**: 이 unit-17-test.md는 07단계로 handoff하지 않는다. 대신 `docs/harness/traceability.md` REQ-017 행의 "단위테스트" 컬럼과 비고란을 "L1 부채 — 07(및 06 정식화) 08 착수 전 정산 필요"로 갱신하고, 05단계로 돌아가 다음 작업 단위를 진행한다.

## 10. 내부 검증 (최소 2회)
L1 경량판 — 검증 생략(ORCHESTRATOR.md 1장, 내부검증 규칙B 생략 가능 조항 적용). 다만 아래 두 차례는 최소한의 자기 점검으로 실제 수행했다:
- 1차 검증(인수조건 커버리지·근거): unit-17-note.md §5의 인수조건 1~8 중, L1 범위인 1~3(정상 경로)은 TC-001·TC-002로 1:1 커버했고, 7(AI 분석 코드 미포함)은 TC-003으로, 4·5·6은 §2에 제외 사유와 함께 명시했다(임의 누락이 아니라 인수조건 8이 명시적으로 허용한 처리). TC-001·TC-002의 예상 결과는 unit-17-note.md §1의 "설계서 대비 해석 결정"(PUT=새 행 추가, GET=최신 조회) 및 03-system-design §3/§4.2, 04-ux-design [C-08]에 근거해 사전에 정의한 것이며, 실행 후 짜맞춘 것이 아니다.
- 2차 검증(다음 단계로 넘겨도 되는가 / 놓친 경계 조건 재검토): 처음에는 API 응답(HTTP 200 + 필드값)만으로 TC-002를 종료하려 했으나, "PUT이 실제로 UPDATE가 아니라 INSERT인가"라는 note의 핵심 설계 주장은 API 응답만으로는 완전히 증명되지 않는다는 점을 재검토 중 발견했다(예: 서버가 내부적으로 UPDATE 후 다른 필드만 바꿔 반환해도 API 상으로는 구분 불가). 이에 TC-002 ⑤로 `whiteboard_snapshots` 테이블을 직접 조회해 두 행이 모두 남아있음을 DB 레벨에서 확인하도록 설계를 보강했다(§4에 반영). 이 재검토가 없었다면 이력 테이블 설계라는 이 유닛의 핵심 아키텍처 결정이 실제로는 검증되지 않은 채 다음 단계로 넘어갈 뻔했다. 07단계로 넘길 때 남는 주요 미검증 경계는 401/403/404/422 에러 경로(§8)와 프론트 실제 렌더링(§8)이며, 둘 다 traceability.md/이 문서 §8에 명시했으므로 놓치지 않고 이관된다.
- 검증 로그 파일 경로: 별도 `verification-log-template.md` 파일을 생성하지 않고(L1 경량판, 검증 생략 조항 적용) 본 절과 §3·§4에 검증 내역을 직접 서술로 남겼다.
