# unit-22 구현 노트 — 공통 테스트 인프라: Playwright(frontend) + pytest 골격(backend) (REQ-ID 없음, DEC-030)

- 작성 에이전트: `05-unit-developer`, 작성: 2026-09-20 02:30 KST (작업 중 API 한도로 01:42경 중단, 02:21 KST 재개 — 이미 끝낸 작업은 반복하지 않고 검증만 재실행)
- 속도 트랙: **L3(일반, DEC-031)** — 06·07 정식(10섹션 전체), 규칙 B 원문(Tier=High), 부채 없음. 이 유닛은 feature가 아닌 공통 인프라이므로 07 그룹핑은 오케스트레이터 소관(DEC-029).
- 입력: `docs/harness/decisions.md` DEC-001/027/028/030/031/032, `backend/app/api/v1/auth.py`, `backend/app/schemas/user.py`, `backend/app/models/*`(FK 순서), `backend/app/core/config.py`(DB 설정 관례), `docs/harness/units/unit-7-note.md`(note 구조)
- REQ-ID: 없음 — `traceability.md` 변경 없음(공통 인프라, 지시에 따라 수정하지 않음).

## 1. 구현 범위

### A. 프런트 (Playwright)
- `frontend`에 `@playwright/test`(`^1.63.0`, 설치 버전 1.63.0)를 devDependency로 추가. 그 외 패키지 추가 없음(lockfile 신규 항목은 `@playwright/test`, `playwright`, `playwright-core` 3개뿐). `npx playwright install chromium`으로 Chrome for Testing 153.0.8010.12(+headless shell) 바이너리를 사용자 홈 캐시(`ms-playwright/`, 저장소 밖)에 받음.
- `frontend/playwright.config.ts`: `testDir: "e2e"`, `baseURL = process.env.E2E_BASE_URL ?? "http://127.0.0.1:3000"`, chromium 프로젝트 하나, **`webServer` 미설정**(DEC-028), `outputDir: "test-results"`, HTML 리포트 `playwright-report/`(open: never).
- `frontend/e2e/smoke.spec.ts`: Next 앱 없이 (1) `page.setContent`로 한국어 렌더/DOM 조회/클릭·스크립트 실행/바운딩박스/스크린샷 파일 생성, (2) 로컬 정적 HTML `file://` 로드 + `navigator.userAgent`가 Chrome. 산출물은 `testInfo.outputPath()` 아래에만 쓴다.
- `frontend/package.json` scripts: `"test:e2e": "playwright test"` 추가.
- 기존 앱 소스 수정 없음. `next dev/build/start` 실행 없음(unit-20의 `.next` 보호).

### B. 백엔드 (pytest)
- `backend/requirements-dev.txt`: `pytest>=9.1,<10`, `httpx>=0.28,<0.29` 추가(기존 `ruff>=0.16,<0.17`의 범위 표기 관례). 설치 확인 버전: pytest 9.1.1, httpx 0.28.1, psycopg 3.2.13(이미 `requirements.txt`가 `psycopg[binary]>=3.2,<3.3`로 명시).
- `backend/pyproject.toml`: `[tool.pytest.ini_options] testpaths = ["tests"]` 추가(기존 ruff 설정 그대로).
- `backend/tests/`
  - `conftest.py`: 세션 스코프 `api`(httpx.Client, `API_BASE_URL` 기본 `http://127.0.0.1:8000`, 서버 미기동이면 원인과 함께 즉시 실패) + 세션 스코프 `account_factory`(종료 시 **그 세션이 만든 계정만** 정리, DB에서 찾은 수가 만든 수보다 적으면 오류).
  - `support/accounts.py`: 마커 이메일 `harness_test_<uuid4>@harness-test.example`, 랜덤 비밀번호, candidate/recruiter 가입·로그인 헬퍼, `AccountFactory`.
  - `support/cleanup.py`: 정리 헬퍼(라이브러리 `cleanup_test_data(emails=None, dry_run=False)` + CLI `python -m tests.support.cleanup`). psycopg 직접 사용(앱과 같은 드라이버), 접속 정보는 env `DATABASE_URL` -> 없으면 `backend/.env`(앱과 같은 관례), 하드코딩 없음.
  - `test_smoke.py`: 6개 케이스(§7 참고).
