# 공통 테스트 인프라 (unit-22, DEC-030)

- 작성: 2026-09-20 02:25 KST (`05-unit-developer`, unit-22)
- 목적: 06(단위)·07(통합/회귀)·08(전체) 에이전트가 **저장소에 보존된 테스트 코드를 재실행**한다. 임시 스크립트를 매번 만들고 지우는 방식은 더 쓰지 않는다.
- 범위 밖: 앱 기능 테스트 자체. 이 문서는 도구·규약만 다룬다. DEC-001(MCP 미연동)은 그대로 유지한다 (브라우저 자동화는 MCP가 아니라 저장소의 `@playwright/test`).

## 1. 구성 한눈에 보기

| 영역 | 도구 | 테스트 위치 | 설정 |
|---|---|---|---|
| 백엔드 | pytest + httpx (+ psycopg: 정리 헬퍼용) | `backend/tests/` | `backend/pyproject.toml` `[tool.pytest.ini_options]` |
| 프런트 | `@playwright/test` (chromium만) | `frontend/e2e/` | `frontend/playwright.config.ts` |

## 2. 백엔드 (pytest)

### 2.1 사전 조건 (실행자가 준비, 자동 기동 없음)
1. DB(`final-project-db`, 5544)가 떠 있고 마이그레이션이 적용되어 있다. Redis/Celery는 스모크에는 불필요하다 (기능 테스트가 필요로 하면 그 feature의 노트를 따른다).
2. API 서버를 **실행자가 직접, 자기 전용 포트로** 띄운다 (§4).
3. 환경변수
   - `API_BASE_URL` — 서버 주소. 기본 `http://127.0.0.1:8000`. 병렬 실행 시 자기 포트를 반드시 지정한다.
   - `DATABASE_URL` — 정리 헬퍼용 DB 접속 문자열. 없으면 앱과 같은 관례로 `backend/.env`의 `DATABASE_URL`을 읽는다. **코드에 자격증명을 넣지 않는다.** API 서버와 **같은 DB**를 가리켜야 한다.

### 2.2 venv (경량, `.harness-tmp/` 하위 — 규칙 K)
전체 `requirements.txt`(torch 등 대용량)는 설치하지 않는다. 테스트 러너에 필요한 것만 설치한다.

```bash
python -m venv .harness-tmp/venv_<단계>_<유닛>
.harness-tmp/venv_<단계>_<유닛>/Scripts/python.exe -m pip install pytest httpx "psycopg[binary]>=3.2,<3.3" "ruff>=0.16,<0.17"
```
(`backend/requirements-dev.txt`에는 `pytest`, `httpx`가 추가되어 있다. 이 파일은 `-r requirements.txt`를 포함하므로 통째로 설치하면 대용량 의존성이 들어온다. 러너 venv는 위처럼 필요한 것만 설치하는 것을 권장한다. 다른 유닛의 venv는 읽기/실행 외에 수정하지 않는다 — DEC-027.)

### 2.3 실행
```bash
cd backend
API_BASE_URL=http://127.0.0.1:<내포트> <venv>/Scripts/python.exe -m pytest -v
# 정리 헬퍼 출력(삭제 전 건수)까지 보려면 -s 추가
```
- `backend/`에서 실행해야 `tests` 패키지 import와 `pyproject.toml` 설정이 잡힌다.
- 서버에 연결하지 못하면 `api` 픽스처가 원인과 함께 즉시 실패한다 (조용히 스킵하지 않는다).
- 린트: `cd backend && <venv>/Scripts/ruff.exe check tests` (프로젝트 `pyproject.toml` 규칙 그대로).

