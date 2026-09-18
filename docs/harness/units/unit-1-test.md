# 테스트 결과서 (Test Result Report) — unit-1 (REQ-001, Feature A. 인증/사용자관리)

> `templates/test-report-template.md` 사용. **속도 트랙 L1 경량판** — 5·8·10절은 미해당으로 명시, 07단계로 handoff하지 않음(ORCHESTRATOR.md 1장, `.claude/agents/06-unit-tester.md` L1 규칙).

## 1. 개요
- 테스트 대상: unit-1 — `backend/app/api/v1/auth.py`(register/login/me/refresh), `frontend/app/{register,login,page}.tsx` (REQ-001)
- 테스트 유형: 단위
- 적용 Tier: High (`docs/harness/decisions.md` 참고 — 프로젝트 전체 선언값. Tier=High이므로 규칙B 완화(2차 생략)는 이 매트릭스와 무관하게 처음부터 적용되지 않으나, 아래 "속도 트랙"에 의해 06단계 자체는 L1 경량판으로 진행함 — 두 축은 서로 다른 조건이며 ORCHESTRATOR.md 1장 도입부가 명시한 대로 트랙 선택 자체는 Tier=High에서도 막히지 않음)
- 적용 속도 트랙: **L1 (DEC-003)**
- 테스트 목적: 5단계(`05-unit-developer`)가 방금 완료한 unit-1 구현이, unit-1-note.md §4의 정상 경로 인수조건 중 핵심 흐름(회원가입, 로그인→토큰 발급→본인정보 조회)을 실제로 만족하는지 **06단계 자신이 독립적으로 재현**하여 증명한다. 5단계 자체 검증 결과(§8)는 참고만 하고 그대로 승계하지 않는다.
- 관련 산출물: `docs/harness/units/unit-1-note.md`, `docs/harness/03-system-design.md` §4.2/§6.1, `docs/harness/04-ux-design.md` [C-01]/[C-02], `docs/harness/traceability.md` REQ-001
- 테스트 수행자(에이전트): `06-unit-tester`
- 테스트 일시: 2026-09-19 (KST)

## 2. 테스트 범위 및 제외 범위
- 범위 (In-Scope, L1 경량판 — 정상 경로 1~2케이스만): unit-1-note.md §4 인수조건 중 1번(회원가입 성공)과 4·5번(로그인 성공 → 발급된 access token으로 /me 조회 성공)을 하나의 연속 플로우로 묶어 재현.
- 제외 범위 (Out-of-Scope) 및 사유:
  - 인수조건 2·3번(이메일 중복 409, recruiter 가입)과 에러 경로 전반(중복 이메일/role 422/비밀번호 422/로그인 401/토큰 없음·위조 401) — L1 규칙상 "정상 경로 1~2케이스"로 한정되며, 5단계 노트 §4·§8에 이미 curl로 실행 확인된 기록이 있어 06 범위에서 임의로 확장하지 않음(인수조건에 없는 내용을 추가하지 않는다는 원칙). 단, 이 항목들은 **아직 06단계가 독립 재현하지 않은 상태**이므로 8절에 리스크로 남긴다.
  - 인수조건 6번(프론트엔드 `/register`→`/login`→`/` 화면 흐름) — 브라우저 자동화 MCP 미연동(unit-1-note.md §3, DEC-001)으로 06단계도 동일하게 실제 클릭 기반 검증은 불가. L1 경량판 필수 범위가 아니므로 이번 06에서는 재현하지 않음(리스크로 8절에 기록).
  - refresh 엔드포인트(§2 편차1) — 정상 경로 인수조건 목록(§4)에 없는 항목이라 L1 범위 밖.