- `backend/app/**`는 읽기만 했다(수정 없음).

### C. 문서·설정
- `docs/harness/test-infra.md` 신규: 실행 방법(백엔드/프런트), 디렉터리 규약, 테스트 데이터 규약, 서버 PID 규칙, `.next` 직렬화 규칙, 06/07/08 재사용 방법.
- `.gitignore`: `backend/.pytest_cache/`, `frontend/test-results/`, `frontend/playwright-report/`, `frontend/blob-report/` 병합(기존 항목 보존).

## 2. 설계서(지시서) 대비 편차 (사유 포함)

| # | 편차 | 사유 | 되돌리기 난이도 |
|---|---|---|---|
| 1 | 마커 이메일 도메인을 지시서의 `@harness-test.invalid`가 아니라 **`@harness-test.example`**로 함 | 앱의 `RegisterRequest.email`이 `EmailStr`이고 email-validator가 `.invalid`를 예약 TLD로 거부한다(pydantic 검증으로 실측: "special-use or reserved name", 가입이 422가 됨). `.invalid`로는 계정을 만들 수 없어 지시의 목적(고유 마커 계정)을 달성할 수 없다. `.example`(RFC 2606)은 같은 예약 도메인이라 실메일이 존재하지 않는다. 앱 코드를 바꾸지 않는 쪽을 택함 | 낮음 — `accounts.MARKER_DOMAIN` 상수 한 곳 |
| 2 | 지시서의 `GET /users/me` 대신 **`GET /api/v1/auth/me`**로 왕복 검증 | `backend/app/api/v1/*`를 전수 확인한 결과 `/users/me`는 존재하지 않는다(`/users/me/consents`, `/users/me/biometric-data`, `/users/me/deletion-requests`만 있음). 지시가 "auth.py와 unit-1 노트로 계약 확인"이라 했으므로 실제 계약을 따름. 해석이 갈리는 사안이 아니라 지시서 표기 오류라 규칙 A 질문 대상이 아니라고 판단 | 낮음 |
| 3 | `pyproject.toml`에 pytest 설정 섹션 추가, `backend/tests/__init__.py`·`support/` 패키지 구성 | 지시에 명시되진 않았으나 `from tests.support...` import와 `testpaths`가 `backend/`에서 동작하려면 필요한 최소 설정. 플러그인 추가 없음 | 낮음 |
| 4 | 정리 헬퍼가 "비-마커 면접이 마커 채용담당자/템플릿을 참조"하면 삭제 대신 **중단** | 실사용자 데이터를 지우거나 참조를 끊는 것보다 안전. 지시의 "오삭제 방지" 취지의 추가 안전장치 | 낮음 |
| 5 | 프런트 스펙이 계정을 만들 때 쓸 Node용 정리 헬퍼는 만들지 않음 | 지시 범위 밖(프런트 스모크는 계정 불필요). `test-infra.md` §5.3에 규약(백엔드 CLI 호출)과 "첫 프런트 feature 스펙 작성 유닛이 필요 시 만든다"를 명시 | 낮음 |

## 3. 수동 확인 필요 부분 (06단계 테스터가 알아야 할 것)

