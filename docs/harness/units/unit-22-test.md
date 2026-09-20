# 테스트 결과서 — unit-22 (공통 테스트 인프라: Playwright(frontend) + pytest 골격(backend), REQ-ID 없음, DEC-030)

> 버전: **v5** (2026-09-20 07:21~07:5x KST, 05 재작업[DEC-033, DEF-001/002/003 수정] 후 06 재검증본). 이력: v0 초안 → v1(1차) → v2(2차) → v3(3차) → v4(4차·5차 확정, 최초 실행 판정 **CONDITIONAL PASS**) → **v5(재작업 후 재검증, 규칙 F.2에 따라 검증을 처음부터 재수행)**. 규칙 B 검증 로그는 `verify-log_unit-22-test.md`에 **기존 기록을 보존한 채 이어서**(6차~) 기록한다.

## 1. 개요
- 테스트 대상 (모듈/기능/업무단위/전체 시스템 중 명시): **공통 테스트 인프라 모듈** — `frontend/playwright.config.ts`, `frontend/e2e/smoke.spec.ts`, `frontend/package.json`(`@playwright/test`, `test:e2e`), `backend/tests/**`(`conftest.py`, `support/accounts.py`, `support/cleanup.py`, `test_smoke.py`), `backend/requirements-dev.txt`, `backend/pyproject.toml`(pytest 설정), `.gitignore` 4개 항목, `docs/harness/test-infra.md`. (feature가 아닌 공통 인프라 — DEC-029. 앱 기능 자체는 대상 아님)
- 테스트 유형: **단위**(테스트 인프라 자체의 단위 검증. 07 대상 아님 — 02-planning v3)
- 적용 Tier (Low/Standard/High, ORCHESTRATOR.md 1장 참고): **High**(DEC-002)
- 적용 속도 트랙 (L1~L5): **L3(일반)**(DEC-031) — 10개 절 전부 작성, 규칙 B 원문(최소 2회)
- 테스트 목적: 05단계가 자체 실행으로 "통과했다"고 기록한 인프라를, 06이 **처음부터 독립 재현**해 (a) 브라우저가 실제로 뜨고 렌더링하며 **가짜 통과가 아님**(부정 경로)을 증명하고, (b) pytest 스모크와 **DB 정리 헬퍼가 실사용자 데이터를 절대 건드리지 않고**(비마커 거부·참조 시 중단·롤백) 마커 계정과 FK 연쇄만 정확히 지우는지 증명하며, (c) 인수조건 13개를 TC와 1:1로 추적한다. 07/08이 이 인프라를 신뢰하고 재사용해도 되는지 판정한다.
- 관련 산출물: `docs/harness/units/unit-22-note.md`(§2 편차 5건, §5 게이트, §7 인수조건 13개), `docs/harness/test-infra.md`, `docs/harness/decisions.md` DEC-027/028/029~032, `docs/harness/units/unit-1-note.md`(auth 계약), `backend/app/api/v1/auth.py`, `backend/app/schemas/user.py`, `backend/app/models/*`. 선례 형식: `docs/harness/units/unit-5-test.md`
- 테스트 수행자(에이전트): `06-unit-tester`
- **변경 이력 / 재검증 개요 (v4 → v5)**: v4 판정은 CONDITIONAL PASS(인수조건 13개 PASS + Low 결함 3건 Open)였다. 오케스트레이터가 05 재작업을 요청·완료했다(DEC-033; 변경: `backend/tests/support/cleanup.py` 수정, `backend/tests/test_cleanup_helper.py` 신규 7케이스, `docs/harness/test-infra.md` §3·§5.2, `docs/harness/units/unit-22-note.md` §7-6·§8). 규칙 F.2에 따라 **DEF-001~003에 해당하는 TC-053/054/055를 재검증**하고, **`cleanup.py` 자체가 바뀌었으므로 정리 헬퍼 안전 계약 TC를 회귀 실행**했으며, 신규 테스트 7건이 계약을 실제로 고정하는지 변이(mutation)로 확인했다. 재검증하지 않은 항목과 그 근거는 2절에 명시한다.
- 테스트 일시: 최초 실행 2026-09-20 02:27:39 ~ 약 03:05 KST(v4) / **재검증 2026-09-20 07:21:58 ~ 07:5x KST(v5)** (재검증 중 03:1x KST에 API 한도로 중단 후 07:21 KST에 재개 — 03:1x까지는 변경 범위 확인만 했고 재검증 실행 결과는 남기지 않아 07:21 이후 전부 새로 실행함) (시각은 PowerShell `TimeZoneInfo` 'Korea Standard Time' 기준)