### 2.4 디렉터리 규약
```
backend/tests/
  conftest.py            # 공용 픽스처: api(세션 httpx.Client), account_factory(세션, 종료 시 자동 정리)
  support/accounts.py    # 계정 팩토리 + 마커 이메일 규칙
  support/cleanup.py     # 정리 헬퍼 (라이브러리 + CLI)
  test_smoke.py          # 인프라 스모크
  <feature>/             # 예: interviews/, consents/ — 각 폴더에 __init__.py 필수 (동일 파일명 충돌 방지)
    test_<주제>.py
```
- 새 feature 테스트는 `backend/tests/<feature>/test_*.py`에 추가한다. 공용 픽스처는 `tests/conftest.py`를 그대로 상속받는다.
- 경로는 `API_V1` 상수(`/api/v1`)로 조립한다: `api.get(f"{API_V1}/...")`. `api`의 base URL은 서버 루트이므로 `/media/...`, `/ws/...`도 그대로 쓴다.
- 계정 인증은 Bearer 토큰만 쓴다. 로그인 헬퍼는 세션 공유 클라이언트의 refresh 쿠키를 비운다 (계정 간 상태 오염 방지).

## 3. 테스트 데이터 규약 (필수)

1. **모든 테스트 계정은 `AccountFactory`(`account_factory.create("candidate"|"recruiter")`)로 만든다.** 이메일은 `harness_test_<uuid4>@harness-test.example` 형식이며 비밀번호는 매번 랜덤 생성이다 (하드코딩 없음).
   - 도메인이 `.invalid`가 아니라 `.example`인 이유: 앱의 `EmailStr`(email-validator)가 `.invalid`를 예약 TLD로 보고 가입을 422로 거부한다 (실측). 둘 다 RFC 예약 도메인이라 실메일이 존재할 수 없다는 성질은 같다. 도메인 변경은 `accounts.MARKER_DOMAIN` 한 곳에서만 한다.
2. **정리 헬퍼 사용은 의무다.** `account_factory` 픽스처를 쓰면 세션 종료 시 **그 세션이 만든 계정만** 자동 정리된다 (생성한 계정 수보다 DB에서 찾은 수가 적으면 API 서버와 `DATABASE_URL`이 다른 DB를 가리키는 것이므로 실패시킨다). 팩토리를 우회해 직접 만든 계정은 `finally`에서 `cleanup_test_data([...])`를 호출한다.
3. 정리 헬퍼의 안전장치:
   - 형식(`MARKER_EMAIL_RE`)에 맞지 않는 이메일이 하나라도 있으면 DB 접근 전에 `UnsafeCleanupTarget`으로 거부.
   - SQL `LIKE` 결과도 정규식으로 재검증.
   - 삭제 전에 `[harness cleanup] 삭제 예정: users=N, interviews=N, ...`을 출력. 삭제 건수가 조회 건수와 다르면 트랜잭션 전체 롤백.
   - 비-마커(실사용자) 면접이 마커 채용담당자/템플릿을 참조하면 아무것도 지우지 않고 중단.
   - DB에 연결할 수 없으면 5초(`CONNECT_TIMEOUT_SECONDS`) 안에 `CleanupError`로 끝난다 (teardown 무기한 대기 없음, 삭제도 일어나지 않음).
   - `--all` 조회에 **UUID 형식이 아닌 마커형 계정(stray)**이 섞여 있으면: 실삭제는 아무것도 지우지 않고 중단하고, `--dry-run`은 정상 마커 건수를 집계하면서 stray를 별도 목록·건수(`stray_users`)로 보고한다. stray는 어떤 경우에도 헬퍼가 삭제하지 않는다 (소유자가 확인 후 수동 SQL로 정리).
   - 단일 트랜잭션 + FK 의존 순서(`transcripts`/`code_submissions`/`whiteboard_snapshots` -> `interviews` -> `consents`/`deletion_requests`/`rubric_templates` -> `users`). **새 테이블이 `users`/`interviews`를 참조하게 되면 `support/cleanup.py`의 조회/삭제 목록에 추가해야 한다** (누락 시 FK 위반으로 롤백되어 아무것도 지워지지 않으므로 조용히 오삭제되지는 않는다).