- **서버는 자동 기동되지 않는다.** 백엔드 pytest 실행 전에 06이 직접 uvicorn을 자기 포트/PID로 띄워야 한다(`test-infra.md` §4). DB 컨테이너 `final-project-db`(5544)가 떠 있어야 하고 `DATABASE_URL`(또는 `backend/.env`)이 그 서버와 같은 DB를 가리켜야 한다. Redis/Celery는 스모크에 불필요.
- pytest 러너 venv는 `pytest`, `httpx`, `psycopg[binary]`, `ruff`만 설치한 경량 venv로 충분(전체 `requirements.txt`의 torch 등 불필요). `requirements-dev.txt`를 통째로 설치하면 `-r requirements.txt` 때문에 대용량이 들어온다.
- Windows Git Bash 콘솔(cp949)에서는 정리 헬퍼의 한국어 출력이 깨져 보일 수 있다(`PYTHONUTF8=1`로 완화). 출력 내용 자체의 문제는 아니다(pytest `capsys` 검증은 통과).
- **`frontend/tsconfig.tsbuildinfo`는 이 유닛의 변경이 아니다.** tracked 생성물이며 `tsc` 실행 때마다 바뀐다. 이 유닛은 `--incremental false`로 tsc를 돌렸고, 작업 중 생긴 변경을 `git checkout`으로 한 번 되돌렸으나 현재 `git status`의 ` M frontend/tsconfig.tsbuildinfo`는 병렬 유닛(unit-20) 쪽 실행으로 다시 생긴 것으로 판단한다(다른 프런트 파일도 같이 수정 중).
- 브라우저 자동화가 실제 앱 화면(`localhost:3000`)에 대해 동작하는지는 이 유닛에서 검증하지 않았다(Next 실행 금지 지시). 스모크는 "브라우저가 뜨고 렌더링한다"만 증명한다.
- 정리 헬퍼의 FK 순서는 `alembic/versions`의 현재 8개 테이블 기준이다. 이후 유닛이 `users`/`interviews`를 참조하는 새 테이블(예: 리포트)을 추가하면 `support/cleanup.py`에 추가해야 한다(누락 시 롤백되어 오삭제 없이 실패).

## 4. 게이트 1 — 정적 분석/린트

재개 후(2026-09-20 02:2x KST) 전부 다시 실행한 결과:
- `cd backend && ruff check tests`(venv_05_unit22의 ruff 0.16.8, 프로젝트 `pyproject.toml` 설정) -> `All checks passed!`
- `cd frontend && npm run lint`(eslint .) -> **에러 0건**, 경고 1건: `app/interviews/new/page.tsx:57` `@next/next/no-html-link-for-pages`(이 유닛이 만든 파일이 아니며 기존 코드, 수정 대상 아님). 이 유닛 파일만 별도 검사(`npx eslint e2e playwright.config.ts`) -> 출력 없음, exit 0.
- `cd frontend && npx tsc --noEmit --incremental false` -> exit 0, 출력 없음(e2e/·playwright.config.ts 포함, `tsconfig.json`의 `**/*.ts` include에 이미 포함되어 설정 수정 불필요). 재개 시점에 unit-20이 프런트를 수정 중이었으나 이 실행 시점에는 타입 오류가 없었다.
- 포매터(prettier 등) 설정은 저장소에 없다 -> 해당 없음(있는데 건너뛴 것이 아님).

## 5. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/지시서 명세와 실제 구현 일치 — §2에 편차 5건과 사유 기록.
- [x] 에러 처리 누락 경로 없음 — 서버 미기동 시 `api` 픽스처가 원인 메시지와 함께 실패(실측: 포트 8399로 실행해 ERROR 확인). 가입/로그인 실패는 `HarnessApiError`, 정리 헬퍼는 `CleanupError`/`UnsafeCleanupTarget`로 승격, 예외를 삼키는 코드 없음.
- [x] 시스템 경계 입력 검증 — 정리 헬퍼 인자(이메일)를 정규식 전체 일치로 검증 후에만 DB 접근, `LIKE` 조회 결과도 재검증, SQL은 전부 바인딩 파라미터(테이블명은 코드 상수). API 응답은 상태코드 검사 후 사용.
- [x] 하드코딩된 시크릿/자격증명 없음 — DB URL은 env/`.env`, 테스트 비밀번호는 `secrets.token_urlsafe(16)` 랜덤 생성.
- [x] 신규 외부 의존성 실존 확인 — `@playwright/test`(`npm install -D` 성공, `npm ls @playwright/test` = 1.63.0, next의 peer도 deduped), `pytest`(9.1.1)/`httpx`(0.28.1)는 `pip install`로 실제 설치 확인. psycopg는 기존 의존성. 그 외 패키지 추가 없음.
- [x] 범위 외 변경 없음 — `backend/app/**`, `frontend/app|components|lib/**`, `traceability.md`, `decisions.md`, `02-planning.md` 미수정. 변경 파일은 §1 목록뿐.