## 3. 테스트 환경
- 실행 환경: Windows 11, PostgreSQL 16(Docker, `final-project-db` 컨테이너, 포트 5544, unit-1-note.md와 동일 컨테이너 재사용 — 이미 `alembic upgrade head`로 `c74075595ceb (head)` 리비전 적용 확인), Python venv `.harness-tmp/venv_05_unit1`(05단계가 만든 격리 venv를 06이 재사용 — unit-1-note.md §8-6이 명시적으로 재사용을 허용함), FastAPI 앱을 06단계가 직접 새 프로세스로 기동(포트 8010, uvicorn, PID 28452 — 05단계가 쓴 8000번 프로세스와 무관한 별도 기동으로 5단계 결과를 그대로 승계하지 않음).
- 테스트 데이터: 06단계가 이번에 새로 생성한 계정 1건 — `qa06_1789748605@example.com` / `Passw0rd123` / name="QA Sixth" / role=candidate (05단계가 만든 기존 테스트 계정과 겹치지 않는 신규 이메일).
- 전제 조건 (Preconditions): Docker Desktop 기동 상태, `final-project-db` 컨테이너 Up, `backend/.env` 존재(JWT_SECRET_KEY 등), 5단계 게이트1(린트)·게이트2(코드리뷰) 통과 확인됨(§0 참고, unit-1-note.md §5·§6 — ruff 0건/eslint 0건/next build 성공, 코드리뷰 체크리스트 6항목 전부 [x]).

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-001 | 회원가입 정상 경로 (인수조건 1) | DB 마이그레이션 적용됨, 서버(8010) 기동 중, `qa06_...@example.com` 미가입 상태 | `curl -X POST http://127.0.0.1:8010/api/v1/auth/register -H "Content-Type: application/json" -d '{"email":"qa06_...@example.com","password":"Passw0rd123","name":"QA Sixth","role":"candidate"}'` | HTTP 201, 응답 바디에 `id`/`email`/`name`/`role`/`created_at`만 존재하고 `password_hash`/`password` 필드는 없음 | HTTP 201. 바디: `{"id":"ef4a3988-01df-4363-90a6-f9af7c4b81b1","email":"qa06_1789748605@example.com","name":"QA Sixth","role":"candidate","created_at":"2026-09-18T16:23:25.370683Z"}` — 예상 필드만 존재, password_hash 미노출 확인 | Pass | 06단계가 직접 재현. 05단계 기록 재사용 아님 |
| TC-002 | 로그인 → access token 발급 → 본인정보 조회 정상 경로 (인수조건 4·5) | TC-001로 가입한 계정 존재 | ① `curl -i -X POST http://127.0.0.1:8010/api/v1/auth/login -d '{"email":"qa06_...@example.com","password":"Passw0rd123"}'` ② 응답의 `access_token`을 `Authorization: Bearer`로 `curl http://127.0.0.1:8010/api/v1/auth/me` | ①: HTTP 200, JSON에 3-segment JWT `access_token` 포함, 응답 헤더에 `Set-Cookie: refresh_token=...; HttpOnly` 포함 / ②: HTTP 200, 응답의 email/role이 로그인한 계정과 일치 | ①: HTTP 200. `access_token` 값이 `eyJ...`.`eyJ...`.`nxo...`(점 2개, 3-segment 확인), 헤더에 `set-cookie: refresh_token=eyJ...; HttpOnly; Max-Age=604800; Path=/api/v1/auth; SameSite=lax` 포함 / ②: HTTP 200, 바디 `{"id":"ef4a3988-...","email":"qa06_1789748605@example.com","name":"QA Sixth","role":"candidate","created_at":"2026-09-18T16:23:25.370683Z"}` — email·role이 로그인 계정과 정확히 일치 | Pass | 06단계가 직접 재현. 05단계 기록 재사용 아님 |

> L1 경량판(정상 경로 1~2케이스)이므로 경계값/예외 입력 케이스는 위 §2 제외범위에 사유와 함께 명시했다(5단계가 이미 실행한 기록은 있으나 06이 독립 재현하지 않았음을 리스크로 별도 기록, §8).

## 5. 커버리지
L1 경량판 — 미해당.