4. CLI (필요 시 수동 정리, `backend/`에서):
   ```bash
   <venv>/Scripts/python.exe -m tests.support.cleanup --email <마커 이메일> [--dry-run]
   <venv>/Scripts/python.exe -m tests.support.cleanup --all --dry-run   # 마커 계정 전체 건수 확인
   ```
   `--all`은 **병렬로 돌고 있는 다른 에이전트의 테스트 계정도 지운다**. 병렬 실행 중에는 쓰지 말고, 반드시 `--dry-run`으로 건수를 먼저 확인한다. 자동 정리는 `--all`을 쓰지 않는다.

   CLI 종료코드: `0` 정상(stray 없음) / `1` 실패·중단(DB 연결 불가, 비마커 이메일 거부, 실삭제 중 stray 발견, 참조 중단 등) / `3` 집계는 정상이나 stray 존재(`--all --dry-run` 전용. `2`는 argparse 사용법 오류라 피했다).

   **계정은 반드시 `account_factory`(`harness_test_<uuid4>` 형식)로만 만든다.** 직접 만든 비-UUID 마커형 계정(예: `harness_test_<12hex>@...`)은 헬퍼로 정리할 수 없고 stray로만 보고된다. 이미 그런 계정이 생겼다면 소유 에이전트가 확인 후 수동으로 정리한다.
5. 마커 이메일이 아닌 계정·데이터는 어떤 테스트도 삭제하지 않는다. 테스트가 만든 그 외 임시 데이터(질문은행 행 등)는 그 테스트가 스스로 정리한다.

## 4. 서버 기동·종료 규칙 (DEC-028, DEC-032)

- **서버는 테스트 실행자가 자기 PID 규칙으로 띄운다.** 테스트 코드·설정은 서버를 자동 기동하지 않는다 (`playwright.config.ts`에도 `webServer`가 없다).
- 포트는 다른 실행자와 겹치지 않게 지정한다 (`netstat -ano | grep :<포트>`로 비어 있는지 먼저 확인).
- 기동한 프로세스의 PID를 파일(`.harness-tmp/<유닛>_pids.txt` 등)에 기록하고 **그 PID로만 종료**한다 (`Stop-Process -Id <PID>` / `taskkill /F /PID <PID>`). `taskkill /IM python.exe`, `pkill python` 같은 이름 기준 종료는 금지.
- Windows에서 `python -m uvicorn`을 `Start-Process`로 띄우면 런처 PID와 실제 리스너 PID가 다를 수 있다. `netstat -ano | grep :<포트>`의 LISTENING PID까지 함께 기록하고 둘 다 종료한다.
- 백엔드 서버용 venv는 백엔드 전체 의존성이 필요하므로 그 유닛 전용 venv를 쓰고 (다른 유닛 venv에 pip install 금지), 러너 venv(§2.2)와 분리해도 된다.

## 5. 프런트 (Playwright)

### 5.1 사전 준비
- `frontend/node_modules`에 `@playwright/test`가 설치되어 있다 (`npm ls @playwright/test`). 최초 1회 브라우저 바이너리: `cd frontend && npx playwright install chromium` (사용자 승인됨, DEC-030). 캐시 위치는 사용자 홈의 `ms-playwright/`이며 저장소 밖이다.
- 앱 화면을 검증하는 스펙은 실행자가 Next 서버를 띄우고 `E2E_BASE_URL`로 주소를 알린다 (기본 `http://127.0.0.1:3000`).

### 5.2 실행
```bash
cd frontend
npm run test:e2e                                   # 전체
npx playwright test e2e/<feature>/                 # feature 단위
E2E_BASE_URL=http://127.0.0.1:<내포트> npm run test:e2e
```
- 인프라 스모크(`e2e/smoke.spec.ts`)는 Next 앱·백엔드 없이 통과해야 정상이다 (`setContent`/`file://`로 브라우저 기동·한국어 렌더링·스크린샷만 확인).
- 산출물: `frontend/test-results/`(스크린샷/trace), `frontend/playwright-report/`(HTML). 둘 다 `.gitignore` 대상이다. 스펙이 만드는 파일은 `testInfo.outputPath()` 아래에만 쓴다.
- 린트/타입: `npm run lint`(eslint .), `npx tsc --noEmit --incremental false`가 `e2e/`와 `playwright.config.ts`를 포함해 통과해야 한다. `--incremental false`를 붙이는 이유: `tsconfig.json`이 `incremental: true`라 플래그 없이 실행하면 저장소에 **추적되는 생성물**(`frontend/tsconfig.tsbuildinfo`, `next-env.d.ts`)이 갱신되어 타 유닛의 변경과 섞인다 (§5.4).