## 6. 로컬 최소 동작 확인 (실제 실행 요약)

1. `npm install -D @playwright/test` -> 3 packages added, 취약점 0. `npx playwright install chromium` -> exit 0.
2. `npm run test:e2e` -> `2 passed`(setContent 스모크, file:// 스모크). 생성된 스크린샷 PNG를 열어 한국어 제목("AI 모의면접 하네스 스모크"), 버튼, 클릭 후 "시작됨" 텍스트가 실제로 렌더링됨을 육안 확인. 재개 후 재실행에서도 2 passed.
3. 자기 서버: `.harness-tmp/venv_05_unit7`의 python을 읽기 전용으로 사용해 포트 8322에 uvicorn 기동(런처 PID 30052, 리스너 PID 28476 기록). `API_BASE_URL=http://127.0.0.1:8322 pytest` -> `6 passed`(최초 실행과 재개 후 재실행 모두).
4. **FK 순서 실측(임시 시나리오, 저장소에 남기지 않음)**: 마커 지원자·채용담당자 2명에 대해 `rubric_templates`, `interviews`(템플릿 참조), `transcripts`, `code_submissions`, `whiteboard_snapshots`, `consents`, `deletion_requests`를 DB에 직접 삽입 -> `dry_run` 건수(각 1, users=2) -> 실삭제 시 동일 건수 삭제, 재실행은 `대상 없음`(멱등), 종료 후 마커 계정 잔여 0. 또 실사용자(비마커) 면접이 마커 채용담당자를 참조하도록 임시 삽입한 상태에서 `UnsafeCleanupTarget`으로 중단됨을 확인(삽입한 임시 면접 행은 id로 삭제, 실사용자 계정·데이터는 변경 없음).
5. CLI: `python -m tests.support.cleanup --all --dry-run` -> `대상 없음 (users=0)` exit 0(테스트 후 DB에 마커 계정 잔여 없음). `--email real@example.com` -> 거부 메시지, exit 1.
6. 정리: 자기 uvicorn 두 PID(28476, 30052)만 `Stop-Process -Id`로 종료(`/IM` 사용 없음), 8322 LISTEN 소멸 확인. 자기가 만든 `.harness-tmp/venv_05_unit22`, `u22_*` 로그/PID 파일, `frontend/test-results`, `frontend/playwright-report`를 삭제. `.harness-tmp/`의 기존 잔여물(다른 venv/로그)과 Docker 컨테이너는 건드리지 않음. `git status` 기준 이 유닛 변경(`.gitignore`, `backend/pyproject.toml`, `backend/requirements-dev.txt`, `backend/tests/`, `docs/harness/test-infra.md`, 이 노트, `frontend/e2e/`, `frontend/package.json`, `frontend/package-lock.json`, `frontend/playwright.config.ts`) 외 잔여물 없음(나머지는 unit-7·unit-20 등 병렬 유닛의 변경).

## 7. 6단계 인수조건 (Acceptance Criteria) — L3 정식

**사전 조건**: 06이 (a) `final-project-db`가 떠 있음을 확인, (b) 경량 venv `.harness-tmp/venv_06_unit22`를 새로 만들어 `pip install pytest httpx "psycopg[binary]>=3.2,<3.3" "ruff>=0.16,<0.17"`, (c) 앱 서버용 venv(기존 venv를 수정하지 말고 읽기 전용 실행 또는 자기 것을 생성)로 uvicorn을 **자기 포트·자기 PID**로 기동해 PID를 기록. 종료 시 자기 PID만 종료하고 자기 venv 삭제.

프런트(백엔드/Next 불필요):
1. `cd frontend && npm ls @playwright/test` -> `@playwright/test@1.63.0` 표시.
2. `npm run test:e2e` -> `2 passed`, exit 0. 실행 후 `frontend/test-results/**/smoke-setcontent.png`가 존재하고 크기 > 0.
3. `npm run lint` -> 에러 0건(경고는 기존 `interviews/new/page.tsx` 1건). `npx eslint e2e playwright.config.ts` -> 출력 없음. `npx tsc --noEmit --incremental false` -> exit 0. (unit-20의 미완성 코드 때문에 전체 lint/tsc가 실패하면 실패 위치가 `e2e/`·`playwright.config.ts`인지 분리해 판정하고, 타 유닛 파일 오류는 이 유닛의 결함으로 기록하지 말 것.)
4. 설정 검증: `playwright.config.ts`에 `webServer`가 없고 `E2E_BASE_URL` 미설정 시 baseURL이 `http://127.0.0.1:3000`. 존재하지 않는 `E2E_BASE_URL`을 줘도 스모크는 통과(앱 비의존).
5. 부정 경로: `e2e/smoke.spec.ts`의 기대 텍스트를 임시로 틀리게 바꾸면 테스트가 실제로 실패해야 한다(가짜 통과 방지). 확인 후 원복(이 파일은 06이 수정한 채로 두지 말 것).

백엔드:
6. `cd backend && API_BASE_URL=http://127.0.0.1:<포트> <venv>/Scripts/python.exe -m pytest -v` -> `13 passed`(재작업 후; 최초 인수 시점은 6 passed): `test_smoke.py` 6개(`test_health`, `test_register_login_me_roundtrip[candidate]`, `[recruiter]`, `test_marker_email_format`, `test_cleanup_refuses_non_marker_email`, `test_cleanup_deletes_only_scoped_marker_account`) + 재작업으로 추가된 `test_cleanup_helper.py` 7개(DB·서버 불필요). `-s`로 실행하면 `[harness cleanup] 삭제 예정: ... users=N` 형태의 건수 출력이 보인다.
7. 실행 전후로 `python -m tests.support.cleanup --all --dry-run`이 `users=0`(병렬 유닛이 마커 계정을 쓰는 중이면 그 수만큼 남을 수 있으니 자기 계정이 없는지만 확인). 세션 종료 후 DB에 이번 실행이 만든 마커 계정이 남아 있으면 결함.
8. 서버 미기동(`API_BASE_URL`을 죽은 포트로 지정) -> `api` 픽스처가 "API 서버(...)에 연결할 수 없습니다" 메시지로 ERROR(조용한 스킵/통과 금지).
9. 안전장치: `python -m tests.support.cleanup --email real@example.com` -> exit 1, DB 변경 없음. 마커 형식이지만 존재하지 않는 이메일 -> `대상 없음`, exit 0. 실사용자 계정·데이터 건수(`SELECT count(*) FROM users WHERE email NOT LIKE 'harness\_test\_%'`)가 테스트 전후 동일.
10. FK 연쇄: 마커 계정에 대해 `interviews`/`transcripts`/`code_submissions`/`whiteboard_snapshots`/`consents`/`deletion_requests`/`rubric_templates`를 DB에 직접 삽입한 뒤 `cleanup_test_data`가 FK 위반 없이 전부 삭제하고 건수가 삽입 수와 일치(본 노트 §6-4와 같은 시나리오, 임시 스크립트는 `.harness-tmp/`에서만 쓰고 삭제).
11. `ruff check tests`(backend에서) -> `All checks passed!`. 
12. Teardown 후 `git status`에 이 유닛 변경 외 잔여물 없음, `backend/.pytest_cache`·`frontend/test-results`·`frontend/playwright-report`는 gitignore 대상임을 `git check-ignore -v`로 확인.
13. 회귀 관점: 이 유닛은 기존 앱 코드를 바꾸지 않았으므로, `git diff --stat -- backend/app frontend/app frontend/components frontend/lib`에 이 유닛 기인 변경이 없어야 한다(타 유닛 변경은 노트 §6-6 참고).

## 8. 재작업 이력 (06 CONDITIONAL PASS -> DEC-033에 따른 5단계 재작업)

- 재작업 시각: 2026-09-20 03:09:23 KST (`05-unit-developer`). 입력: `docs/harness/units/unit-22-test.md` §6(DEF-001~003, 모두 Low/Open), §8. 06은 TC-053/054/055만 재검증하면 된다(나머지 TC는 아래 §8-4 이외의 코드가 바뀌지 않아 유효).

### 8-1. 변경 내용과 근거
| 결함 | 변경 | 근거 |
|---|---|---|
| DEF-001 (DB 불통 시 무기한 대기) | `backend/tests/support/cleanup.py`: `_connect()` 신설, `psycopg.connect(url, connect_timeout=CONNECT_TIMEOUT_SECONDS)`(5초). `psycopg.OperationalError`는 `CleanupError("DB에 연결할 수 없습니다 (제한 5초): ...")`로 승격, 그 외 `psycopg.Error`(DSN 파싱 오류 등)는 원문을 싣지 않고 예외 클래스명만 담은 `CleanupError`로 승격(파싱 오류 메시지가 접속 문자열/비밀번호를 되풀이할 수 있어 누출 방지). CLI는 기존 `except CleanupError` 경로로 명확한 메시지 + exit 1 | 무인(08) 실행에서 teardown이 수십~수백 초 멈추는 위험 제거. 삭제 동작은 연결 이후 코드라 변경 없음(fail-safe 유지). `account_factory` teardown도 같은 함수를 쓰므로 동일하게 빨리 실패 |
| DEF-002 (문서 불일치) | `docs/harness/test-infra.md` §5.2의 타입체크 명령을 `npx tsc --noEmit --incremental false`로 통일하고, 이유 한 줄 추가: `tsconfig.json`이 `incremental: true`라 플래그 없이 실행하면 추적되는 생성물(`frontend/tsconfig.tsbuildinfo`, `next-env.d.ts`)이 갱신되어 타 유닛 변경과 섞임(§5.4 참조) | 문서 내부 불일치 해소 |
| DEF-003 (`--all --dry-run`이 stray 1건에 전체 중단) | `cleanup_test_data`: 조회 결과 중 UUID 마커 형식이 아닌 행을 `stray`로 분리. **`dry_run=True`이면** stray를 삭제 대상(`user_ids`)에서 제외하고 정상 마커만 집계하며 `형식 불일치(stray) 마커형 계정 N건 ... : <목록>`을 출력, 반환 dict에 `stray_users` 키 추가. **`dry_run=False`이면 종전대로 삭제 없이 `UnsafeCleanupTarget`으로 중단.** CLI 종료코드: 0=정상(stray 없음), 1=실패/중단, **3=집계 정상 + stray 존재**(argparse 사용법 오류가 2라 충돌 회피). `test-infra.md` §3에 stray 동작, 종료코드, "계정은 반드시 `account_factory`(UUID 형식)로만" 문구를 눈에 띄게 추가 | 병렬 환경에서 08의 "잔여 마커 확인"이 타 에이전트의 비-UUID 계정 한 건 때문에 불가능해지는 문제 해소. 삭제 경로의 안전 계약은 그대로 |

**약화하지 않은 안전 계약**(코드 대조 + 아래 재검증으로 확인): 비마커 이메일 거부(`UnsafeCleanupTarget`, DB 접근 전), 명시 이메일 경로의 비-UUID 마커형 거부, 삭제 건수 != 조회 건수 시 롤백, 비마커 면접이 마커 계정/템플릿을 참조하면 중단, FK 의존 순서와 단일 트랜잭션, stray는 어떤 경로로도 삭제되지 않음. `--all` 실삭제는 이 재작업 검증에서 실행하지 않았다.

추가로 `backend/tests/test_cleanup_helper.py`(신규, 7 케이스)를 넣었다. 가짜 psycopg 연결을 monkeypatch해 DB·서버·실계정 없이 실패/stray 경로를 고정한다: connect_timeout 전달 + OperationalError 승격, DSN 비밀번호 비누출, CLI exit 1(DB 불통), dry-run stray 보고 + stray가 대상 id에서 제외됨, **실삭제 경로 stray 시 DELETE 미실행 + 중단**, 종료코드 0/3/1, stray만 있을 때 보고. 이유: 실삭제 stray 중단 계약을 실DB `--all` 실행 없이(타 에이전트 계정 오삭제 위험 없이) 회귀 검증하기 위함.

### 8-2. 재검증 결과 (2026-09-20, 독립 venv `.harness-tmp/venv_05_unit22`, 서버 포트 8322)
- `ruff check tests` -> `All checks passed!`
- `pytest -v`(API_BASE_URL=http://127.0.0.1:8322) -> **13 passed**(기존 6 + 신규 7).
- DEF-001: 닫힌 포트(127.0.0.1:5999)로 `--all --dry-run` -> 5.6초에 `실패: DB에 연결할 수 없습니다 (제한 5초): connection timeout expired`, exit 1(이전: 60초 초과 미종료). 127.0.0.1:1 -> 5.5초, 동일 메시지, exit 1. 잘못된 DSN(`postgresql://u:secretpw@[bad/x`) -> `DB 접속 설정이 올바르지 않습니다 (ProgrammingError)`, exit 1, 비밀번호 미출력.
- DEF-003(실DB, dry-run과 내가 만든 계정만 사용): (a) 기준선 `--all --dry-run` -> `대상 없음`, exit 0(이 시점 타 에이전트의 마커 계정은 DB에 없었음 — DB 상태를 가정하지 않고 매번 dry-run으로 확인). (b) 내가 만든 stray(`harness_test_<12hex>@harness-test.example`) + 정상 계정 1개가 있는 상태에서 `--all --dry-run` -> stray 1건을 이메일과 함께 보고 + `users=1` 집계, **exit 3**. (c) `--email <정상> --dry-run` -> exit 0. (d) `--email <stray>` -> 비마커 형식 거부, exit 1. (e) 위 (b)~(d) 후 두 계정이 DB에 그대로 남아 있음(무삭제 확인). 종료 후 정상 계정은 `cleanup_test_data([email])`로, stray는 **내가 만든 정확한 이메일** 한 건만 SQL로 삭제했고 이후 `--all --dry-run`이 `users=0`, exit 0.
- 비마커 거부: `--email real@example.com` -> `마커 형식이 아닌 이메일은 정리할 수 없습니다`, exit 1.
- 프런트 코드는 이번 재작업에서 바뀌지 않았다(문서 한 줄만 변경) — 프런트 게이트 재실행 생략.

### 8-3. Teardown / 상태
- 자기 uvicorn(런처 PID 21348, 리스너 PID 21460)만 `Stop-Process -Id`로 종료, 8322 리스너 0 확인. 자기 venv `.harness-tmp/venv_05_unit22`, `u22_*` 로그/PID 파일, `backend/.pytest_cache`, `frontend/test-results`, `frontend/playwright-report` 삭제. 스크래치 시나리오 스크립트는 저장소 밖. 타 에이전트의 마커 계정·`.harness-tmp` 기존 잔여물은 건드리지 않았고, `--all` 실삭제는 실행하지 않았다.
- 이번 재작업의 변경 파일: `backend/tests/support/cleanup.py`, `backend/tests/test_cleanup_helper.py`(신규), `docs/harness/test-infra.md`, 이 노트. `git status`에 그 외 이 유닛 기인 잔여물 없음.

### 8-4. 06 재검증 안내
- TC-053(DEF-001): 닫힌/응답 없는 주소로 CLI 실행 시 ~5초 내 CleanupError 메시지 + exit 1인지 확인.
- TC-054(DEF-002): `test-infra.md` §5.2에 `--incremental false`와 사유가 있고 §5.4와 일치하는지 확인.
- TC-055(DEF-003): stray 포함 상태에서 `--all --dry-run`이 정상 건수 + stray 목록을 출력하고 exit 3인지, stray 없으면 exit 0인지, 실삭제 경로 중단은 `test_sweep_real_run_with_stray_aborts_without_deleting`/`test_cli_exit_codes_for_stray_and_clean`으로 확인(실DB에서 `--all` 실삭제는 병렬 에이전트 계정 오삭제 위험이 있어 실행하지 말 것).
- 인수조건 §7-6의 pytest 기대값이 `6 passed`에서 `13 passed`로 바뀌었다.