## 6. 결함(Defect) 목록
결함 없음. 근거: TC-001·TC-002 각각 예상 결과(응답 코드, 응답 바디 필드 구성, 토큰 포맷, 쿠키 속성, 조회 결과의 email/role 일치)를 사전에 정의하고, 실제 curl 실행 결과와 1:1로 대조하여 전부 일치함을 확인했다("에러 없이 실행됨"이 아니라 필드 단위 비교로 PASS 판정).

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트 목록:
  - `.harness-tmp/qa06_email.txt`, `.harness-tmp/qa06_cookies.txt`, `.harness-tmp/qa06_login_full.txt` (테스트 실행용 스크래치 파일)
  - `.harness-tmp/uvicorn_06_unit1.log` (06단계가 직접 기동한 서버 프로세스 로그, 포트 8010)
  - 재사용(신규 생성 아님): `.harness-tmp/venv_05_unit1` — 05단계가 만든 venv를 그대로 재사용(unit-1-note.md §8-6에서 재사용 허용 명시). 06단계가 신규로 만든 것이 아니므로 이번 절에서 삭제 대상으로 삼지 않음(다음 단계도 재사용 가능한 공용 산출물).
  - 신규 생성한 DB 레코드: `qa06_1789748605@example.com` 계정 1건(테스트 데이터, 재생성 가능) — 별도 정리 스크립트 없이 `final-project-db` 컨테이너 자체는 다음 단위가 이어서 쓰므로 유지(unit-1-note.md §8-5와 동일 방침). 이 계정 데이터 자체는 임시 아티팩트가 아니라 애플리케이션 데이터이므로 규칙K 대상은 아니지만, 참고를 위해 기록.
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): [x] 예
- 정리(삭제) 완료 여부: 완료. `qa06_email.txt`, `qa06_cookies.txt`, `qa06_login_full.txt`, `uvicorn_06_unit1.log` 삭제함. 06단계가 기동한 uvicorn 프로세스(PID 28452, 포트 8010)는 정리 전 `Stop-Process`로 종료 확인(종료 후 `curl`이 연결 거부로 응답, 서버 다운 확인).
- 정리 후 `git status` 실행 결과 (그대로 첨부):
```
 M .gitignore
 D "00 파이널 프로젝트 계획서/AI_모의면접_프로젝트_전체흐름도.mermaid"
 M docs/harness/01-trend-analysis.md
 M docs/harness/decisions.md
?? "00 파이널 프로젝트 계획서/AI_모의면접_프로젝트_전체흐름도.md"
?? backend/
?? docs/harness/02-planning.md
?? docs/harness/03-system-design.md
?? docs/harness/04-ux-design.md
?? docs/harness/traceability.md
?? docs/harness/units/
?? docs/harness/verify-log_01-trend-analysis.md
?? docs/harness/verify-log_02-planning.md
?? docs/harness/verify-log_03-system-design.md
?? docs/harness/verify-log_04-ux-design.md
?? frontend/
```
  (이 세션 시작 시점의 git status 스냅샷과 동일 — `.harness-tmp/`는 `.gitignore`에 등록되어 있어 위 목록에 나타나지 않으며, 06단계 작업으로 인한 신규 추적대상 변경 없음. `docs/harness/units/`는 이번 unit-1-test.md 신규 작성으로 이미 untracked 상태였던 디렉터리 그대로.)
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: [x] 없음
- **Teardown 완료 확인됨 — 9절 PASS 판정의 전제조건 충족.**

## 8. 리스크 및 잔존 이슈
L1 경량판 — 미해당(단, 아래 07 부채 사실은 규칙에 따라 이 절이 아니라 traceability.md에 기록함).

참고(경량판 범위 밖 정보, 판정에는 영향 없음): 인수조건 2·3·에러경로·프론트 화면 흐름(§2 제외범위)은 이번 06단계가 독립 재현하지 않았고, 5단계 자체 실행 기록(unit-1-note.md §8)만 존재하는 상태다. 이후 07(및 L1 06 정식화) 정산 시 06단계가 직접 재현해야 할 항목으로 traceability.md에 남긴다.

## 9. 결론 및 판정
- [x] PASS — 다음 단계(05단계로 복귀, 다음 작업단위 진행) 가능 (7절 Teardown 확인 완료됨)
- [ ] CONDITIONAL PASS
- [ ] FAIL

**L1 규칙에 따른 후속 처리**: 이 unit-1-test.md는 07단계로 handoff하지 않는다. 대신 `docs/harness/traceability.md` REQ-001 행의 "단위테스트" 컬럼과 비고란을 갱신하고, 05단계로 돌아가 unit-2(다음 작업 단위)를 진행한다.

## 10. 내부 검증 (최소 2회)
L1 경량판 — 검증 생략(ORCHESTRATOR.md 1장, 내부검증 규칙B 생략 가능 조항 적용).