### 5.3 디렉터리 규약
```
frontend/e2e/
  smoke.spec.ts          # 인프라 스모크 (앱 불필요)
  <feature>/<주제>.spec.ts   # 예: interview-room/code-editor.spec.ts
```
- 백엔드가 필요한 스펙의 테스트 계정도 §3 규약(마커 이메일 + 정리)을 따른다. 프런트 스펙이 계정을 만들 때는 가입 API 호출 후 종료 시 백엔드 정리 헬퍼(`python -m tests.support.cleanup --email ...`)를 호출하는 방식으로 정리한다 (전용 Node 헬퍼는 아직 없다 — 첫 프런트 feature 스펙을 쓰는 유닛이 필요 시 만든다).

### 5.4 `.next` 충돌 방지 — 프런트 빌드/dev 직렬화
- `next dev`, `next build`, `next start`는 모두 `frontend/.next`를 쓴다. **동시에 두 개 이상 실행하면 서로의 산출물을 깨뜨린다.** 병렬 에이전트 사이에서 프런트 서버/빌드는 직렬화한다: 실행 전에 `netstat -ano | grep :3000`과 `frontend/.next` 사용 여부를 확인하고, 다른 실행자가 쓰는 중이면 끝날 때까지 기다린다.
- 인프라 스모크나 Playwright 자체 실행(`npm run test:e2e`)은 `.next`를 쓰지 않으므로 언제든 병렬 실행해도 된다.
- 빌드 산출물(`.next`)과 `tsconfig.tsbuildinfo`는 개발 서버/tsc가 갱신하는 생성물이므로 테스트 실행자가 수동 편집하거나 되돌리지 않는다 (`tsc`는 `--incremental false`로 실행하면 이 파일을 건드리지 않는다).

## 6. 06/07/08 에이전트 재사용 방법

1. 재실행: 위 §2.3/§5.2 명령을 그대로 사용한다. 통과 기준은 노트의 인수 조건(unit-22-note.md §7)을 따른다.
2. 06(단위): 그 유닛의 테스트를 `backend/tests/<feature>/`, `frontend/e2e/<feature>/`에 **추가·보존**한다 (임시 스크립트 삭제 관행 대체). 결과서에는 실행 명령과 pass/fail 개수를 적는다.
3. 07(통합/회귀): feature 폴더 전체 + 이전 feature 폴더를 다시 실행해 회귀를 증명한다. `backend/tests`는 `python -m pytest`(전체), 프런트는 `npm run test:e2e`(전체).
4. 08(전체): 전체 스위트 재실행 + 남은 마커 계정이 없는지 `python -m tests.support.cleanup --all --dry-run`의 `users=0`으로 확인한다 (병렬 작업이 끝난 뒤에만).
5. Teardown(규칙 K): 자기 venv와 자기가 띄운 서버 PID만 정리하고 `git status`가 (본 작업 + 타 유닛 변경) 외 잔여물이 없음을 결과서에 남긴다. `frontend/test-results/`, `frontend/playwright-report/`, `backend/.pytest_cache/`는 gitignore 대상이지만 자기가 만든 것은 삭제한다.
6. 브라우저로 확인하지 못한 항목이 있으면 (예: 실제 카메라/마이크 하드웨어) 그 사실을 결과서에 명시한다. 스모크가 통과했다는 것은 "브라우저가 뜬다"는 증명일 뿐, 특정 화면이 정상이라는 증명이 아니다.