## 2. 테스트 범위 및 제외 범위
- 범위 (In-Scope): unit-22-note.md §7 인수조건 13개 전부(AC1~AC13) + 지시된 독립 재현 항목 5가지: (1) 브라우저 렌더링 + 부정 경로, (2) pytest 스모크·정리 헬퍼(dry-run=실삭제, 멱등, 비마커 거부, 비마커 면접 참조 시 `UnsafeCleanupTarget`, 건수 불일치 롤백, FK 순서 코드 대조), (3) SQL 바인딩·자격증명 env 전용·서버 자동 기동 없음·마커 도메인(편차#1 실측), (4) `.gitignore` 4항목·`requirements-dev.txt`·ruff/lint/tsc 직접 재실행, (5) `test-infra.md` 절차 그대로 따라 하기. 편차 5건 전부의 타당성 검증.
- **재검증(v5) 추가 범위**: TC-053(닫힌 포트·응답 없는 주소·오설정 DSN에서 약 5초 내 명확한 메시지+exit 1, 비밀번호 비누출), TC-054(test-infra §5.2/§5.4 일치 + 문서 명령 실행), TC-055(stray 상태별 exit 0/3/1, 목록·정상 건수, 실삭제 경로 stray 시 삭제 없이 중단), 정리 헬퍼 안전 계약 회귀(TC-057), 신규 테스트 7건 민감도(TC-058), pytest 13 passed·ruff(TC-056), SQL 바인딩·자격증명·서버 자동 기동(TC-059), 실사용자 데이터 무변화(TC-060).
- **재검증 생략 항목과 근거(영향 범위 판단)**: (a) 프런트 Playwright 스모크·lint·eslint 재실행 — 재작업은 프런트 파일을 바꾸지 않았다(`frontend/e2e/smoke.spec.ts` sha256 `3bc4ef90…`, `playwright.config.ts` `d2cd4309…`가 v4 측정값과 동일, `package.json` 수정시각 01:37 그대로). 다만 문서 §5.2가 바뀐 `tsc` 명령은 **문서대로 실제 실행**했다(TC-054). (b) `.gitignore`·`requirements-dev.txt`·`pyproject.toml`·`test_smoke.py`·`conftest.py`·`accounts.py` 관련 TC — 파일 해시/수정시각 불변(`be841a8c…`, `86709eb2…`, `5582a191…`). 단 이 파일들을 통해 실행되는 pytest 스모크는 TC-056에서 다시 실행했다. (c) AC5 부정 경로, AC8 죽은 포트 ERROR, 편차 #1/#2 실측 — 코드/서버 계약 불변이며 TC-057의 H 시나리오(.invalid 422, /users/me 404)로 축약 회귀. (d) `--all` 실삭제는 지시에 따라 실행하지 않음(실DB에서의 "실삭제 경로 stray 중단"은 가짜 연결 테스트 + 변이 M1로 검증, 코드 정독으로 삭제 이전 위치 확인).
- 제외 범위 (Out-of-Scope) 및 사유:
  - **`python -m tests.support.cleanup --all`(실삭제)**: 병렬 에이전트(v4: 06 unit-7, v5: unit-19 06·unit-20 06)의 마커 계정을 지울 수 있어 금지됨(지시). `--all`은 `--dry-run`으로만 실행, 실삭제는 자기 세션이 만든 이메일 범위(`--email`/라이브러리 호출)로만 수행.
  - **실제 앱 화면(`localhost:3000`) 대상 e2e**: `next dev/build/start` 실행 금지(unit-20의 `.next` 보호). 스모크는 "브라우저가 뜨고 렌더링한다"만 증명하며, 특정 앱 화면이 정상이라는 증명은 아니다(test-infra.md §6-6과 동일 전제).
  - **Node용 프런트 정리 헬퍼**: note §2 편차#5로 이 유닛 범위 밖(첫 프런트 feature 스펙 작성 유닛이 필요 시 작성). test-infra.md §5.3에 그 사실이 명시되어 있음을 확인(TC-051).
  - **브라우저 다중 엔진(Firefox/WebKit)**: 설계상 chromium 1개만(note §1-A).
  - **부하/동시성 테스트**: 인프라 골격 유닛이라 해당 없음(단, 병렬 에이전트와 같은 DB를 실제로 공유한 상태에서 실행했으므로 마커 격리는 실환경에서 자연 검증됨 — TC-021).
  - **`.next` 산출물·`frontend/tsconfig.tsbuildinfo`**: 이 유닛의 변경이 아님(타 유닛 생성물). 사실만 기록(7절).

## 3. 테스트 환경
- 실행 환경 (OS/런타임/브라우저/DB 등): Windows 11(10.0.26200), Git Bash + PowerShell. Python 3.13.9(**신규** 경량 venv `.harness-tmp/venv_06_unit22`: pytest 9.1.1, httpx 0.28.1, psycopg 3.2.13 + psycopg-binary, ruff 0.16.8, (커버리지 측정용) coverage — 전체 `requirements.txt` 미설치). Node/npm(frontend `node_modules`의 `@playwright/test` 1.63.0), Playwright Chromium: Chrome for Testing 153.0.8010.12(사용자 캐시 `%LOCALAPPDATA%\ms-playwright\chromium-1243` — **재다운로드 없음**, `npx playwright install chromium` exit 0/3초로 확인). DB: Docker `final-project-db`(5544, 기존 컨테이너 재사용, 스키마 변경 없음), Redis 미사용. 백엔드 서버: `.harness-tmp/venv_05_unit7`의 python을 **읽기 전용 실행**만(pip/삭제 없음)해 uvicorn을 **포트 8422**에 기동(런처 PID 34320 / 리스너 PID 28920, `.harness-tmp/u22t06_pids.txt`에 기록, 그 PID로만 종료 — DEC-028).
- **재검증(v5) 환경**: 06 전용 venv `.harness-tmp/venv_06_unit22`를 **새로 생성**(pytest 9.1.1, httpx 0.28.1, psycopg 3.2.13, ruff 0.16.8, coverage 7.16.1). 서버: `.harness-tmp/venv_05_unit7`의 python을 읽기 전용으로 실행해 포트 8422에 uvicorn(런처 PID 35324 / 리스너 PID 6612, `.harness-tmp/u22t06_pids.txt`). 병렬로 unit-19 06(포트 8720)·unit-20 06(포트 8620)이 같은 DB에서 UUID 마커 계정(이름 `u20 e2e` 등, 재검증 중 최대 12개)을 만들어 쓰는 중이었으며 06은 그 계정을 집계(dry-run)만 하고 삭제하지 않았다. 재검증 시작 시점 DB에는 stray가 없었다(`--all --dry-run` → `대상 없음`, exit 0; v4에서 문제였던 unit-19의 stray 3건은 그 사이 소유 측이 정리한 것으로 보임 — 06은 건드리지 않음). 실사용자 스냅샷: users 30·interviews 16·code_submissions 9·whiteboard 5·consents 18·deletion_requests 5.
- 테스트 데이터: 백엔드 스모크·독립 시나리오가 API로 만든 **마커 계정**(`harness_test_<uuid4>@harness-test.example`, 랜덤 비밀번호). 시나리오 B·F용으로 06이 만든 **비마커 canary/stray 행**(이메일 `u22t06-canary-<uuid>@example.com`, `harness_test_u22t06stray@harness-test.example`, 템플릿명 `u22t06`)은 06이 id로만 삽입/삭제하고 실행 직후 잔여 0건 확인(TC-021). FK 연쇄용 행(rubric_templates/interviews/transcripts/code_submissions/whiteboard_snapshots/consents/deletion_requests)은 SQL 직접 삽입 후 헬퍼가 삭제. **실사용자(비마커) 데이터는 어떤 테스트도 삭제·수정하지 않음**을 md5 행 스냅샷으로 검증(TC-021).
- 전제 조건 (Preconditions): (a) 5단계 게이트 확인 — note §4(ruff/lint/tsc) · §5(자체 코드 리뷰 체크리스트 6항목 전부 체크)가 통과 기록됨을 확인했고, 06이 §4의 3개 명령을 **직접 재실행**해 동일 결과 확인(TC-006~008, TC-039). (b) `docker ps`로 `final-project-db`·`final-project-redis` Up 확인. (c) 시작 시점 `git status`·`.harness-tmp` 목록·마커 계정 수(0)를 기준선으로 기록. (d) 병렬 에이전트(unit-7 06, unit-20, 시간이 지나며 합류한 unit-19, 02 문서 갱신)가 같은 DB/저장소에서 동작 중 — DB 실사용자 행 수가 내 조작 없이도 변동(내 첫 조회 users=34 → 스냅샷 시점 19, 둘 다 내가 DB에 쓰기 전. 다른 에이전트의 계정 삭제 때문)하므로, 실사용자 무변화 증명은 "스냅샷 이후 내 모든 실행이 끝난 뒤 md5 비교"로 수행.

## 4. 테스트 케이스 및 결과

### 4-1. 인수조건(AC) ↔ TC 추적표 (1:1 이상)
| AC | 내용 요약 | 대응 TC | 결과 |
|----|-----------|---------|------|
| AC1 | `npm ls @playwright/test` = 1.63.0 | TC-001, TC-002 | PASS |
| AC2 | `npm run test:e2e` 2 passed·exit 0, 스크린샷 존재·크기>0 | TC-003, TC-004, TC-005 | PASS |
| AC3 | `npm run lint` 에러 0, eslint 대상 파일 무출력, `tsc --noEmit --incremental false` exit 0 | TC-006, TC-007, TC-008 | PASS |
| AC4 | `webServer` 없음, 기본 baseURL `http://127.0.0.1:3000`, 죽은 `E2E_BASE_URL`에도 스모크 통과 | TC-009, TC-010, TC-011 | PASS |
| AC5 | 기대 텍스트를 틀리게 바꾸면 실제로 실패(가짜 통과 방지), 원복 | TC-012~TC-016 | PASS |
| AC6 | `pytest -v` 6 passed(케이스명 6개), `-s`로 건수 출력 | TC-017, TC-018, TC-019 | PASS — v5: 재작업으로 기대값이 **13 passed**(기존 6 + 신규 7)로 변경됨, TC-056에서 13 passed 확인(기존 6건은 TC-017~019에서 v4 검증) |
| AC7 | 실행 전후 마커 dry-run users=0, 이번 실행이 만든 마커 계정 잔여 없음 | TC-020, TC-021, TC-022 | PASS — v5: `--all --dry-run`이 stray가 있어도 정상 건수를 집계하고 exit 3(DEF-003 Fixed, TC-055). 자기 계정 잔여 0은 v4/v5 모두 확인 |
| AC8 | 죽은 포트 → 명확한 ERROR(조용한 스킵/통과 금지) | TC-023, TC-024 | PASS |
| AC9 | 비마커 이메일 거부 exit 1·DB 무변경, 마커형 미존재 → 대상 없음 exit 0, 실사용자 건수 전후 동일 | TC-025~TC-031, TC-037 | PASS |
| AC10 | FK 연쇄: 7개 종속 테이블 삽입 후 FK 위반 없이 전부 삭제, 건수 일치 | TC-032~TC-036 | PASS |
| AC11 | `ruff check tests` → All checks passed | TC-039, TC-040 | PASS — v5: 신규 파일 포함 `ruff check tests` 재실행 통과(TC-056) |
| AC12 | Teardown 후 git status에 이 유닛 외 잔여 없음, gitignore 대상 `git check-ignore -v` | TC-047, TC-048 | PASS |
| AC13 | 회귀: `backend/app`·`frontend/{app,components,lib}`에 이 유닛 기인 변경 없음 | TC-049 | PASS |
| (지시 3·4·5) | SQL 바인딩·자격증명·서버 자동기동 없음·편차#1/#2 실측·의존성·문서 재현·병렬 환경 | TC-038, TC-041~TC-046, TC-050~TC-060 | 아래 표. v4의 FAIL(TC-053/054/055) → **v5 재검증 PASS**(DEF-001/002/003 Fixed) + 회귀 TC-056~060 |

### 4-1b. note §2 편차 5건 판정
| # | 편차 | 06의 판정 | 근거 TC |
|---|------|-----------|---------|
| 1 | 마커 도메인 `.invalid` → `.example` | **타당(필요)** — 앱 `EmailStr`이 `.invalid`를 422로 거부함을 서버에 직접 가입 요청해 재현, `.example`은 201 | TC-044 |
| 2 | `GET /users/me` → `GET /api/v1/auth/me` | **타당** — `/users/me`는 404, openapi에 없음. 실제 계약(`/auth/me`)으로 왕복 검증 성공 | TC-045, TC-017 |
| 3 | pytest 설정(`testpaths`)·`tests` 패키지 구성 | **타당** — `backend/`·저장소 루트 어느 쪽에서 호출해도 6건 수집·통과, 플러그인 추가 없음 | TC-019, TC-050 |
| 4 | 비-마커 면접이 마커를 참조하면 삭제 대신 중단 | **타당(안전 강화)** — 실제로 실사용자 면접 참조 시 무삭제 중단(B1/B5). 다만 문구 부정확(OBS-2) | TC-035, TC-038 |
| 5 | Node용 프런트 정리 헬퍼 미작성 | **타당(범위 밖)** — 문서 §5.3에 명시, 프런트 스모크는 계정 불필요 | TC-051 |

### 4-2. 테스트 케이스 표
표기: 모든 명령은 저장소 루트 `C:\big21\vibe-coding\FINAL-PROJECT-NEW` 기준. `V`=`.harness-tmp/venv_06_unit22/Scripts/python.exe`. 백엔드 명령은 `cd backend`, env `API_BASE_URL=http://127.0.0.1:8422 PYTHONPATH=. PYTHONUTF8=1`. 06의 임시 시나리오 스크립트(`.harness-tmp/u22t06_*.py`, `.harness-tmp/u22t_neg*/`, `.harness-tmp/u22t_guard/`)는 규칙 K에 따라 7절대로 삭제했다(아래 표가 실행 근거).

| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-001 | (AC1) 설치 버전 | `frontend/node_modules` 존재 | `cd frontend && npm ls @playwright/test`; `node_modules/@playwright/test/package.json`의 version | `@playwright/test@1.63.0`(next peer deduped) | `@playwright/test@1.63.0`, `next@16.3.5 └ @playwright/test@1.63.0 deduped`, package.json version `1.63.0` | PASS | 정상 경로 |
| TC-002 | (AC1 보강) 패키지 실존·lockfile 변경 범위 | 네트워크 | `npm view @playwright/test@1.63.0 version`; `git diff frontend/package-lock.json` 의 추가 항목 열거 | registry에 실존, lockfile 신규 항목은 3개뿐 | `1.63.0` 반환. lockfile diff = `@playwright/test`, `playwright`, `playwright-core` 3개(모두 1.63.0, registry.npmjs.org resolved + sha512 integrity, `devOptional`) + root devDependencies 1줄. 그 외 추가/삭제 0 | PASS | "그 외 패키지 추가 없음"(note §1-A) 확인 |
| TC-003 | (AC2 전제) 브라우저 바이너리 재다운로드 여부 | 사용자 캐시 | `ls %LOCALAPPDATA%\ms-playwright`; `npx playwright install --dry-run chromium`; `npx playwright install chromium` | 이미 캐시에 있어 무다운로드·exit 0 | `chromium-1243`, `chromium_headless_shell-1243`, `ffmpeg-1011` 존재(1208/1234 폴더도 존재 — 출처 미확인, 이 유닛과 무관), dry-run의 install location이 모두 실존, install exit 0 / 3초(다운로드 없음) | PASS | 캐시는 저장소 밖(사용자 홈) — 규칙 K 대상 아님 |
| TC-004 | (AC2) 스모크 실행 | Next/백엔드 미기동, 3000 포트 미사용 | `cd frontend && npm run test:e2e` (3회 반복) | `2 passed`, exit 0 | 3회 모두 `2 passed (1.3~1.5s)`, exit 0(`echo $?`를 파이프 없이 확인). `setContent` 케이스·`file://` 케이스 각 ✓ | PASS | 재현성 3/3 |
| TC-005 | (AC2) 스크린샷 산출물 + 육안 렌더링 | TC-004 직후 | `find frontend/test-results -name smoke-setcontent.png -size +0`; 이미지 열람 | 파일 존재, 크기>0, 한국어 제목·버튼·클릭 후 텍스트가 실제로 그려짐 | `test-results/smoke-setContent-…-chromium/smoke-setcontent.png` **7,977 bytes**. 이미지 육안 확인: 제목 "AI 모의면접 하네스 스모크", 버튼 "면접 시작", 클릭 후 "시작됨" 렌더링(1280x720) | PASS | 브라우저가 실제로 그린 증거(문자열 비교만이 아님) |
| TC-006 | (AC3) 전체 lint | 프런트 타 유닛(unit-20)이 수정 중일 수 있음 | `cd frontend && npm run lint` | 에러 0건(경고는 기존 `interviews/new/page.tsx` 1건) | `✖ 1 problem (0 errors, 1 warning)` — `app/interviews/new/page.tsx:57 @next/next/no-html-link-for-pages` 1건뿐(이 유닛 파일 아님) | PASS | 타 유닛 오류 없음(분리 판정 불필요) |
| TC-007 | (AC3) 유닛 파일 lint + 실제 lint 대상 여부 | — | `npx eslint e2e playwright.config.ts`; `npx eslint --print-config e2e/smoke.spec.ts` / `playwright.config.ts` | 무출력·exit 0, 두 파일이 실제 설정을 받는 대상 | 무출력 exit 0. `--print-config`가 두 파일 모두 규칙 세트를 출력(=무시 대상 아님) | PASS | 가짜 통과(ignore로 lint 회피) 배제 |
| TC-008 | (AC3) 타입체크 + 유닛 파일 포함 여부 + tracked 생성물 무변경 | — | `sha256sum tsconfig.tsbuildinfo`; `npx tsc --noEmit --incremental false`; `--listFilesOnly \| grep -E "e2e\|playwright.config"`; 해시 재측정 | exit 0·무출력, 두 파일이 프로그램에 포함, buildinfo 해시 불변 | exit 0. `playwright.config.ts`·`e2e/smoke.spec.ts` 모두 포함. 해시 전후 `7321a45f…` 동일(=이 유닛/06 실행이 tsbuildinfo를 바꾸지 않음) | PASS | `tsconfig.json` include(`**/*.ts`)로 이미 포함 — 설정 수정 불필요 확인 |
| TC-009 | (AC4) `webServer` 부재 | — | `grep -n webServer frontend/playwright.config.ts`; `.harness-tmp`에 실 config를 import하는 probe로 `config.webServer` 출력 | 설정 값 없음(주석만) | grep은 3행 **주석**만 히트. probe 출력 `webServer=undefined` | PASS | 서버 자동 기동 없음(DEC-028) |
| TC-010 | (AC4) 기본 baseURL | `E2E_BASE_URL` 미설정 | probe 스펙이 fixture `baseURL` 출력 | `http://127.0.0.1:3000` | `PROBE baseURL=http://127.0.0.1:3000` | PASS | |
| TC-011 | (AC4/예외) 존재하지 않는 `E2E_BASE_URL`에도 스모크 통과 | — | `E2E_BASE_URL=http://127.0.0.1:1`로 probe와 `npx playwright test` | baseURL 반영(`…:1`), 실제 스모크는 `2 passed` | `PROBE baseURL=http://127.0.0.1:1`, 스모크 `2 passed` | PASS | 앱 비의존 증명 |
| TC-012 | (AC5 부정) 제목 기대값 변조 | 원본을 `.harness-tmp/u22t_neg/`로 복사 후 변조(원본 미접촉) | 변조본 `vA`(`toHaveText("…스모크XX")`)을 별도 config(`--config`, NODE_PATH로 `@playwright/test` 해석)로 실행 | 해당 테스트만 실패 | `setContent` 케이스 ✘(5.4s), 메시지 `Expected: "AI 모의면접 하네스 스모크XX" / Received: "AI 모의면접 하네스 스모크"`. 같은 파일의 `file://` 케이스는 ✓ | PASS | 실패가 의도한 단언에서 발생 |
| TC-013 | (AC5 부정) 클릭 후 상태 텍스트 변조 | 동일 | `vB`(`toHaveText("종료됨")`) | 실패(클릭·스크립트 실행이 실제로 검증됨) | ✘ `Expected: "종료됨" / Received: "시작됨"` | PASS | 클릭→DOM 갱신이 실제로 일어남을 증명 |
| TC-014 | (AC5 부정) User-Agent 변조 | 동일 | `vC`(`/Firefox\//`) | `file://` 케이스 실패, 실제 UA 노출 | ✘ `Expected pattern: /Firefox\//  Received: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.8010.12 Safari/537.36"` | PASS | 실제 Chrome 153이 구동됨을 UA로 재확인. (첫 시도의 sed가 no-op이라 diff 공백을 확인해 폐기하고 재변조 — 변조가 실제 적용됐는지 diff로 검증) |
| TC-015 | (AC5 부정) `toContainText` 변조 | 동일 | `vD`(`"존재하지않는텍스트"`) | `file://` 케이스 실패 | ✘ `Expected substring: "존재하지않는텍스트" / Received string: "AI 모의면접 하네스 스모크"` | PASS | |
| TC-016 | (AC5 부정) 문서 제목 변조 + 원복 확인 | 동일 | `vE`(`page.title()` 기대 `"틀린 제목"`) 실행; 이후 **원본** `npm run test:e2e` 재실행, 원본 sha256 기록 | 실패 확인, 원본은 무변조·`2 passed` | ✘ `Expected: "틀린 제목" / Received: "하네스 스모크"`. 변조본 5종 = 5개 테스트 ✘, 각 파일의 나머지 케이스 ✓. 원본 재실행 `2 passed`, sha256 `3bc4ef90…f3` 유지(06 종료 시 재측정, 7절) | PASS | 원본 수정 없이 `.harness-tmp/` 사본으로만 수행 |
| TC-017 | (AC6) pytest 스모크 6건 | 서버 8422·DB 기동, 마커 0 | `V -m pytest -v -p no:cacheprovider` (2회 이상); `--collect-only -q` | `6 passed`, 이름 6개 = note §7-6의 목록 | `6 passed in 0.84~0.94s`, exit 0. 이름: `test_health`, `test_register_login_me_roundtrip[candidate]`, `[recruiter]`, `test_marker_email_format`, `test_cleanup_refuses_non_marker_email`, `test_cleanup_deletes_only_scoped_marker_account` — 목록 일치 | PASS | 회원가입→로그인→`GET /api/v1/auth/me` 왕복(role·id·email 일치, 무토큰 401) 포함 |
| TC-018 | (AC6) 건수 출력 확인 | — | `-s` 로 실행 | `[harness cleanup] 삭제 예정: … users=N` 형태 출력 | 세션 종료 시 `[harness cleanup] 삭제 예정: transcripts=0, …, users=3`(candidate·recruiter·keep 3계정), 중간에 `대상 없음 (users=0)` 2회(멱등 호출·finally 호출) | PASS | 스모크 내부 `삭제 예정: ` 단언은 capsys로 소비되어 별도 출력 |
| TC-019 | (AC6 보강) 호출 방식 강건성 | — | ① `backend/`에서 `Scripts/pytest.exe -q` ② 저장소 루트에서 `python -m pytest -q backend/tests` | 둘 다 `tests` import·pyproject 설정 인식 | 둘 다 `6 passed` | PASS | test-infra.md "backend/에서 실행" 지침보다 관대함 |
| TC-020 | (AC7) 실행 전후 마커 잔여 | — | `python -m tests.support.cleanup --all --dry-run`을 pytest 전/후, 모든 시나리오 후에 반복 | 항상 `users=0` | 02:53 KST 이전의 모든 실행(기준선·pytest 전/후·시나리오 후)은 `대상 없음 (users=0)`. 02:53 KST 이후에는 **타 에이전트(unit-19, 계정명 `u19 …`)가 만든 형식 불일치 마커형 행 3건**(`harness_test_<12hex>@harness-test.example`)이 생겨 `--all --dry-run`이 중단됨(TC-055, DEF-003 — v5에서 Fixed). 06이 만든 계정은 전부 UUID 형식이며, 최종 시점에 **엄격 형식(UUID) 마커 행 0건**을 파이썬 정규식으로 직접 확인 | PASS | `--all` 실삭제는 실행하지 않음(금지 준수). unit-19의 3건은 06이 만든 것이 아니므로 건드리지 않음 |
| TC-021 | (AC7/AC9) **실사용자 데이터 무변화** | 스냅샷 저장(users 19, interviews 9, transcripts 0, code_submissions 3, whiteboard 0, consents 11, deletion_requests 5, rubric_templates 0) | 8개 테이블 각 행의 `md5(row::text)`를 저장 후, 06의 **모든** DB 쓰기 시나리오(A~I, pytest 다수) 종료 뒤 비교; canary/stray 잔여 조회 | missing 0, changed 0, 마커 0, 내 canary/stray/템플릿 0 | 1차 비교(A~H·F·guard 후): 8개 테이블 모두 `missing=0 changed=0`, `RESULT: UNCHANGED`. **2차 재현·최종 비교(모든 06 쓰기 종료 후)**: users 19→22(+3, unit-19의 신규 계정), interviews 9→16(+7, 타 에이전트 생성), 나머지 6개 테이블 건수 불변 — **사전 존재 행은 전부 `missing=0 changed=0`(md5 동일)**, `RESULT: UNCHANGED`. `u22t06%` 사용자 0, `u22t06` 템플릿 0, 엄격 UUID 형식 마커 행 0 | PASS | 시작 시 users 34→스냅샷 19는 타 에이전트의 삭제(내 쓰기 이전 시점) — §3 참고 |
| TC-022 | (AC7) 세션 정리 가드: API와 다른 DB를 볼 때 | temp conftest가 `cleanup_test_data`를 "0건 발견"으로 대체 | `pytest .harness-tmp/u22t_guard`(계정 1개 생성 후 종료) | 종료 시 `CleanupError`로 ERROR(조용히 통과 금지) | `1 passed, 1 error` — teardown ERROR: `CleanupError: 생성한 계정 1개 중 0개만 DB에서 찾았습니다. API 서버와 DATABASE_URL이 같은 DB를 가리키는지 확인하세요…`. (남은 그 마커 계정은 이메일 지정으로 정리, 후속 dry-run 0) | PASS | note §1-B / test-infra §3-2의 가드가 실제로 작동 |
| TC-023 | (AC8) 죽은 포트 | 8499 미사용 확인 | `API_BASE_URL=http://127.0.0.1:8499 pytest -v` | `api` 픽스처 ERROR + 명확한 원인 메시지, exit≠0 | 서버 필요 4건 `ERROR at setup`: `API 서버(http://127.0.0.1:8499)에 연결할 수 없습니다: [WinError 10061] … 서버를 직접 띄우고 API_BASE_URL을 지정하세요 (docs/harness/test-infra.md)`. 서버 불필요 2건은 passed. **exit=1** | PASS | 조용한 스킵/통과 없음. (관찰: 체인 예외가 반복 출력돼 소음이 있으나 첫 줄 메시지는 명확) |
| TC-024 | (AC8) 기본 포트 + 자동 기동 없음 | 8000 미사용(`netstat`) | `API_BASE_URL` 미지정으로 `pytest -q` | 동일 ERROR, 이후에도 8000은 비어 있음 | 동일 ERROR 메시지(`…127.0.0.1:8000…`), `2 passed, 4 errors`. 테스트 코드에서 `subprocess/Popen/os.system/webServer` grep 히트 0(config 주석 1건 제외) | PASS | 서버 자동 기동 없음 |
| TC-025 | (AC9) 실사용자 이메일 CLI 거부 | — | `python -m tests.support.cleanup --email real@example.com` | exit 1, 메시지, DB 무변경 | `[harness cleanup] 실패: 마커 형식이 아닌 이메일은 정리할 수 없습니다: ['real@example.com']`, **exit 1** | PASS | 권한 경계 |
| TC-026 | (AC9) 마커형 미존재 이메일 | — | `--email harness_test_<새 uuid>@harness-test.example` | `대상 없음`, exit 0 | `[harness cleanup] 대상 없음 (users=0)`, exit 0 | PASS | 경계값 |
| TC-027 | (AC9/예외) CLI 인자 경계 | — | 인자 없음 / `--all --email a` | argparse 오류 exit 2(암묵적 "전체 삭제" 없음) | `error: one of the arguments --email --all is required` exit 2 / `argument --email: not allowed with argument --all` exit 2 | PASS | `--all`은 명시해야만 동작 |
| TC-028 | (AC9/보안) 이메일 입력 거부 매트릭스 — **DB 접근 전** 거부 | `DATABASE_URL`을 일부러 닿지 않는 값으로 설정(DB에 도달하면 `OperationalError`가 나므로 "접근 전 거부" 증명) | `cleanup_test_data([x])` 14종: 실사용자 이메일, 대문자 마커, UUID 대문자 hex, 끝 개행(`…\n`), 앞 공백, `%` 와일드카드, `_` 와일드카드, SQL 인젝션(`x' OR '1'='1`, `a'; DROP TABLE users;--@harness-test.example`), 옛 `.invalid` 도메인, 서브도메인 변형, 빈 문자열, UUID 자리수 부족, 마커 접두+실도메인(`@gmail.com`); + 마커1+비마커1 혼합 목록, 제너레이터 입력 | 전부 `UnsafeCleanupTarget` | 16/16 `UnsafeCleanupTarget`(DB 예외 0) | PASS | 정규식 `fullmatch` + 소문자 hex 고정 덕분에 개행/대문자 우회 불가 |
| TC-029 | (AC9) 같은 입력의 CLI 경로 | 위와 동일 | `main(["--email","real@example.com"])`, `["--email","x' OR 1=1--"]`, `["--email",<마커>,"--email","real@example.com","--dry-run"]` | 각 exit 1 | 3/3 exit 1 | PASS | 혼합 입력이면 마커 계정도 보호적으로 미처리 |
| TC-030 | (AC9/경계) 빈 목록·중복·미존재 | 마커 계정 1개 생성 | `cleanup_test_data([])`; `[새 마커 형식]`; `[m, m] dry_run` | `[]`는 삭제 0건(전체 삭제로 오해석 금지), 미존재는 0, 중복은 users=1 | 모두 0건 / `users=1`. 계정은 그대로 존재 확인 후 정리 | PASS | `emails is not None` 분기 정확 |
| TC-031 | (AC9) 비마커(canary) 계정·면접 보존 | canary 사용자(비마커) + 마커 데이터 | B3(중단 시 canary 그대로), B8(정상 삭제 후 canary 계정 존재), B9(마커 지원자의 면접이 **비마커 채용담당자**를 참조 → 그 면접만 삭제, canary 존재) | canary 항상 보존 | 3/3 통과. B9: `{'interviews': 1, 'users': 1}` 삭제, canary 사용자 count=1 | PASS | 실사용자 보호의 직접 증명 |
| TC-032 | (AC10) **FK 연쇄 전체 + dry-run=실삭제 + 멱등** | 마커 지원자·채용담당자 2명 API 가입 → SQL로 rubric_templates 1, interviews 2, transcripts 3, code_submissions 2, whiteboard_snapshots 1, consents 2(양 계정), deletion_requests 1 삽입 | A1 삽입 건수 검증 → A2 `dry_run` → A3 dry-run 후 무변화 → A4 실삭제 → A5 8개 테이블 잔여 0(독립 SQL) → A6 재실행 → A7 CLI 재실행 | dry-run 건수 = 삽입 건수 = 실삭제 건수, 잔여 0, 재실행 전부 0·exit 0 | A1~A7 7/7. 건수: `{transcripts 3, code_submissions 2, whiteboard_snapshots 1, interviews 2, consents 2, deletion_requests 1, rubric_templates 1, users 2}`가 삽입=dry-run=실삭제 모두 동일. 재실행 전부 0, CLI exit 0 | PASS | FK 위반 없음(실제 PostgreSQL 제약 하에서 삭제 성공) |
| TC-033 | (AC10) **FK 순서 코드 대조** | DB 접속 가능 | `pg_constraint`에서 `users`·`interviews`·`rubric_templates`·`questions`를 참조하는 FK 열거 → `cleanup.py`의 조회/삭제 목록과 대조; `app/models/*` `ForeignKey` 대조 | 실제 FK 8개 전부가 삭제 순서(자식→부모)에 반영 | DB FK: consents→users, deletion_requests→users, interviews→users(candidate·recruiter 2개), rubric_templates→users, transcripts→interviews, code_submissions→interviews, whiteboard_snapshots→interviews (= users/interviews 참조 8개), + interviews→rubric_templates(모델엔 없고 DB에만 존재), transcripts→questions. cleanup 순서: transcripts, code_submissions, whiteboard_snapshots → interviews → consents, deletion_requests → rubric_templates → users. 자식이 모두 부모보다 먼저, `interviews`가 `rubric_templates`보다 먼저(FK 충족), `questions`는 users/interviews를 참조하지 않아 정리 대상 아님(`transcripts.question_id`는 nullable FK라 삭제 방향에 영향 없음). **불일치 0건** | PASS | note §3 마지막 항목(신규 테이블 추가 시 헬퍼 갱신) — 현재 스키마 기준 완전 |
| TC-034 | (AC10/테스트 민감도) FK 제약 비공허성 | 마커 계정+consents 행 | 자식 행이 있는 마커 `users`를 직접 `DELETE` | `ForeignKeyViolation` | `psycopg.errors.ForeignKeyViolation` | PASS | "순서를 틀리면 실제로 실패한다" → TC-032가 순서 정확성을 실증 |
| TC-035 | (AC10/AC9) 비마커 면접이 마커를 참조 → **삭제 없이 중단** | canary(비마커) 지원자 + 마커 채용담당자·템플릿·연쇄 데이터 | B1: canary 면접(recruiter=마커) 삽입 후 정리 시도; B2 무삭제; B4 CLI; B5: canary 면접이 **마커 템플릿만** 참조(recruiter NULL); B6 무삭제; B7 참조 해소 후 정상 삭제 | `UnsafeCleanupTarget`, 마커 8개 테이블 삽입 상태 그대로, CLI exit 1, 해소 후 정상 | B1·B5 `UnsafeCleanupTarget`(`마커 계정을 참조하는 비-마커 면접 1건이 있어 중단합니다`), B2·B6 건수 전부 그대로, B4 exit 1, B7 삭제 건수 = 삽입 건수 | PASS | note 편차#4 실측 |
| TC-036 | (AC10) **삭제 건수 불일치 시 전체 롤백** | 연쇄 데이터 삽입 상태 | `_count`를 변조해 ① users 조회 건수+1(마지막 DELETE에서 불일치) ② transcripts 조회 건수+1(첫 DELETE에서 불일치) | `CleanupError`, 앞서 실행된 DELETE 포함 **전부 취소** | ① `users: 삭제 건수(2)가 조회 건수(3)와 달라 롤백합니다.` ② `transcripts: 삭제 건수(3)가 조회 건수(4)와 …`. 두 경우 모두 직후 8개 테이블 건수가 삽입 상태 그대로(①은 자식 테이블 7개 DELETE가 이미 실행된 뒤이므로 **트랜잭션 롤백이 실제로 작동**함을 증명) | PASS | 정상 종료 시에만 commit되는 구조 확인 |
| TC-037 | (AC9/보안) LIKE 결과 재검증 | 형식이 어긋난 stray 행(`harness_test_u22t06stray@harness-test.example`) 임시 삽입(수 초) | `--all`(dry-run) 라이브러리 호출; 같은 상황에서 `--email` 범위 정리 | `--all`은 `UnsafeCleanupTarget`, `--email`은 영향 없음, stray는 삭제되지 않음 | F2 `조회된 계정 중 마커 형식이 아닌 것이 있어 중단합니다: […]`, F3 `users=1` 정상, F4 stray 존재. 종료 후 stray 삭제(id+이메일 조건) 확인 | PASS | 이 안전 동작이 실환경에서 dry-run까지 막는 문제는 TC-055/DEF-003 |
| TC-038 | (관찰, 범위 밖) 범위 밖 **마커** 계정이 참조하는 경우 | 마커 채용담당자 A + 마커 지원자 B, 면접(B,A) | `cleanup([A])`; `cleanup([A,B])` | (설계상) A만 지정하면 중단, 둘 다면 삭제 | G1 `UnsafeCleanupTarget`(메시지는 "비-마커 면접"이라 표기되지만 실제 참조자는 다른 **마커** 계정 B), G2 `interviews=1, users=2` 삭제 | PASS(안전) | OBS-2: 동작은 안전하나 메시지 문구 부정확 + 07/08은 상호 참조 계정을 **함께** 정리해야 함 |
| TC-039 | (AC11) ruff | 경량 venv의 ruff 0.16.8, 프로젝트 `pyproject.toml` | `cd backend && ruff check tests` | `All checks passed!` | `All checks passed!`, exit 0 | PASS | |
| TC-040 | (AC11/민감도) ruff가 실제로 위반을 잡는가 | `.harness-tmp/`에 미사용 import 파일 | 같은 설정으로 `ruff check` | 위반 검출 | `Found 2 errors`(F401 ×2) — 도구가 살아 있음. 파일 삭제 | PASS | 무규칙 통과 배제 |
| TC-041 | (보안) SQL 파라미터 바인딩 | — | `grep -n "execute(" cleanup.py`; f-string 사용처 열거; 인젝션 문자열 입력(TC-028) | 모든 `execute`가 `%s` 바인딩, f-string은 메시지에만(SQL 없음), 인젝션 입력은 DB 도달 전 거부 | `execute` 6개소 전부 `(sql, params)` 형태(테이블명은 코드 상수 dict). f-string은 예외/출력 메시지 6개소뿐(SQL 문자열에는 없음). 인젝션 2종 `UnsafeCleanupTarget` | PASS | 코드 정독 + 동적 입력 양면 |
| TC-042 | (보안/설계) 자격증명 env 전용 | — | `grep -rniE "postgres(ql)?://\|password *= *['\"]\|secret\|api[_-]?key\|5544"` on `backend/tests`, `frontend/e2e`, config; `_database_url()` 4시나리오 | 하드코딩 자격증명 0, env→.env 순, 둘 다 없으면 오류 | grep 히트 = `secrets.token_urlsafe(16)`·`postgresql+psycopg://` 치환 코드뿐. E1(접미사 치환), E2(env/.env 모두 없음 → `CleanupError: DATABASE_URL이 없습니다…`, 기본값 폴백 없음), E3(.env 파싱: 주석 무시·따옴표 제거), E4(env 우선) 4/4. 테스트 비밀번호는 매번 랜덤 22자 | PASS | `.env` 파싱은 임시 디렉터리(`.harness-tmp`)로 `_BACKEND_DIR`을 바꿔 검증 — 실제 `.env` 미접촉 |
| TC-043 | (설계) 서버 자동 기동 없음 | — | `grep -rnE "subprocess\|Popen\|os\.system\|webServer\|spawn"` | 코드에 기동 로직 없음 | 히트는 `playwright.config.ts` 3행 **주석** 1건뿐 | PASS | DEC-028 |
| TC-044 | (편차#1) `.invalid` 불가·`.example` 필요성 실측 | 서버 8422 | `POST /auth/register` with `harness_test_<uuid>@harness-test.invalid` / `@harness-test.example` | `.invalid` 422(앱이 거부), `.example` 201 | `.invalid` → **422** `value is not a valid email ad…`(DB에 계정 미생성 확인), `.example` → **201** | PASS | 편차#1 **타당**: 지시서의 `.invalid`로는 계정을 만들 수 없음 |
| TC-045 | (편차#2) `/users/me` 부재·`/auth/me` 계약 | 서버 8422 | `GET /api/v1/users/me`, `GET /users/me`, openapi.json 경로 열거, `GET /api/v1/auth/me`(무토큰/가짜토큰) | 앞 둘 404, openapi에 `/users/me` 없음(`/users/me/consents` 등만), `/auth/me` 무토큰·가짜토큰 401 | 404, 404, openapi 경로 중 `me`/`users`/`health` 포함 항목 = `/api/v1/auth/me`, `/api/v1/users/me/consents`, `/api/v1/users/me/biometric-data`, `/api/v1/users/me/deletion-requests`, `/api/v1/interviews/{interview_id}/resume`, `/api/v1/ops/health`, `/api/v1/health`(단독 `/users/me` 없음), 401, 401. 스모크가 정상 토큰으로 200 + role/id/email 일치 확인 | PASS | 편차#2 **타당**(지시서 표기 오류, 규칙 A 질문 대상 아님 — 실제 계약을 따름) |
| TC-046 | (테스트 민감도) 백엔드 스모크가 가짜 통과가 아닌가 | `.harness-tmp/u22t_neg_be/`에 스모크 사본+변조 conftest | 변이 3종: ① role 단언을 `"admin"`으로 ② cleanup을 no-op(건수만 반환)으로 대체 ③ cleanup을 no-op+`삭제 예정` 출력으로 대체 | 각각 실패 | ① 2건 ✘(`'candidate' == 'admin'` 등) ② `test_cleanup_deletes_only_scoped_marker_account` ✘(출력 단언 `'삭제 예정: ' in ''`) + `test_cleanup_refuses_non_marker_email` ✘ ③ `assert relogin.status_code == 401` → **`200 == 401`** ✘ + refuse 테스트 `DID NOT RAISE` ✘. 변이 중 생긴 계정 8개는 이메일 목록으로 정리(`users=8`) | PASS | 스모크의 "실제 삭제 확인(재로그인 401)" 단언이 반환값이 아닌 상태를 본다는 증명 |
| TC-047 | (AC12) gitignore 4항목 | — | `git check-ignore -v backend/.pytest_cache/x frontend/test-results/x frontend/playwright-report/x frontend/blob-report/x` + `.harness-tmp/x`, `backend/tests/__pycache__/x.pyc`; 음성 대조(`frontend/e2e/smoke.spec.ts`, `backend/tests/conftest.py`); `git diff HEAD -- .gitignore`의 삭제 행 | 4항목 전부 ignore, 소스는 ignore 아님, 기존 항목 보존 | `.gitignore:33/41/42/43` 매칭(+ `.harness-tmp/` line 7, `__pycache__` line 29). 소스 2개는 exit 1(무시 안 됨). `-` 행 0(기존 항목 보존, 6줄 추가만) | PASS | |
| TC-048 | (AC12) Teardown 후 `git status` | 7절 정리 완료 | `git status`·`git status --short` 전문 채취, `.harness-tmp` 목록을 시작 기준선과 비교, 프로세스·포트·DB 잔여 조회 | 이 유닛 산출물 + 06 산출물 + 타 유닛 변경 외 잔여 없음 | 7절 전문 첨부: 06이 새로 만든 파일은 06 산출물 2개뿐, `.harness-tmp/u22*`·`frontend/test-results`·`frontend/playwright-report`·`backend/.pytest_cache` 0건, 8422 리스너 0, DB 06 행 0 | PASS | 규칙 K 2번 충족 |
| TC-049 | (AC13) 회귀: 앱 소스 무변경 | — | `git diff --stat -- backend/app frontend/app frontend/components frontend/lib`; 각 변경 파일의 소유 유닛을 note로 대조; `grep -rn "unit-22\|u22\|harness_test\|harness-test" backend/app frontend/app frontend/components frontend/lib` | 이 유닛 기인 변경 0 | 측정 시점(2차 검증)의 변경 파일 14개(`git diff --stat`, 646+/182-) 전부가 타 유닛 기인: `ws.py`·`main.py`·`job_queue.py`(unit-7-note에 명시), `config.py`(`redis_url` 추가 — unit-7 주석), `models/transcript.py`(question FK — unit-7 모델 docstring), `globals.css`·`CodeEditorPanel.tsx`·`WhiteboardCanvas.tsx`·`interviews/[id]/page.tsx`·`WebcamPreview.tsx`(unit-20-note에 명시), `api/v1/interviews.py`·`schemas/interview.py`·`app/page.tsx`·`lib/api.ts`(코드 주석에 `REQ-002(unit-19…)` 명기, unit-19 진행 중). unit-22-note는 이 파일들을 "읽기"로만 언급하며 06이 첫 측정(시작 시 10개)보다 4개 늘어난 것은 unit-19가 뒤늦게 시작한 것으로 설명됨. 소스 내 unit-22/마커 참조 grep 0건. 이 유닛 산출물 sha256(§7)은 06 실행 전후 동일 | PASS | 타 유닛 변경은 결함으로 세지 않음 |
| TC-050 | (지시4) 의존성 실존·버전·설정 | 네트워크 | `pip install --dry-run "pytest>=9.1,<10" "httpx>=0.28,<0.29" "ruff>=0.16,<0.17"`; 실제 설치 버전; `requirements.txt`의 psycopg 행; `pyproject.toml` diff; `pytest --collect-only` | 범위가 실제 해석됨, psycopg 기존 의존성, 설정이 testpaths만 추가 | 해석·설치 성공: pytest **9.1.1**, httpx **0.28.1**, ruff **0.16.8**, psycopg **3.2.13**(`requirements.txt:5 psycopg[binary]>=3.2,<3.3`). `requirements-dev.txt` diff = 2줄 추가. `pyproject.toml` diff = `[tool.pytest.ini_options] testpaths=["tests"]` 4줄(ruff 설정 무변경). collect 6건 | PASS | note가 "전체 requirements 설치 불필요"라 한 근거: `requirements.txt`에 `sentence-transformers`(torch 유입)·`faster-whisper` 존재 |
| TC-051 | (지시5) test-infra.md 절차 그대로 재현 | 처음 받는 사람 관점 | §2.2 venv/pip 명령, §2.3 pytest, §3.4 CLI 3종, §4 서버 기동(런처≠리스너 PID 현상 포함)·PID 종료 원칙, §5.1 `npm ls`/`playwright install chromium`, §5.2 `npm run test:e2e`, §5.3(편차#5 명시 여부), §6 재사용 지침 | 문서대로 추가 질문 없이 재현 | 전부 문서 그대로 성공. §4의 "런처 PID와 리스너 PID가 다를 수 있다"는 실측 일치(34320 vs 28920). §5.3에 "전용 Node 헬퍼는 아직 없다" 명시 확인. 단 **§5.2의 tsc 명령은 아래 TC-054** | PASS | |
| TC-052 | (경계/예외) 계정 팩토리 헬퍼 | 서버 8422 | `auth_headers`(미로그인), 틀린 비밀번호 로그인, 짧은 비밀번호(5자) 가입, `role=admin` 가입 | 각각 `HarnessApiError` / 401 / 422 / 422; 팩토리 비밀번호는 최소 길이 이상 | I1 `HarnessApiError`, I2 `HarnessApiError: 로그인 실패: 401`, I3 **422**, I4 **422**(admin은 테스트로 만들 수 없음). 팩토리 비밀번호 길이 **22**(≥8, ≤128) | PASS | 권한 경계(역할 위조 차단) 포함 |
| TC-053 | (DEF-001 재검증) DB 불통·오설정 시 정리 헬퍼가 약 5초 내 명확한 메시지로 종료 | 재작업 반영본(`_connect()`, `connect_timeout=5`). 사용하지 않는 주소 확인(`netstat`) | 각 `DATABASE_URL`로 `python -m tests.support.cleanup --all --dry-run`을 `timeout 60`으로 실행, 소요시간·exit·마지막 줄·출력 내 비밀번호 문자열 검색: ① 닫힌 포트 127.0.0.1:5999 ② 127.0.0.1:1(`postgresql+psycopg://`) ③ 응답 없는 주소 10.255.255.1:5432 ④ TEST-NET 192.0.2.1:5432 ⑤ 잘못된 DSN `…@[bad/x` ⑥ 잘못된 포트 `:notaport` ⑦ 쓰레기 문자열 ⑧ `?sslmode=bogus` ⑨ 실DB(5544)에 존재하지 않는 사용자+틀린 비밀번호 | ①~④ 5초 안팎에 `실패: DB에 연결할 수 없습니다 (제한 5초): …` exit 1(v4: 60초 초과 미종료), ⑤~⑨ 즉시 실패, 비밀번호 미출력 | ①5.7s ②5.6s ③5.6s ④5.6s 모두 `[harness cleanup] 실패: DB에 연결할 수 없습니다 (제한 5초): connection timeout expired`, **exit 1**(traceback 없음). ⑤0.6s `DB 접속 설정이 올바르지 않습니다 (ProgrammingError). DATABASE_URL을 확인하세요.` exit 1 ⑥0.6s `…invalid integer value "notaport" for connection option "port"` exit 1 ⑦0.6s ⑤와 동일 메시지 ⑧0.6s `invalid sslmode value: "bogus"` ⑨0.6s `FATAL: password authentication failed for user "u22r2nouser"`(사용자명만, 비밀번호 없음). 9건 모두 출력 내 `secretpw`/`WRONGPW` 검색 **0건**. 가짜 연결 단위 테스트 3건(`test_connect_uses_timeout_and_wraps_operational_error`, `…does_not_leak_dsn`, `test_cli_exits_1_when_db_unreachable`)도 통과 | **PASS**(v4 FAIL → 재검증 PASS) | 관찰 OBS-7: 오설정(⑥⑧)에도 "(제한 5초)" 문구가 붙는 것은 사소한 문구 문제. 변이 M3·M4·M8이 이 테스트들에서 kill됨(TC-058). 실DB 인증 실패 메시지가 비밀번호를 싣지 않음을 확인 |
| TC-054 | (DEF-002 재검증) test-infra.md §5.2/§5.4 일치 + 문서 명령 실행 | 재작업 반영 문서(sha256 `9782daf2…`) | ① §5.2·§5.4의 tsc 관련 문장을 grep(`tsc`) ② **문서대로** `cd frontend && npx tsc --noEmit --incremental false` 실행, 실행 전후 `tsconfig.tsbuildinfo`·`next-env.d.ts` sha256 비교 ③ 대조: 플래그 없는 `npx tsc --noEmit`을 `--tsBuildInfoFile`을 `.harness-tmp/`로 돌려 실행(추적 파일 비접촉) | §5.2가 `--incremental false`와 사유를 명시해 §5.4와 일치, 문서 명령은 추적 생성물을 바꾸지 않고 exit 0 | ① §5.2(104행)는 `npx tsc --noEmit --incremental false` + "`tsconfig.json`이 `incremental: true`라 플래그 없이 실행하면 추적되는 생성물(`tsconfig.tsbuildinfo`, `next-env.d.ts`)이 갱신되어 타 유닛 변경과 섞인다 (§5.4)", §5.4(117행)는 "`--incremental false`로 실행하면 이 파일을 건드리지 않는다" → **일치**, 문서 내 플래그 없는 `tsc --noEmit` 안내 0건. ② exit 0, `tsbuildinfo` `eb6dc01596…`·`next-env.d.ts` `1b59d4c6b8…` **전후 동일**(타 유닛 코드도 현재 컴파일 통과). ③ 플래그 없는 실행은 139,271 bytes buildinfo를 기록(위험 실재, probe 삭제) | **PASS**(v4 FAIL → 재검증 PASS) | 문서 문구만 정정된 결함이라 프런트 스모크·lint 재실행은 불필요(2절) |
| TC-055 | (DEF-003 재검증) stray 상태별 `--all --dry-run` 동작 + 실삭제 경로 중단 | 재작업 반영본. 시작 시 DB에 stray 없음, 타 에이전트의 UUID 마커 계정 존재 | **실DB(06은 dry-run과 자기 행만)**: F2 stray 없음 → `--all --dry-run` / F3 06이 stray 1행(`harness_test_u22r2stray0@harness-test.example`)과 그 stray가 후보인 면접 1건을 삽입 → 연속 dry-run 건수 비교, stray 면접 삭제 전후 interviews 건수 비교 / F4 CLI exit·출력 / F5 무삭제 / F6 `--email <stray>` / F7 stray 공존 시 `--email 정상 --dry-run` / F8 같은 상황에서 `--email 정상` 실삭제 / F9 stray 보존. **가짜 연결 단위 테스트(신규 4건)**: dry-run stray 보고·제외, 실삭제 stray 중단(DELETE 0), 종료코드 0/3/1, stray만 있을 때 | stray 없으면 exit 0, stray 있으면 정상 건수 + stray 목록 + exit 3, stray는 어떤 경로로도 삭제·집계 안 됨, **실삭제 경로는 stray 시 삭제 없이 중단** | F2 exit 0, `users=12`(타 에이전트 마커 포함 집계, 삭제 없음). F3/F3b 연속 dry-run 정상 건수 안정 + stray 면접을 지워도 interviews 건수 동일(7=7) → stray 면접은 집계에 없음. F4 **exit 3**, 출력에 stray 이메일·`DRY-RUN(삭제 안 함)`·`users=` 포함. F5 stray 행 그대로. F6 exit 1 `마커 형식이 아닌 이메일…`. F7 exit 0. F8 `users=1, stray_users=0` 정상 삭제. F9 stray 보존. 종료 후 06이 삽입한 stray/면접 행은 id+이메일 조건으로만 삭제(잔여 0). 재작업 후 CLI `--all --dry-run`(stray 없음) 최종 `users=11`, exit 0. 가짜 연결 테스트 7건 전부 통과, **실삭제 경로 stray 중단은 변이 M1(중단 조건 제거)·M10에서 kill**(TC-058). **실DB `--all` 실삭제는 지시에 따라 미실행**(코드 정독: `if stray and not dry_run: raise`가 첫 조회 직후·모든 DELETE 이전인 100행에 위치) | **PASS**(v4 FAIL → 재검증 PASS) | 안전 트레이드오프 확인: 실삭제는 stray 1건에도 전체 중단(보수적) — 08은 dry-run(exit 0/3)으로 잔여를 확인하고 stray는 소유자가 수동 정리. 06이 stray를 삽입한 약 1초의 구간 동안 병렬 에이전트의 `--all --dry-run`이 exit 3을 볼 수 있었음(공개). 반환 dict에 `stray_users` 키가 추가되어 호출자가 dict 전체를 비교하면 영향(OBS-8) |
| TC-056 | (AC6/AC11 재실행) pytest 13건·ruff·서버 비의존 신규 7건 | 서버 8422·DB 기동, 마커 stray 0 | `V -m pytest -v -p no:cacheprovider`; `V -m ruff check tests`; `API_BASE_URL=http://127.0.0.1:8499`(죽은 포트)로 `pytest tests/test_cleanup_helper.py -q` | `13 passed`, ruff 통과, 신규 7건은 서버 없이 통과(fixture `api` 미사용) | `13 passed in 1.05s`(신규 7 + 스모크 6, 이름 전부 확인), `All checks passed!`, 죽은 포트에서 신규 `7 passed in 0.02s` | PASS | note §7-6의 새 기대값과 일치 |
| TC-057 | (회귀) 정리 헬퍼 안전 계약 — `cleanup.py`가 바뀌었으므로 v4와 동일 시나리오를 새로 실행(임시 스크립트, 64개 단언) | 서버 8422, 06이 만든 마커 계정·연쇄 데이터·canary | A(7): 연쇄 8개 테이블 삽입→dry-run=삽입 건수(`stray_users=0` 포함)=실삭제 건수, 잔여 0, 멱등, CLI 0 / B(9): 비마커 canary 면접이 마커 채용담당자·템플릿을 참조 → `UnsafeCleanupTarget`+무삭제+CLI exit 1, 해소 후 정상 삭제, 비마커 보존, 마커 지원자↔비마커 채용담당자 방향 / C(4): 조회 건수를 users(마지막 DELETE)·transcripts(첫 DELETE)에서 변조 → `CleanupError`+8개 테이블 롤백 / D(26): 이메일 16종(실사용자, 대문자, 개행, 앞 공백, `%`/`_`, SQL 인젝션 2종, `.invalid`, 서브도메인, 빈 문자열, 자리수 부족, **12hex 비-UUID 마커형 2종**, 실도메인)을 DB 도달 전 `UnsafeCleanupTarget`으로 거부(연결 실패로 오인되지 않도록 `UnsafeCleanupTarget`과 일반 `CleanupError`를 구분, 대조군으로 정상 형식은 연결 시도), 혼합·제너레이터, CLI 4종은 메시지가 `마커 형식이 아닌`임을 확인, 빈 목록 `[]`≠전체, 미존재·중복 / E(4): 접속정보 env→.env 파싱·폴백 없음·env 우선 / F1: FK 제약 실재(직접 DELETE → `ForeignKeyViolation`) / G(2): 범위 밖 마커 참조 안전 중단·함께 지정 시 삭제 / H(2): `.invalid` 422, `/users/me` 404 | 전부 v4와 동일 결과(계약 유지), 반환 dict에 `stray_users`만 추가 | **64/64 PASS**(A 7, B 9, C 4, D 26, E 4, F 10(F1~F9+F3b), G 2, H 2). 대표 출력: dry-run=실삭제=`{transcripts 3, code_submissions 2, whiteboard_snapshots 1, interviews 2, consents 2, deletion_requests 1, rubric_templates 1, users 2, stray_users 0}`, B1 `마커 계정을 참조하는 비-마커 면접 1건이 있어 중단합니다`, C1 `users: 삭제 건수(2)가 조회 건수(3)와 달라 롤백합니다.`. FK 순서는 `pg_constraint` 재조회 없이 코드 정독 + A/F1로 확인(cleanup의 DELETE 목록·순서 v4와 동일: transcripts→code_submissions→whiteboard_snapshots→interviews→consents→deletion_requests→rubric_templates→users) | PASS | v4의 FK 전수 대조(TC-033)는 스키마·삭제 목록 모두 불변이라 재실행 생략 |
| TC-058 | (민감도) 신규 테스트 7건이 실제로 계약을 고정하는가 — 변이(mutation) 검증 | 원본 미접촉, `.harness-tmp/u22t_mut/` 사본에서만 변이(변이 대상 문자열이 정확히 1회 존재함을 단언), 무변이 대조군 포함 | 10개 변이를 각각 적용해 `pytest tests/test_cleanup_helper.py` 실행: M1 실삭제 stray 중단 제거 / M2 stray를 대상 id에 포함 / M3 `connect_timeout` 제거 / M4 DSN 오류에 원문 노출 / M5 종료코드 3→2 / M6 stray여도 exit 0 / M7 stray 보고 출력 제거 / M8 OperationalError 승격 제거 / M9 `stray_users`를 항상 0 / M10 dry-run에서도 stray면 중단(DEF-003 회귀) | 대조군 `7 passed`, 모든 변이는 최소 1개 테스트가 실패 | 대조군 7 passed. **10/10 변이 kill**: M1→2 failed(`test_sweep_real_run_with_stray_aborts_without_deleting`, `test_cli_exit_codes_for_stray_and_clean`), M2→2(dry_run_reports…, stray_only…), M3→1(connect_uses_timeout…), M4→1(config_error_does_not_leak_dsn), M5→1, M6→1(cli_exit_codes…), M7→1(dry_run_reports…), M8→2(connect_uses_timeout…, cli_exits_1_when_db_unreachable), M9→3, M10→3. 사본 삭제, 원본 `cleanup.py` sha256 `11ca793db3…` 불변 | PASS | 사용자 지정 예시(실삭제 stray 중단 테스트 변이)는 M1에서 확인 |
| TC-059 | (보안 재확인) SQL 바인딩·자격증명·서버 자동 기동·저장소 내 테스트 파일 | 변경된 `cleanup.py`·신규 테스트 | `grep -n "execute("`; SQL을 담은 f-string 검색; 자격증명 패턴 grep(`postgres://…@`, `password=`, `secret`, `:5544` 등); `psycopg.connect` 호출부; `subprocess/Popen/os.system/webServer` grep | 모든 `execute`는 바인딩, SQL에 f-string 없음, 하드코딩 자격증명 0, 서버 자동 기동 0 | `execute` 6개소 전부 `(sql, params)`(테이블명은 코드 상수). f-string은 오류 메시지 1건(64행)뿐이며 SQL 아님. `psycopg.connect`는 `_connect()` 한 곳(62행)에서만 `_database_url()`(env→`.env`)로 호출. 자격증명 grep 히트는 `secrets.token_urlsafe(16)`과 `test_cleanup_helper.py`의 **더미 DSN `u:secretpw@127.0.0.1:1/x`**(비밀번호 누출 검사용 센티널, 실제 자격증명 아님). `subprocess` 등 히트는 `playwright.config.ts` 주석 1건뿐 | PASS | OBS-9: 더미 `secretpw` 문자열은 시크릿 스캐너가 오탐할 수 있음(낮음) |
| TC-060 | (실사용자 무변화 재검증) 8개 테이블 행 md5 스냅샷 | 스냅샷 저장(users 30, interviews 16, transcripts 0, code_submissions 9, whiteboard 5, consents 18, deletion_requests 5, rubric_templates 0) — 06의 쓰기 실행 전 | 06의 모든 DB 쓰기 시나리오(A~H, pytest, 변이 아님) 종료 후 동일 스냅샷 비교; 06 소유 패턴(`u22t06%`, `u22t06` 템플릿, `harness-*` 팩토리 이름) 잔여 조회 | 사전 존재 행 missing 0·changed 0, 06 잔여 0 | 8개 테이블 모두 `before==after`, `missing=0 changed=0`, `RESULT: UNCHANGED`. 마커/자기 패턴 조회 11행은 전부 unit-20 계정(`u20 e2e`, 07:24 생성)이며 06 소유 패턴 0건. `--all --dry-run` → `users=11`, exit 0(타 에이전트 마커는 집계만, 삭제하지 않음) | PASS | 이 기간 타 에이전트의 쓰기가 있었어도 사전 존재 행 변경은 관측되지 않음 |
| TC-061 | (재검증 생략 항목의 근거 검증) 프런트·비변경 파일 불변 | — | `sha256sum`/수정시각: `frontend/e2e/smoke.spec.ts`, `playwright.config.ts`, `package.json`, `backend/tests/{test_smoke,conftest,support/accounts}.py`, `.gitignore`, `pyproject.toml`, `requirements-dev.txt` | v4 측정값과 동일 | 해시 동일(`3bc4ef90…`, `d2cd4309…`, `be841a8c…`, `86709eb2…`, `5582a191…`), 프런트·설정 파일 수정시각 01:35~01:41 그대로. 변경 파일은 재작업 명세대로 `cleanup.py`(03:07), `test_cleanup_helper.py`(03:07), `test-infra.md`(03:06), note(03:09)뿐 | PASS | 프런트 스모크 재실행 생략의 정당성 근거 |

- 실행 근거 요약: (v4) 프런트 스모크 3회+변조 6회, pytest 공식 스위트 다회(6/6), 06 독립 시나리오 63개 단언. (v5 재검증) pytest 13 passed(다회), 신규 7건 서버 비의존 실행, ruff, 재작업 대상 TC-053/054/055 재검증, 정리 헬퍼 안전 계약 회귀 시나리오 **64개 단언 전부 PASS**, 신규 테스트 변이 **10/10 kill**, 커버리지 측정 1회.
- 판정 집계(v5): TC 61건 전부 **PASS / FAIL 0**. 단 TC-053/054/055는 v4에서 FAIL이었고 v5에서 재검증 PASS로 바뀐 것이며(이력 보존), 나머지 52건은 v4 결과가 유효하고 v5에서 영향받는 부분만 TC-056~061로 재실행했다. (TC-048 Teardown도 v5 Teardown 후 재확정 — 7절)

## 5. 커버리지
- 커버리지 지표(v5 재측정): `coverage.py`(06 전용 venv, branch 모드)로 **공식 pytest 스위트(13건) + 06 회귀 시나리오 A~H(64단언) + CLI 직접 실행(정상 exit 0·DB 불통 exit 1)**을 합산, 대상 `backend/tests/conftest.py`·`support/*`·`test_smoke.py`·`test_cleanup_helper.py`: **문장 326 중 319 실행(97%), 분기 46 중 부분 5**. 파일별: **`cleanup.py` 100%(문장·분기 모두 미실행 0)** — v4의 98%에서 `__main__` 진입점과 신규 `_connect` 오류 분기·stray 분기까지 전부 실행됨. `test_cleanup_helper.py` 100%, `test_smoke.py` 100%. `accounts.py` 90%(미실행 45·66·76행: 미로그인 `auth_headers` 예외·가입 실패·로그인 실패 분기 — 파일이 v4 이후 불변이고 v4의 TC-052에서 별도 검증했으며 v5 재검증에서는 실행하지 않음), `conftest.py` 79%(미실행 22-23행 = 서버 미기동 `pytest.fail` 분기 — v4 TC-023/024로 검증, 37행 = 생성 계정 0건 조기 return, 40행 = 세션 종료 시 DB 불일치 `CleanupError` — v4 TC-022로 검증, 파일 불변).
- 기능(인수조건) 커버리지: AC1~AC13 **13/13**에 TC 매핑(4-1절), 정상/경계/예외/권한 경계 각 포함(경계: 빈 목록·중복·개행·대문자·UUID 자리수·비밀번호 길이, 예외: 죽은 포트·DB 불통·불일치 롤백, 권한 경계: 비마커 거부·비마커 면접 참조 중단·`role=admin` 가입 거부).
- 프런트: `smoke.spec.ts`는 2개 테스트/전 단언이 부정 경로(TC-012~016, v4)로 민감도가 확인됨(5개 변조 → 5개 실패). 프런트 파일은 재작업에서 불변(TC-061)이라 v5에서 재실행하지 않았다. 프런트 커버리지 도구는 미구동(인프라 스모크라 라인 커버리지가 의미 없음).
- 신규 테스트의 결함 검출력: 변이 10종 전부 kill(TC-058) — 라인 커버리지가 아니라 계약 고정력 지표.
- 커버되지 않은 부분과 사유:
  - 회원가입 서버 오류(4xx/5xx) 시 `HarnessApiError` 분기(`accounts.py:66`): 정상 서버에서 가입 실패를 안전하게 유도할 방법이 없어 미실행(`login_account` 실패 분기와 구조가 동일하고 TC-052 I2로 확인).
  - 실제 앱 화면(Next) 대상 e2e: 금지 사항.
  - **실DB에서의 `--all` 실삭제 경로**(stray 중단, 다수 계정 일괄 삭제, 실삭제 롤백): 지시상 금지라 실행하지 않았다. stray 중단은 가짜 연결 테스트+변이(M1)로, 롤백·FK 순서는 `--email` 범위 실삭제로(TC-057 A~C) 검증했다.
  - **저장소에 보존된 테스트가 커버하지 않는 계약**: 비마커 면접 참조 중단·롤백·FK 연쇄는 06의 임시 시나리오(위 TC-057)로만 검증됐고 `backend/tests/`에는 회귀 테스트로 남아 있지 않다(OBS-6).
  - 정리 헬퍼가 다루지 않는 미래 테이블(FK 신규): 현재 8 테이블 기준 완전(TC-033). 새 테이블 추가 시 갱신 필요 — 누락되면 FK 위반으로 롤백(오삭제 없음).
  - 동시 실행(두 pytest 세션이 같은 DB에서 동시에): 각 세션이 자기 이메일 범위만 정리하도록 설계돼 있고, 06 세션 중 병렬 에이전트(unit-7 06, unit-19)가 실제로 같은 DB를 사용했으나 06의 정리 호출이 그들의 행을 지운 흔적은 없음(TC-021 md5 비교, unit-19의 마커형 3건이 06 종료 후에도 그대로 존재). 명시적 동시성 부하 테스트는 미수행.

## 6. 결함(Defect) 목록
| ID | 설명 | 재현 절차 | 심각도(Critical/High/Medium/Low) | 상태(Open/Fixed/Deferred) | 조치 내용 |
|----|------|-----------|-----------------------------------|----------------------------|-----------|
| DEF-001 | 정리 헬퍼(`backend/tests/support/cleanup.py`)의 `psycopg.connect(url)`에 `connect_timeout`이 없어, DB에 접속할 수 없는 상황(컨테이너 중지·잘못된 주소)에서 CLI/세션 teardown이 **수십~수백 초 응답 없이 대기**한다(닫힌 포트 127.0.0.1:5999에서 60초 초과, 127.0.0.1:1에서 100초 초과). 또 `OperationalError`/`ConnectionTimeout`이 `CleanupError`로 승격되지 않아 원시 traceback으로 종료(exit 1). 삭제는 일어나지 않으므로 데이터 안전에는 영향 없음(fail-safe) | `cd backend && DATABASE_URL=postgresql://u:p@127.0.0.1:5999/x V -m tests.support.cleanup --all --dry-run` → 60초 내 미종료(TC-053). 대조: `psycopg.connect(..., connect_timeout=5)` → 5.0초에 `ConnectionTimeout` | **Low** | **Fixed** (v5 재검증 PASS) | 05 재작업(DEC-033): `_connect()`에 `connect_timeout=5` 추가, `OperationalError`→`CleanupError`(제한 5초 메시지), 그 외 `psycopg.Error`는 클래스명만 노출. **06 재검증: TC-053** — 닫힌 포트·응답 없는 주소 4종 5.6~5.7초 내 exit 1·명확한 메시지(v4: 60초 초과), 오설정 DSN 5종 즉시 실패, 비밀번호 비누출 9종 0건, 변이 M3/M4/M8 kill(TC-058) |
| DEF-002 | `docs/harness/test-infra.md` §5.2가 타입체크를 `npx tsc --noEmit`(플래그 없음)으로 안내하는데, `tsconfig.json`이 `incremental: true`라 그대로 실행하면 **추적 대상 `frontend/tsconfig.tsbuildinfo`가 갱신**된다. §5.4는 "`--incremental false`로 실행하면 이 파일을 건드리지 않는다"고 하여 문서 내부가 불일치 | TC-054: 플래그 없는 `--noEmit`이 139,055 bytes buildinfo를 기록함을 출력 위치를 바꿔 확인 | **Low**(문서) | **Fixed** (v5 재검증 PASS) | 05 재작업: test-infra §5.2를 `--incremental false`+사유로 통일. **06 재검증: TC-054** — §5.2/§5.4 일치 확인, 문서 명령 실행 시 `tsbuildinfo`·`next-env.d.ts` 해시 불변, tsc exit 0 |
| DEF-003 | `--all`(dry-run 포함)이 LIKE 패턴(`harness_test_%@harness-test.example`)에는 걸리지만 UUID 엄격 정규식에 맞지 않는 행이 **1건이라도** 있으면 건수 출력 없이 전체 중단(exit 1)한다. 삭제가 없는 `--dry-run`까지 막아, 병렬 환경에서 "잔여 마커 확인"(test-infra §6-4, note §7-7)이 불가능해지고 형식 불일치 행은 헬퍼로 정리할 방법도 없다. 실환경에서 타 에이전트(unit-19)가 12자리 hex 형식으로 3건을 만들어 **실제 발생**(TC-055) | `cd backend && V -m tests.support.cleanup --all --dry-run` (unit-19 계정 3건이 존재하는 동안) → `실패: 조회된 계정 중 마커 형식이 아닌 것이 있어 중단합니다: [...]`, exit 1 | **Low** | **Fixed** (v5 재검증 PASS) | 05 재작업: `--dry-run`은 stray를 별도 집계(`stray_users`)·목록 보고·정상 건수 유지·exit 3, 실삭제는 종전대로 stray 시 삭제 없이 중단, 문서 §3에 종료코드·`account_factory` 규약 명시. **06 재검증: TC-055** — 실DB stray 공존 시 exit 3+목록+정상 건수, stray 없으면 exit 0, 실삭제 경로 중단은 가짜 연결 테스트+변이 M1/M10 kill. unit-19의 3건은 소유 측이 정리한 것으로 보이며 06은 건드리지 않음 |

- v5 결과: **DEF-001·002·003 모두 Fixed**(각각 TC-053/054/055 재검증 PASS + 변이 검증). 재검증 중 **신규 결함은 발견되지 않았다**. 근거: 안전 계약 회귀 64단언 PASS(TC-057), 신규 테스트 변이 10/10 kill(TC-058), `cleanup.py` 문장·분기 100% 실행(5절), 실사용자 스냅샷 무변화(TC-060), 보안 grep(TC-059). 인수조건 13개는 v4에서 PASS였고 재작업이 관련 계약을 약화시키지 않았음을 확인했다.
- 관찰(OBS, 결함 아님, 각각 심각도 낮음 · 후속 참고용):
  - OBS-6(v5): 정리 헬퍼의 핵심 계약(비마커 면접 참조 중단, 롤백, FK 연쇄, 비-UUID 명시 이메일 거부)은 06의 임시 시나리오로만 검증됐고 저장소의 `backend/tests/`에는 스모크의 일부(6건)와 가짜 연결 7건뿐이다. 후속 유닛이 실DB 계약 테스트(`test_cleanup_contract.py` 등)를 추가하면 07/08이 06 없이도 회귀를 재실행할 수 있다(선택 사항).
  - OBS-7(v5): `_connect()`의 "(제한 5초)" 문구가 오설정(잘못된 포트/sslmode) 오류에도 붙는다 — 문구만의 문제.
  - OBS-8(v5): `cleanup_test_data`의 반환 dict에 `stray_users` 키가 추가되었다(`--email` 경로에서는 항상 0). 호출자가 dict 전체를 리터럴과 비교하면 깨질 수 있다(06의 v4 시나리오도 갱신 필요했음).
  - OBS-9(v5): `test_cleanup_helper.py`의 더미 DSN 비밀번호 `secretpw`는 누출 검사용 센티널이지만 시크릿 스캐너가 오탐할 수 있다.
  - OBS-1: `pytest` 서버 미기동 시 체인 예외가 반복 출력되어 소음이 크다(첫 줄 메시지는 명확). 기능 영향 없음.
  - OBS-2: 정리 헬퍼가 "범위 밖 **마커** 계정이 참조하는 면접"에서도 "비-마커 면접" 문구로 중단한다(TC-038). 안전 방향이지만 문구가 부정확하고, 여러 마커 계정이 서로 면접으로 얽힌 시나리오(지원자↔채용담당자)는 **같이 정리 목록에 넣어야** 한다. `account_factory`는 세션 종료 시 일괄 정리하므로 자동 경로는 문제없다. 07/08이 계정 단위로 쪼개 정리하려면 주의.
  - OBS-3: 테스트 계정 객체(`HarnessAccount`)의 repr에 비밀번호·토큰이 포함되어 단언 실패 출력에 노출될 수 있다. 값은 랜덤·일회성이고 곧 삭제되는 계정이라 위험은 낮다.
  - OBS-4: (구) `--all` 전체 중단은 안전 방향 설계이나 실환경에서 dry-run까지 막는 문제가 확인되어 **DEF-003**으로 승격(TC-037 → TC-055).
  - OBS-5: 저장소 내 캐시 폴더: `backend/.ruff_cache`는 기존 디렉터리(자기 자신을 ignore), `backend/tests/__pycache__`는 05의 이전 실행이 만든 기존 폴더 — 06이 새로 만든 것은 `backend/.pytest_cache`뿐이다(7절).

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K

### 7-B. 재검증(v5) Teardown — [[V5_TEARDOWN]]

### 7-A. 최초 실행(v4, 2026-09-20 02:27~03:05 KST) Teardown — 이력 보존
- 이번 테스트에서 생성한 임시 아티팩트 목록 (경로 포함) 및 처리:
  | 아티팩트 | 처리 |
  |---|---|
  | `.harness-tmp/venv_06_unit22/`(경량 venv, pytest/httpx/psycopg/ruff/coverage) | **삭제 완료** |
  | `.harness-tmp/u22t06_*`(기동 스크립트 `u22t06_start.ps1`, PID 파일 `u22t06_pids.txt`, 서버 로그 `u22t06_uvicorn.log/.err`, 스냅샷 `u22t06_snap.py`·`u22t06_snap_before.json`, 시나리오 `u22t06_scen.py`·`u22t06_extra.py`·`u22t06_g.py`·`u22t06_i.py`), `.harness-tmp/u22t06.coverage`, `.harness-tmp/u22t_tsbi_before.txt` | **삭제 완료** |
  | `.harness-tmp/u22t_neg/`(Playwright 변조 사본·probe), `.harness-tmp/u22t_neg_be/`(백엔드 스모크 변조 사본), `.harness-tmp/u22t_guard/`(teardown 가드 시나리오) | **삭제 완료** |
  | `frontend/test-results/`, `frontend/playwright-report/`, `backend/.pytest_cache/`(gitignore 대상, 시작 시 존재하지 않았음을 확인 → 전부 06이 만든 것) | **삭제 완료** |
  | uvicorn 프로세스(포트 8422): 런처 PID **34320** / 리스너 PID **28920** | `Stop-Process -Id`로 두 PID만 종료, `Get-NetTCPConnection -LocalPort 8422 -State Listen` 결과 없음, 두 PID 잔존 0 확인 (`/IM python.exe` 등 이름 기준 종료 미사용) |
  | DB 임시 행(마커 계정·연쇄 데이터, canary/stray 행, `u22t06` 템플릿) | 각 시나리오 `finally`에서 정리. 최종 조회: `u22t06%` 이메일 0건, `u22t06` 템플릿 0건, 엄격 UUID 형식 마커 행 0건, 팩토리 이름(`harness-*`) 사용자 0건 |
  | `.harness-tmp/` 밖: 프로젝트 소스 수정 **없음**(06 산출물 2개 제외) — 06 종료 시점 sha256(`frontend/e2e/smoke.spec.ts` `3bc4ef90…`, `playwright.config.ts` `d2cd4309…`, `backend/tests/test_smoke.py` `be841a8c…`, `conftest.py` `86709eb2…`, `support/__init__.py` `e3b0c442…`, `accounts.py` `5582a191…`, `cleanup.py` `0ca4bcfc…`)가 06이 코드 검토 직후 기록한 값과 동일(중간에 06이 바꾼 것 없음) | 코드 무수정 증명(코드 수정 금지 준수) |
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): [x] 예 — 예외로 `frontend/test-results`·`frontend/playwright-report`·`backend/.pytest_cache`는 각 도구의 고정 출력 위치라 저장소 하위에 생기지만 `.gitignore` 대상이며 위 표대로 삭제함. `backend/.ruff_cache`(2026-09-19 생성, 자기 자신을 ignore)와 `backend/tests/__pycache__`(05의 이전 실행이 만든 폴더)는 06이 새로 만든 것이 아니어서 남겼다.
- 정리(삭제) 완료 여부: **완료**. 정리 직후 `.harness-tmp/` 목록에서 `u22*`는 0건. 남은 항목은 (i) 06 시작 전부터 있던 기존 잔여물(`venv_05_unit5/6/7/9/12/13`, `venv_06_unit5`, `unit9/12/13_server.log`) — **미접촉**(특히 `venv_05_unit7`은 읽기 전용 실행만 함), (ii) 타 에이전트 소유(`u19_*` 12개 — unit-19 05). 06 시작 시 있던 `u20_*`·`u7t_*`·`__pycache__`는 06이 삭제하지 않았으며 소유 에이전트가 자체 정리한 것으로 보인다(06은 해당 파일을 만지지 않음).
- 정리 후 `git status` 실행 결과 (그대로 첨부, 요약 금지 — `git status` 전문. `--short` 형식으로도 동일 내용을 확인함):
```
On branch PROD
Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
	modified:   .gitignore
	modified:   backend/alembic/env.py
	modified:   backend/app/api/v1/interviews.py
	modified:   backend/app/api/v1/ws.py
	modified:   backend/app/core/config.py
	modified:   backend/app/main.py
	modified:   backend/app/models/transcript.py
	modified:   backend/app/schemas/interview.py
	modified:   backend/app/services/job_queue.py
	modified:   backend/docker-compose.yml
	modified:   backend/pyproject.toml
	modified:   backend/requirements-dev.txt
	modified:   backend/requirements.txt
	modified:   docs/harness/02-planning.md
	modified:   docs/harness/decisions.md
	modified:   docs/harness/traceability.md
	modified:   docs/harness/verify-log_02-planning.md
	modified:   frontend/app/globals.css
	modified:   frontend/app/interviews/[id]/components/CodeEditorPanel.tsx
	modified:   frontend/app/interviews/[id]/components/WhiteboardCanvas.tsx
	modified:   frontend/app/interviews/[id]/page.tsx
	modified:   frontend/app/page.tsx
	modified:   frontend/components/WebcamPreview.tsx
	modified:   frontend/lib/api.ts
	modified:   frontend/package-lock.json
	modified:   frontend/package.json
	modified:   frontend/tsconfig.tsbuildinfo

Untracked files:
  (use "git add <file>..." to include in what will be committed)
	"99.\355\230\204\354\236\254\354\203\201\355\203\234/"
	backend/alembic/versions/e4b6a1c9f2d7_v8_questions_rag.py
	backend/app/models/question.py
	backend/app/services/celery_app.py
	backend/app/services/interview_prompts.py
	backend/app/services/llm_engine.py
	backend/app/services/rag_engine.py
	backend/app/services/seed_questions.py
	backend/app/services/ws_publisher.py
	backend/app/worker/
	backend/tests/
	docs/harness/test-infra.md
	docs/harness/units/unit-19-note.md
	docs/harness/units/unit-20-note.md
	docs/harness/units/unit-22-note.md
	docs/harness/units/unit-22-test.md
	docs/harness/units/unit-7-note.md
	docs/harness/units/unit-7-test.md
	docs/harness/verify-log_unit-7-test.md
	frontend/app/interviews/[id]/components/InterviewSidePanel.tsx
	frontend/components/CandidateHome.module.css
	frontend/components/CandidateHome.tsx
	frontend/e2e/
	frontend/lib/useMediaQuery.ts
	frontend/playwright.config.ts

no changes added to commit (use "git add <file>..." to update what will be committed)
```
  (이 출력은 2026-09-20 02:57 KST, `docs/harness/verify-log_unit-22-test.md` 생성 **직전**의 측정이다. 이후 03:0x KST 재측정(`git status --short`, 52줄)과의 차이는 두 가지뿐이다: ① 위 목록에 없던 `?? docs/harness/verify-log_unit-22-test.md`(06 산출물)가 추가됨, ② ` M frontend/tsconfig.tsbuildinfo` 줄이 **사라짐** — 타 에이전트가 이 생성물을 원복한 것으로 보이며 06이 한 일이 아니다(06은 `git checkout`/복원을 하지 않음).)
  - **이 유닛 변경(05 산출물)**: ` M .gitignore`, ` M backend/pyproject.toml`, ` M backend/requirements-dev.txt`, ` M frontend/package.json`, ` M frontend/package-lock.json`, `?? backend/tests/`, `?? docs/harness/test-infra.md`, `?? docs/harness/units/unit-22-note.md`, `?? frontend/e2e/`, `?? frontend/playwright.config.ts`. **06 산출물**: `?? docs/harness/units/unit-22-test.md`(이 문서), `?? docs/harness/verify-log_unit-22-test.md`.
  - **병렬 타 유닛 변경(이 유닛과 무관, 06이 만들지도 되돌리지도 않음)**: unit-7(`backend/alembic/env.py`, `backend/app/api/v1/ws.py`, `backend/app/core/config.py`, `backend/app/main.py`, `backend/app/models/transcript.py`, `backend/app/services/job_queue.py`, `backend/docker-compose.yml`, `backend/requirements.txt`, 신규 `backend/alembic/versions/e4b6a1c9f2d7_v8_questions_rag.py`, `backend/app/models/question.py`, `backend/app/services/{celery_app,interview_prompts,llm_engine,rag_engine,seed_questions,ws_publisher}.py`, `backend/app/worker/`, `docs/harness/units/unit-7-note.md`, `unit-7-test.md`, `verify-log_unit-7-test.md`), unit-19(`backend/app/api/v1/interviews.py`, `backend/app/schemas/interview.py`, `frontend/app/page.tsx`, `frontend/lib/api.ts`, `frontend/components/CandidateHome.{tsx,module.css}`, `docs/harness/units/unit-19-note.md`), unit-20(`frontend/app/globals.css`, `frontend/app/interviews/[id]/components/{CodeEditorPanel,WhiteboardCanvas,InterviewSidePanel}.tsx`, `frontend/app/interviews/[id]/page.tsx`, `frontend/components/WebcamPreview.tsx`, `frontend/lib/useMediaQuery.ts`, `docs/harness/units/unit-20-note.md`), 02 문서 갱신·오케스트레이터(`docs/harness/02-planning.md`, `decisions.md`, `traceability.md`, `verify-log_02-planning.md`). `?? "99.현재상태/"`는 06 시작 시점 `git status`에 이미 있던 항목(출처 미확인, 06 무관).
  - `frontend/tsconfig.tsbuildinfo`: 06 시작 시 ` M`, 종료 직전(02:57) ` M`, 03:0x 재측정 시 ` M` 없음. 그 사이에도 ` M`이 사라졌다가(타 에이전트가 원복한 것으로 보임) 다시 생기는 등 **타 유닛 에이전트들이 tsc를 돌릴 때마다 바뀐다**(내가 관측한 해시: `7321a45f…` → `eb6dc015…` → `ffee8325…`, 06의 tsc 실행 전후 해시는 매번 동일). 06은 `tsc --noEmit --incremental false`만 사용했고, 플래그 없는 tsc 동작 관찰(TC-054)은 `--tsBuildInfoFile`을 `.harness-tmp/`로 돌려 추적 파일을 건드리지 않았다. 06은 이 파일을 복원(`git checkout`)하지 않았고 이 유닛의 변경으로도 취급하지 않는다.
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: [x] 없음 — 단, DB 접속 불가 케이스(TC-053) 실행 중 도구의 120초 제한으로 명령 하나가 백그라운드로 전환된 적이 있으나 스스로 종료(exit 0)했고, 그 뒤 `timeout` 래퍼로 재확인했으므로 중단·잔여 프로세스는 없다(`tests.support.cleanup` 프로세스 잔존 0건을 CIM 조회로 확인).
- **이 절이 미완성이거나 `git status`가 깨끗함을 확인하지 못했다면, 8절에서 PASS로 판정할 수 없다 (규칙 K 2번).** → 위 확인으로 충족(본 유닛+06 산출물+타 유닛 변경 외 잔여물 없음).

## 8. 리스크 및 잔존 이슈
- 이번 테스트로 커버되지 않는 알려진 리스크:
  - 스모크는 "브라우저가 뜨고 렌더링한다"만 증명한다. 특정 앱 화면(면접장 등)의 동작은 미검증 — unit-20의 06이 앱 화면 e2e를 처음 작성할 때 실증해야 한다(Next 서버 직렬화 규칙 §5.4 준수).
  - 정리 헬퍼는 현재 스키마(8 테이블) 기준이다. `users`/`interviews`를 참조하는 새 테이블(예: 리포트)이 추가되면 `support/cleanup.py`의 조회·삭제 목록을 함께 갱신해야 한다(누락 시 FK 위반으로 롤백되어 정리 실패 — 오삭제는 아님). 테스트 계정을 만드는 새 테스트가 세션 종료 시 `CleanupError`를 내면 우선 이 점을 의심할 것.
  - 실DB에서의 `--all` 실삭제 경로는 지시상 미실행(5절). stray 중단은 가짜 연결 테스트+변이로, 나머지 삭제 계약은 `--email` 범위 실삭제로 검증했다.
  - 정리 헬퍼의 핵심 계약 회귀 테스트가 저장소에는 일부만 보존됨(OBS-6).
  - **stray 정책의 운영 영향(재작업으로 생긴 설계 결정)**: 실삭제는 stray가 1건이라도 있으면 전체 중단한다(보수적). 따라서 어떤 유닛이 비-UUID 마커형 계정을 만들어 남기면 `--all` 실삭제형 정리는 불가능하고, `--all --dry-run`은 exit 3으로 이를 알리기만 한다.
  - Windows 콘솔 인코딩: 한국어 출력은 `PYTHONUTF8=1` 권장(note §3에도 명시).
  - DEF-001~003은 v5에서 모두 Fixed다(6절). Open 결함 없음.
- 미해결 질문(규칙 A 형식: `[단계번호] 질문 / 왜 판단이 안 되는지 / 선택지·트레이드오프`) — 진행을 막지는 않는 비차단 질문:
  1. **[06→오케스트레이터, 08 착수 전] 08의 "잔여 마커 확인"에서 `--all --dry-run`이 exit 3(stray 존재)을 반환하면 08을 어떻게 처리할 것인가?** / stray 처리는 06의 권한 밖이고, exit 3을 PASS로 볼지 FAIL로 볼지는 08의 완료 조건 해석이다. / 선택지: (a) exit 0만 PASS로 인정하고 stray는 소유 유닛이 정리할 때까지 08을 보류 — 엄격하나 병렬 작업이 남아 있으면 지연됨, (b) exit 3은 "정상 마커 users=0"인 경우에 한해 경고 + 소유자 정리 요청으로 통과 — 진행은 빠르나 테스트 데이터 잔존을 허용함. 
  2. **[06→오케스트레이터] 실DB 계약 테스트(비마커 면접 참조 중단, 롤백, FK 연쇄)를 저장소 `backend/tests/`에 보존하는 후속 작업을 만들지?** (OBS-6) / 현재는 06의 임시 시나리오로만 검증되어 07/08이 06 없이 회귀를 재실행할 수 없다. / 선택지: (a) 별도 소규모 유닛/재작업으로 `test_cleanup_contract.py` 추가(실DB·서버 필요, 마커 계정 자체 생성·정리로 병렬 안전) — 재실행 가능성↑, (b) 지금은 보류하고 07 통합 시점에 필요하면 추가 — 비용 0이나 회귀 검증이 06 의존.
- 후속 조치가 필요한 항목:
  1. 07/08/unit-19·20 06이 이 인프라를 쓸 때의 제약(v4에서 유지): API 서버와 `DATABASE_URL`이 **같은 DB**여야 함(불일치 시 세션 종료에서 실패로 드러남, TC-022); `--all` 실삭제 금지(병렬 에이전트 계정 삭제 위험) — 08 마무리 시점에 병렬 작업이 끝난 뒤 `--all --dry-run`으로 잔여 확인(**exit 0=잔여 없음, 3=stray 존재(소유자 정리 필요), 1=DB 불통/오류**); 서로 참조하는 마커 계정(지원자↔채용담당자)은 함께 정리(OBS-2); 계정은 반드시 `account_factory`(UUID 마커)로만 생성; 서버·PID 규칙(DEC-028)과 프런트 `.next` 직렬화; 프런트 스펙이 계정을 만들면 백엔드 CLI로 정리(Node 헬퍼 없음).
  2. `cleanup_test_data`의 반환 dict에 `stray_users` 키가 추가되었으므로 dict를 통째로 비교하는 코드는 갱신(OBS-8).
  3. `frontend/tsconfig.tsbuildinfo`·`next-env.d.ts`는 이 유닛의 변경이 아니며 타 유닛이 갱신하는 생성물이다. 문서의 `tsc` 명령은 `--incremental false`로 통일되었다(DEF-002 Fixed).

## 9. 결론 및 판정
- [x] **PASS** — 다음 단계 진행 가능 (7절 Teardown 확인 완료가 전제조건 → 7-B 완료)
- [ ] CONDITIONAL PASS — (v4 판정이었음. 조건이던 DEF-001/002/003이 v5에서 모두 Fixed·재검증 PASS로 해소됨)
- [ ] FAIL — 해당 없음
- 근거 요약: ① 인수조건 13개 전부 PASS(v4)이며 재작업이 관련 계약을 약화시키지 않았음을 회귀로 확인(TC-057, 64/64), ② DEF-001/002/003 Fixed(TC-053/054/055, 변이 10/10 kill), ③ 신규 테스트 7건이 서버 없이 통과·계약을 고정(TC-056/058), ④ `cleanup.py` 문장·분기 100% 실행(5절), ⑤ 실사용자 데이터 무변화(TC-060), ⑥ 재검증 중 신규 결함 0건, ⑦ 7-B Teardown 완료·`git status` 전문 첨부, ⑧ 규칙 B: 재작업 이후 검증을 처음부터 수행(10절).
- 07 대상이 아닌 공통 인프라라 07 handoff는 없다(02-planning v3). `traceability.md`·`decisions.md`·`02-planning.md`는 지시에 따라 수정하지 않았다(오케스트레이터 소관 — 필요 시 DEC-033 후속 기록은 오케스트레이터가 수행).

## 10. 내부 검증 (최소 2회, `verification-log-template.md` 사용)
- 1차 검증 결과 요약(자가 재검토, v0→v1): 결함 5건 발견·수정 — 단언 개수 과대 기재(90→실측 63), f-string 개수 오기, 근거 없는 서술("타 프로젝트 잔존물"), openapi 경로 열거 불완전, 표 안의 파이프 문자 등 서식. 인수조건 13개 ↔ TC 1:1 매핑 완결 확인.
- 2차 검증 결과 요약(처음 받는 심사자 관점 + 전체 명령 재실행, v1→v2): **결함 4건** 발견·수정 — ① 재실행 중 신규 실측 결함 **DEF-003**(타 유닛의 비-UUID 마커형 계정 때문에 `--all --dry-run` 중단) 및 TC-055 누락, ② AC7/TC-020 서술이 02:53 KST 이후 사실과 불일치, ③ note §2 편차 5건에 대한 명시적 판정표 누락, ④ AC13 소유 유닛 매핑에 unit-19 파일 누락 및 TC-021 최종 스냅샷 비교 미반영.
- 3차 검증 결과 요약(v2→v3): 표·수치 교차검증 스크립트와 Teardown 사후 조회는 통과했으나 **결함 1건**(7절 `git status` 전문의 한글 경로 표기가 이스케이프 오류로 깨져 기록) 발견·수정.
- 4차 검증 결과 요약(v3→v4): 수정 확인·재대조는 통과했으나 **결함 1건**(검증 로그 자체의 동일 유형 표기 깨짐 + 결과서에 규칙 A 형식 미해결 질문 소절 누락) 발견·수정 → §8에 미해결 질문 소절 추가.
- 5차 검증 결과 요약(v4): 두 파일 깨진 문자 검사·TC 표 집계(55건, 52 PASS/3 FAIL)·미해결 질문/9절 일치·`git status` 재대조 통과 → **결함 0건, 확정**.
- 검증 로그 파일 경로: `docs/harness/verify-log_unit-22-test.md`
