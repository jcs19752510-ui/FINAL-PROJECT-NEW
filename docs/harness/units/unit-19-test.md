# 테스트 결과서 — unit-19 (GET /interviews + [C-03] 지원자 홈, REQ-002)

> 이 문서는 `docs/harness/units/unit-19-test.md`의 완결본이다("v0 작업 중 초안" 대체). 이전 세션은 API 사용량 한도로 2회 강제 중단되었고, 본 세션이 남은 작업(Next 빌드/UI 스펙 실행/게이트/결과서/검증로그/Teardown)을 이어받아 완료했다.

## 1. 개요
- 테스트 대상: `GET /api/v1/interviews`(내 면접 목록, `backend/app/api/v1/interviews.py`) + `[C-03]` 지원자 홈(`frontend/components/CandidateHome.tsx`, `frontend/app/page.tsx`) — 업무 단위(feature) B의 unit-19, REQ-002
- 테스트 유형: 단위 (06단계)
- 적용 Tier: **High** (규칙 B 원문, 완화 없음)
- 적용 속도 트랙: **L3(일반)** — 06 정식(10섹션 전체), 07 정식, 부채 없음 (`unit-19-note.md` 표기, DEC-031)
- 테스트 목적: 05단계 구현이 `03-system-design.md` §4.2(`GET /interviews`), `04-ux-design.md` §2 `[C-03]`·§1.1(재접속 플로우)·§5(접근성)·§6(반응형)의 요구사항과 `unit-19-note.md` §9의 인수 조건(AC-B1~B12, AC-F1~F15)을 충족하는지 자동화 테스트(API 수준 + 브라우저 수준)로 증명한다.
- 관련 산출물: `docs/harness/03-system-design.md` §3.1/§4.2/§4.3/§6.1, `docs/harness/04-ux-design.md` §2 `[C-03]`·§1.1·§5·§6, `docs/harness/02-planning.md` §9 unit-19, `docs/harness/units/unit-19-note.md`(05단계 구현 노트, 인수 조건 원본), `docs/harness/test-infra.md`(unit-22 공통 테스트 인프라 표준)
- 테스트 수행자(에이전트): `06-unit-tester`
- 테스트 일시: 2026-09-20 (05 구현 03:0x KST → 06 1차 세션 07:2x~07:5x KST[한도로 중단, v0 초안 저장] → 06 2차 세션 22:4x~23:1x KST[본 세션, 재개 완료])

## 2. 테스트 범위 및 제외 범위
- 범위 (In-Scope):
  - 백엔드: `GET /api/v1/interviews` 인증/인가, 응답 계약(필드 집합·타입), 정렬(`COALESCE(started_at,created_at)` desc, id desc 동률 처리), lazy expiry(24h) 커밋 일관성, 소유자 격리(수평 권한 상승), 회귀(unit-2/3 기존 엔드포인트 무변경).
  - 프런트: `[C-03]` 지원자 홈의 4가지 상태(로딩/정상/빈/에러), 카드 표시(정렬·라벨·배지·점수·액션·href), 중단 세션 배너, 10건 표시 제한, 역할별 화면(candidate/recruiter/admin), 로그인/로그아웃/계정 전환, 하이드레이션(#418) 수정, 접근성(포커스 순서·대비·터치 타깃·랜드마크)·반응형(390px/320px).
  - 정적 분석/린트 게이트: 백엔드 `ruff`, 프런트 `eslint`/`tsc --noEmit`/`next build`(unit-19가 추가한 `frontend/e2e/unit-19/` 포함).
- 제외 범위 (Out-of-Scope) 및 사유:
  - `POST /interviews/{id}/start`의 Celery 파이프라인 내부 동작(질문 생성·WS 이벤트 등) — unit-7 범위, unit-19는 `/start` 호출 후 `status=live`로의 **동기 전이**만 회귀 확인(§4 AC-B11).
  - 리포트 화면(`[C-10]`/`[C-11]`) 자체 — unit-10/11 범위. 배지는 상태 표시만 검증.
  - 레이트리밋(`POST /interviews`) — REQ-038/unit-8 범위. §8 리스크로만 기록.
  - 실기 스크린리더 낭독, 다크/고대비 테마(설계상 라이트 단일) — §8에 미검증 사실 기록.
  - 실카메라/마이크 하드웨어 — 이 화면에 해당 없음.

## 3. 테스트 환경
- 실행 환경: Windows 11, Node/Next.js(저장소 `frontend`), Python 3(`\.harness-tmp\venv_05_unit7`, 읽기 전용 재사용 — 백엔드 전체 의존성 포함), Chromium(Playwright, `frontend/node_modules/@playwright/test`), Docker `final-project-db`(5544, 기존 공용 컨테이너)·`final-project-redis`(6389, 기존 공용 컨테이너, 논리 DB 12로 격리).
- 백엔드: `uvicorn app.main:app --port 8720`, 환경변수 `REDIS_URL=redis://localhost:6389/12`(unit-7/20이 쓰는 6389 자체는 공유 Redis 데몬이고 병렬 유닛과 겹치지 않는 논리 DB만 격리 사용), `CORS_ORIGINS=http://localhost:3720,http://127.0.0.1:3720`, `COOKIE_SECURE=false`.
- 프런트: `NEXT_PUBLIC_API_BASE_URL=http://localhost:8720/api/v1`로 `next build` 1회(§7 참고, 이후 기본값으로 원복 시도), `next start -p 3720`.
- 테스트 데이터: 모든 계정은 `test-infra.md` §3 규약대로 `AccountKit`(`frontend/e2e/unit-19/helpers.ts`)이 `harness_test_<uuid4>@harness-test.example` 형식으로 생성하고, Playwright fixture(`kit`)의 `finally`에서 정확한 id로 자동 정리한다. 세션 상태(`paused`/`live`/`ready` 등)는 이를 만드는 운영 경로가 아직 없어(`unit-19-note.md` §4) `docker exec final-project-db psql`로 직접 SQL 조작한다(`setSession` 헬퍼).
- 전제 조건 (Preconditions): DB 마이그레이션 적용됨(기존 컨테이너, 21건 API 테스트가 스키마 의존 동작을 통과해 간접 확인), 포트 8720/3720 비어있음(사전 `netstat` 확인), `.harness-tmp/next.lock` 뮤텍스 획득 후 `next build`/`next start` 수행, 다른 병렬 유닛(unit-7: 8181/6389*/8091, unit-20: 8620) 포트·파일 미접촉(*6389는 Redis 데몬 포트 자체이며 논리 DB로만 분리 공유).

## 4. 테스트 케이스 및 결과

### 4.1 인수 조건 ↔ 테스트 매핑 (unit-19-note.md §9, 1:1 추적)

| AC | 절차(요약) | 테스트 파일:테스트명 | 결과 |
|----|------------|----------------------|------|
| AC-B1 | Authorization 없음 → 401 | `api-list.spec.ts:[AC-B1]` | PASS |
| AC-B2 | 쓰레기/변형 토큰 → 401 | `api-list.spec.ts:[AC-B2]`, `[AC-B2+]`(refresh 토큰·탈퇴 계정 토큰) | PASS |
| AC-B3 | 신규 candidate → `200 []` | `api-list.spec.ts:[AC-B3]` | PASS |
| AC-B4 | recruiter → 403 | `api-list.spec.ts:[AC-B4]`(세션 유무·recruiter_id 지정과 무관, DB 롤 변경 즉시 반영까지 확인) | PASS |
| AC-B5 | `POST` 3회 → 3건 scheduled/none/resumable=false, 내림차순 | `api-list.spec.ts:[AC-B5]` | PASS |
| AC-B6 | 7상태 혼합 → DB 일치·정렬 정확 | `api-list.spec.ts:[AC-B6][AC-B10]`, `[AC-B6+]`(점수 경계 0.0/10.0/99.9) | PASS |
| AC-B7 | live 25h → expired 확정, 재조회 일관 | `api-list.spec.ts:[AC-B7]`, `[AC-B7+]`(23h59m55s/24h00m05s 경계, `started_at NULL` live 무만료), `[AC-B7++]`(다건 동시 만료), `[AC-B7+++]`(동시요청 5개 경합) | PASS |
| AC-B8 | A/B 격리 | `api-list.spec.ts:[AC-B8][AC-B9]`, `[AC-B8+]`(타인 만료 부작용 격리) | PASS |
| AC-B9 | `?candidate_id=B` 무시 | 위와 동일 테스트(+9종 쿼리 파라미터 스푸핑 변형) | PASS |
| AC-B10 | 키 집합 정확, 내부 식별자 비노출 | `api-list.spec.ts:[AC-B6][AC-B10]`, `[AC-B10]`(recruiter_id/rubric_template_id/이메일까지 미노출) | PASS |
| AC-B11 | 회귀(생성→시작→재개→종료→목록 반영) | `api-list.spec.ts:[AC-B11]`, `[AC-B11+]`(만료 상세/410/타인 403/404/422), `[AC-B11++]`(405 라우트 충돌 없음) | PASS |
| AC-B12 | `ruff check app alembic/env.py` | §6 게이트 1 | PASS (unit-19 변경 파일 기준) |
| AC-F1 | 비로그인 랜딩, 목록 미호출 | `home.spec.ts:[AC-F1]` | PASS |
| AC-F2 | 신규 candidate 빈 상태 | `home.spec.ts:[AC-F2]` | PASS |
| AC-F3 | CTA 클릭 → consent → 복귀 시 카드 1개 | `home.spec.ts:[AC-F3]`(+ 키보드 Enter 변형) | PASS(1차 실행에서 테스트 자체 결함 발견·수정 후 PASS, §4.2) |
| AC-F4 | 7상태 카드 표시 | `home.spec.ts:[AC-F4][AC-F10]`, `[AC-F4+]`(일시 로케일/점수 경계) | PASS |
| AC-F5 | 중단 배너 | `home.spec.ts:[AC-F5]`(+ `[AC-F5+]`: 1건/만료뿐/completed뿐) | PASS(1차 실행에서 테스트 자체 결함 발견·수정 후 PASS, §4.2) |
| AC-F6 | 10건 제한 | `home.spec.ts:[AC-F6]`, `[AC-F6+]`(배너는 전체 응답 기준) | PASS |
| AC-F7 | 로딩 스켈레톤 | `home-states.spec.ts:[AC-F7]`, `[AC-F7+]`(로딩 중 CTA 실동작) | PASS |
| AC-F8 | 목록 500 에러 UI | `home-states.spec.ts:[AC-F8]`, `[AC-F8+]`(단절/403/404), `[AC-F8++]`(재시도 실패 유지) | PASS |
| AC-F9 | 목록 401 → 랜딩 | `home-states.spec.ts:[AC-F9]` | PASS |
| AC-F10 | 타인 세션 비노출(프런트) | `home.spec.ts:[AC-F4][AC-F10]` | PASS |
| AC-F11 | recruiter/admin 화면 | `home.spec.ts:[AC-F11]`, `[AC-F11+]`(admin) | PASS |
| AC-F12 | 하이드레이션 #418 없음 | `home-states.spec.ts:[AC-F12]`, `[AC-F12+]`(경로 조합), `[AC-F12 대조군]`(검출기 동작 증명), `[AC-F12++]`(JS 비활성 시 서버 HTML) | PASS |
| AC-F13 | 반응형/접근성 | `home-a11y.spec.ts:[AC-F13]`×2(Tab 순서·재시도 포커스), `[AC-F13+]`×8(390px/320px/랜드마크/색대비/색외 라벨/reduced-motion/줌 겹침/**긴 이름**) | **부분 FAIL** — 8건 중 7건 PASS, "긴 이름(100자 무공백)" 1건 FAIL → **DEF-001**(§6) |
| AC-F14 | 로그아웃 | `home.spec.ts:[AC-F14]`(+ 계정 전환 변형) | PASS |
| AC-F15 | lint/tsc/build | §6 게이트 1 | PASS |

추가로 인수 조건에 명시되지 않았지만 위험도가 있어 임의로 포함한 케이스(원칙 "명백히 위험한 케이스는 범위를 벗어나도 테스트"): XSS(사용자 이름에 `<img onerror>`/`<script>` 삽입, `home.spec.ts` "[보안]"), 무효 토큰 잔존 시 즉시 폐기(`home.spec.ts` "[예외]"), 무인증 상태의 `/interviews/new` 접근 시 로그인 리다이렉트(`home.spec.ts` "[예외]"), 세션 300건+만료 28건 규모 스모크(`api-list.spec.ts`, 10초 이내), 정렬 동률 타이브레이커·`started_at NULL` 혼합 정렬. **전부 PASS.**

### 4.2 실행 로그(요약) 및 발견·조치한 테스트 자체 결함 2건

`frontend/e2e/unit-19/`(`api-list.spec.ts`, `home.spec.ts`, `home-states.spec.ts`, `home-a11y.spec.ts`, `helpers.ts`, `ui.ts`)을 실제로 실행한 결과:

```
cd frontend
E2E_BASE_URL=http://127.0.0.1:3720 E2E_API_URL=http://localhost:8720/api/v1 \
  npx playwright test e2e/unit-19/ --workers=2 --reporter=list
```
- 1차 실행: **60 tests, 57 passed, 3 failed.**
- 실패 3건을 원인 분석한 결과 **2건은 테스트 코드 자체의 결함**(제품 결함 아님), **1건은 실제 제품 결함**(DEF-001, §6)으로 판명:
  1. **[테스트 결함, 수정함] `home.spec.ts` AC-F3**: `getComputedStyle(el).outlineWidth`가 `"3px"`인지로 "CTA 강조 해제"를 검증했으나, `outline-style: none`(강조 꺼짐)인 요소도 브라우저의 `outline-width` 초기값(`medium` 키워드가 통상 3px로 해석됨)이 `"3px"`로 보고되는 CSS 특성 때문에 오탐(false positive)이 발생했다(`border-width`와 달리 `outline-width`는 `outline-style: none`이어도 0으로 collapse되지 않음). `.ctaEmphasis` 클래스는 실제로 `outline: 3px solid`를 **무조건**(포커스 여부와 무관) 지정하므로, 강조 여부는 `outlineStyle`(`"solid"` vs 그 외)로 판별해야 정확하다. `outlineStyle`을 확인하도록 수정 후 재실행 PASS. 제품 코드(`CandidateHome.tsx`/`.module.css`)는 원인이 아니었다(변경 없음).
  2. **[테스트 결함, 수정함] `home.spec.ts` AC-F5**: 배너의 표시 일시가 카드의 일시와 같은지 대조하는 로케이터가 `cards(page).nth(1).locator("div").first()`였는데, 카드 DOM 구조(`<li class="card"><div class="cardMain"><div class="cardDate">…</div><div class="tags">…</div><div class="score">…</div></div><a>…</a></li>`)상 `div`를 문서 순서로 찾으면 `.first()`는 가장 바깥의 `cardMain`(날짜+상태+점수 텍스트가 전부 합쳐짐)이 선택되고, 실제 날짜만 담은 `cardDate`는 `.nth(1)`이다. `.nth(1)`로 수정 후 재실행 PASS. 배너 자체의 실제 표시 텍스트에는 애초에 올바른 일시가 포함되어 있었다(실패 로그의 "Received string"에 날짜가 그대로 보임) — 제품 결함이 아니었다.
  3. **[제품 결함, Open] `home-a11y.spec.ts` AC-F13+ "긴 이름(100자, 공백 없음)"**: §6 DEF-001 참고. 테스트 자체는 올바르며 제품 코드를 수정해야 한다.
- 두 테스트 결함 수정 후 재실행: **60 tests, 59 passed, 1 failed(DEF-001만 재현, 안정적으로 재현됨 — 3회 반복 확인).**
- 백엔드 API 21건(`api-list.spec.ts`)은 최초 실행부터 전부 PASS(이전 세션에서 이미 rubric FK 관련 테스트 결함 1건을 발견·수정해 둔 상태를 그대로 재확인).

### 4.3 게이트 1(정적 분석/린트) 재확인 결과

| 명령(작업 디렉터리) | 결과 |
|---|---|
| `ruff check app/api/v1/interviews.py app/schemas/interview.py`(`backend`, unit-19 변경 파일만) | **All checks passed!** |
| `ruff check app alembic/env.py`(`backend`, 프로젝트 전체) | 에러 3건 — 전부 `services/job_watchdog.py`·`services/turn_numbering.py`·`worker/tasks.py`(unit-7이 현재 병렬로 작업 중인 파일, unit-19 비접촉 범위). unit-19 소관 파일은 위처럼 0건이므로 unit-19 자체의 게이트 1은 통과로 판정. unit-7 소관 결함이므로 이 보고서에서 조치하지 않음(오케스트레이터 참고용으로만 기록) |
| `npm run lint`(`frontend`) | 0 errors, 7 warnings — 기존 `app/interviews/new/page.tsx:57`(unit-19 소관 아님, 기존) 1건 + `frontend/e2e/unit-20/support.ts` 6건(unit-20 소관, unit-19 비접촉). unit-19가 추가한 `frontend/e2e/unit-19/*`는 0 errors/0 warnings(단, `helpers.ts`의 Playwright fixture 콜백 매개변수명이 `use`였던 것이 `react-hooks/rules-of-hooks`와 충돌해 최초 실행 시 error 2건 발생 → React 19의 `use()`가 예약어처럼 취급되는 lint 규칙과의 이름 충돌로 판단, Playwright는 매개변수 이름에 의미를 두지 않으므로 `runTest`로 개명해 해결. 동작 변경 없음, 오탈자 수준의 기계적 리네이밍으로 직접 수정함) |
| `npx tsc --noEmit --incremental false`(`frontend`, `e2e/`·`playwright.config.ts` 포함) | 통과(exit 0), `tsconfig.tsbuildinfo`/`next-env.d.ts` 미변경(실행 전후 sha256 동일, `eb6dc015…`/`1b59d4c6…`) |
| `NEXT_PUBLIC_API_BASE_URL=http://localhost:8720/api/v1 npm run build`(`frontend`) | 통과, 12개 라우트 생성, 에러 0. 빌드 산출물에 `localhost:8720`이 내장됨을 `.next/static/chunks` grep으로 확인(`.env.local`의 8000 기본값이 아니라 셸 환경변수가 우선 적용됨을 실측 확인) |

## 5. 커버리지
- 인수 조건 커버리지: **27/27 (100%)** — AC-B1~B12, AC-F1~F15 전부 최소 1개 이상의 자동화 테스트에 매핑(§4.1). 이 중 AC-F13은 문자 그대로의 절차(390px 가로 스크롤·터치 타깃·Tab 순서·포커스 링)는 전부 PASS이나, 06이 위험 판단으로 추가한 확장 케이스("100자 무공백 이름")에서 실패(DEF-001) — AC-F13 자체의 리터럴 범위는 충족했으나 그 원칙을 확장한 경계값에서 결함을 발견했다.
- 기능적 분기 커버리지(정성 평가, 커버리지 도구 미사용 — 이 스위트는 pytest-cov가 아니라 Playwright 기반이라 라인 커버리지 계측 도구를 적용하지 않음. 근거: `test-infra.md` §5의 프런트 표준도 Playwright이며, 이 유닛의 백엔드 변경은 핸들러 1개+스키마 1개로 소규모라 분기를 전수 열거하는 편이 라인 커버리지 수치보다 신뢰도가 높다고 판단):
  - `list_my_interviews`/`_to_list_item`: 401(무토큰/쓰레기/변형/refresh토큰/탈퇴계정) 5종, 403(recruiter/admin/역할변경) 3종, 200(빈/1건/3건/7상태/300건) 5종, lazy expiry(단건/경계/다건동시커밋/동시요청경합) 4종, 정렬(정상/동률타이브레이커/NULL혼합) 3종, 쿼리 파라미터 스푸핑 9종, 응답 키 집합·내부식별자 비노출 — 전부 실행·확인.
  - `CandidateHome.tsx`: `state.kind`(loading/ready/error) 3분기, `isEmpty` 2분기, `resumables.length`(0/1/2+) 3분기, `items.length`(0/1~10/11+) 3분기, `role`(candidate/recruiter/admin) 3분기, `report_status`(none/queued/ready/failed) 4분기, `status`(5종) — 전부 실행·확인.
- 커버되지 않은 부분과 사유:
  - 실제 스크린리더(NVDA/VoiceOver 등) 음성 출력 검증 — 도구 미보유, `role`/`aria-*`/포커스 순서/대비로 대체 검증(05 노트 §4에 이미 명시된 한계, 06도 동일 한계 확인).
  - 다크/고대비 테마 — 04 설계가 라이트 단일 테마이므로 해당 없음.
  - 실제 다계정 동시접속 부하(수백 동시 사용자) — 이 유닛의 AC 범위 밖(REQ-002는 개별 사용자 목록 조회), §8에 규모 측정치만 기록.
  - Celery 워커가 실제로 소비하는 `/start` 이후의 비동기 파이프라인 — unit-7 범위, `status=live`로의 동기 전이까지만 확인.

## 6. 결함(Defect) 목록

| ID | 설명 | 재현 절차 | 심각도 | 상태 | 조치 내용 |
|----|------|-----------|--------|------|-----------|
| DEF-001 | `[C-03]` 홈 헤더(`<h1>{user.name}님, 환영합니다`)가 공백 없는 긴 사용자 이름에서 줄바꿈되지 않아, 390px 뷰포트에서 페이지 전체에 가로 스크롤이 발생한다(AC-F13 "390px 가로 스크롤 없음" 원칙 위반). 백엔드 `name` 필드는 `Field(min_length=1, max_length=100)`(`backend/app/schemas/user.py:11`)로 100자·공백 无제한을 명시적으로 허용하므로, 이는 비현실적인 입력이 아니라 스키마가 실제로 승인하는 경계값이다. | `frontend/e2e/unit-19/home-a11y.spec.ts` "[AC-F13+] 긴 이름(100자, 공백 없음/한글)…" 테스트로 재현(`"A".repeat(100)` 및 `"가나다라".repeat(25)` 두 값 모두 재현, viewport 390×844). 재현율 3/3(반복 실행). 스크린샷: `frontend/test-results/…test-failed-1.png`(Teardown 시 삭제, §7). | **Medium** — 핵심 기능(로그인·목록·CTA)은 계속 동작하고 페이지 나머지 요소는 정상이나, 명시적 반응형 AC를 위반하고 모바일 사용성을 저해한다. 데이터 손실·보안 영향 없음. | **Fixed(05 재작업 완료, 07 회귀 스윕에서 공식 재검증 예정)** | 05가 `.header h1`에 `min-width:0; overflow-wrap:anywhere;` 2줄 추가로 조치(줄바꿈 방식 채택 — 저장소 기존 관례(`globals.css` `.chat-bubble__text`)·04 접근성 원칙과 정합, 말줄임 기각). 격리 재현(실제 컴포넌트 마크업+CSS 로드, Playwright)으로 수정 전 `scrollWidth=1739>clientWidth=390`(재현) → 수정 후 `390=390`(해소) 대조 확인. **단, `.harness-tmp/next.lock`을 당시 unit-20이 보유 중이라 실제 Next.js 앱을 통한 `home-a11y.spec.ts` 전체 재실행은 하지 않음 — 07 회귀 스윕(또는 lock 확보 후 06)에서 공식 재확인 필요.** 상세는 `docs/harness/units/unit-19-note.md` "## DEF-001 재작업" 참고. |

결함 0건이 아니므로 "결함 없음" 서술은 해당 없음. 위 DEF-001 외에 §4.2에서 발견·즉시 수정한 테스트 코드 자체의 결함 2건(제품 결함 아님)은 이 표에 포함하지 않았다(재발 방지를 위해 §4.2에 근거와 수정 내용을 남김).

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트 목록(전부 `.harness-tmp/` 하위, 이전 중단 세션이 남긴 것 포함):
  - `.harness-tmp/u19t06_start_backend.ps1`(재사용), `.harness-tmp/u19t06_backend.{out,err}.log`, `.harness-tmp/u19t06_pids.txt`(백엔드 launcher/listener PID)
  - `.harness-tmp/u19t06_frontend.{out,err}.log`, `.harness-tmp/u19t06_frontend_pids.txt`(프런트 launcher/listener PID)
  - `.harness-tmp/u19t06_perf.py`, `.harness-tmp/u19t06_perf2.py`(이전 세션이 만든 규모 프로브 스크립트, §8 수치의 출처 — 본 세션에서 재실행하지 않고 삭제)
  - `.harness-tmp/u19t06_e2e/`(이전 세션이 만든 E2E 스펙 초안 — 본 세션에서 `frontend/e2e/unit-19/`로 이전 후 원본 삭제)
  - `.harness-tmp/next.lock/`(뮤텍스, 사용 후 즉시 해제)
  - `frontend/test-results/`(Playwright 스크린샷/트레이스 — gitignore 대상이지만 자체 정리 대상, §7 규칙 준수)
- 위 아티팩트를 전부 `.harness-tmp/` 하위(또는 gitignore된 `frontend/test-results/`)에서만 생성했는가: **[x] 예**
- 정리(삭제) 완료 여부: **완료** — 위 목록 전부 삭제 확인(`ls .harness-tmp | grep u19` 결과 없음, `frontend/test-results` 디렉터리 없음). 백엔드(launcher 31720/listener 34004)·프런트(launcher 34440/listener 32256) 프로세스를 정확한 PID로 종료(`Stop-Process -Id`)했고, 종료 후 `netstat`로 포트 8720/3720 리슨 없음 확인. 이미지명 와일드카드 종료는 사용하지 않았다. 다른 유닛의 백엔드/프런트(unit-7 8181/8091, unit-20 8620)는 접촉하지 않았다.
- DB 정리: `python -m tests.support.cleanup --all --dry-run`으로 잔여 마커 계정을 확인한 결과 11건이 남아 있었으나, 전부 `name='u20 e2e'`(2026-09-19 22:24 KST 생성)로 **unit-20 소유**임을 이메일·이름·생성시각으로 확인했다(unit-19 계정은 전부 `harness_test_<uuid4>@harness-test.example` + `u19 …`/커스텀 이름이며 `AccountKit`의 `finally` 정리로 테스트당 즉시 삭제됨). unit-19 자신의 잔여 데이터는 0건이며, 병렬 작업 중인 다른 유닛의 데이터를 삭제하지 않았다(`--all` 실삭제는 실행하지 않음, dry-run만 사용).
- 추적 생성물: `frontend/tsconfig.tsbuildinfo`/`next-env.d.ts`는 최종적으로 세션 시작 시점과 동일한 sha256(`eb6dc015…`/`1b59d4c6…`) — 변경 없음.
- **알려진 미해결 정리 항목(차단 아님, 투명하게 기록)**: `frontend/.next`는 현재 이 유닛의 검증용 빌드(`NEXT_PUBLIC_API_BASE_URL=http://localhost:8720/api/v1`)로 남아 있다. `05-unit-developer`가 남긴 기본값(환경변수 없음, `localhost:8000` 내장) 빌드로 원복을 시도했으나, 원복 재빌드를 위해 `.harness-tmp/next.lock`을 재획득하려 한 시점에 **unit-20이 이미 그 락을 보유 중**이었다(`owner=06-unit-tester(unit-20)`). 최대 90초 대기 후에도 해제되지 않아, 다른 유닛의 작업을 지연시키지 않기 위해 원복을 포기했다(락 강탈 없음, 프로토콜 준수). `.next`는 gitignore 대상이라 `git status`에는 영향이 없으며, 다음으로 `frontend`에서 `next build`/`next dev`를 실행하는 에이전트가 자신의 목적에 맞게 다시 빌드하게 된다(기능적 영향 없음, 참고용으로만 기록).
- **참고(본 절 작성 이후 관측)**: 본 절을 작성한 직후, `frontend/next-env.d.ts`가 `M`으로 바뀌는 것을 재확인했다. 원인을 조사한 결과 unit-19의 작업이 아니라 **unit-20이 현재 보유 중인 `.harness-tmp/next.lock` 하에서 실행 중인 `next dev`**가 `.next/dev/types/...` 경로로 이 파일을 재생성한 것으로 확인했다(`git diff`로 변경 내용이 `./.next/types/...` → `./.next/dev/types/...` 임을 확인, unit-19가 직전에 실행한 `tsc --incremental false`/`next build` 시점의 sha256과는 무관 — 그 시점 값은 §6 게이트 1에 이미 기록됨). `test-infra.md` §5.4에 따라 이런 공유 생성물은 실행자가 수동으로 되돌리지 않는 것이 규약이므로 그대로 둔다. 아래 `git status` 스냅샷에는 이 항목이 포함되어 있으며, **unit-19가 만든 변경이 아님**을 명시한다.
- 정리 후 `git status` 실행 결과 (그대로 첨부):
  ```
  M backend/.env.example
  M backend/app/api/v1/interviews.py
  M backend/app/api/v1/ws.py
  M backend/app/core/config.py
  M backend/app/main.py
  M backend/app/services/celery_app.py
  M backend/app/services/interview_prompts.py
  M backend/app/services/job_queue.py
  M backend/app/services/llm_engine.py
  M backend/app/services/rag_engine.py
  M backend/app/worker/tasks.py
  M backend/docker-compose.yml
  M docs/harness/decisions.md
  M frontend/next-env.d.ts
  ?? "99.현재상태/현재상태_02.png"
  ?? backend/alembic/versions/f2a9c4d81e36_v9_transcripts_unique_turn_index.py
  ?? backend/app/services/job_watchdog.py
  ?? backend/app/services/turn_numbering.py
  ?? frontend/e2e/unit-19/
  ?? frontend/e2e/unit-20/
  ```
  이 중 unit-19가 이번 세션에서 만든 변경은 **`frontend/e2e/unit-19/`(신규, 의도된 산출물 — DEC-030 테스트 코드 보존 원칙)뿐**이다. `frontend/next-env.d.ts`는 unit-20의 `next dev`가 실시간으로 재생성한 것(위 참고 항목)이라 unit-19 소관이 아니다. `backend/app/api/v1/interviews.py`는 05단계가 이미 만들어 둔 변경(수정하지 않음). 그 외(`ws.py`/`config.py`/`main.py`/`services/*`/`worker/tasks.py`/`docker-compose.yml`/`.env.example`/alembic 신규 파일/`job_watchdog.py`/`turn_numbering.py`)는 **unit-7**이, `frontend/e2e/unit-20/`은 **unit-20**이 병렬로 만든 변경이며 이 유닛은 하나도 건드리지 않았다. `docs/harness/decisions.md`는 오케스트레이터 소관이라 이 유닛은 편집하지 않았다(기존에 이미 수정 상태로 있던 것). git add/commit은 수행하지 않았다.
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: **[ ] 없음 / [x] 있음(이전 세션, 규칙 K 3번)** — 이전 세션이 API 사용량 한도로 2회 강제 중단되었으며, 그 재점검·정리(백엔드 잔류 프로세스 PID 7412/9360 확인 후 종료, `next.lock` stale 여부 확인)는 **오케스트레이터가 본 세션 시작 전에 이미 완료**했다(작업 지시문에 명시). 본 세션 시작 시 `.harness-tmp/u19t06_*` 잔여물을 직접 재확인했고(§ 진행상태 검증), `tasklist`로 PID 7412/9360이 이미 존재하지 않음을 재확인한 뒤 이어서 작업했다. 본 세션 자체는 중단 없이 정상 종료했다.

이 절이 완성되었고 `git status`가 (병렬 유닛 변경 외) 깨끗함을 확인했으므로 8절 이하의 판정이 유효하다.

## 8. 리스크 및 잔존 이슈
- **DEF-001(§6) 연계**: 390px에서 긴 사용자 이름 시 가로 스크롤 발생. 위 §6에서 Open 결함으로 등록했다. 08(전체시스템테스트) 착수 전에는 반드시 Fixed 상태여야 한다(안전장치 1번, ORCHESTRATOR.md 1장). 07(통합테스트)은 이 결함과 직접 관련된 회귀 축은 아니므로 병행 착수를 막을 필요는 없다고 판단하지만, 07의 회귀 스윕에 이 케이스가 다시 걸릴 것이므로 05가 먼저 조치하는 편이 재작업 비용이 적다.
- **RISK-1: lazy expiry 커밋 후 N+1 재조회 (성능)**: 이전 세션이 측정(`.harness-tmp/u19t06_perf.py`/`perf2.py`, 본 세션에서 재실행하지 않고 수치만 인용·삭제)한 근거 — 1건 만료 확정 + 나머지 1000행 조회 시 1178ms(기준 무만료 1000행 34ms), 5000행 시 6605ms(기준 135ms); 만료 확정 행당 약 8.5ms 추가 비용(500건 동시 만료 시 약 4.2초 추가 지연 추정). 원인: `_apply_lazy_expiry`가 만료 대상을 커밋한 뒤 전체 목록을 다시 SELECT하는 구조로 보인다(05 노트 §4 "미검증" 항목에서 이미 추정, 06이 실측으로 확인). **판정**: `unit-19-note.md`의 인수 조건(AC-B1~B12) 어디에도 응답 시간 SLA가 명시되어 있지 않고, 03 §4.2도 성능 기준을 규정하지 않는다. 기능적으로는 300건+만료 28건 규모에서 10초 이내(AC 범위 내 규모 스모크, §4.1)로 정상 동작을 확인했다. 실사용에서 한 사용자가 수백 건의 동시 만료 대상을 갖는 상황은 이례적이다(면접 세션은 사용자당 소수 건이 일반적). 따라서 **이번 unit-19 판정을 막는 결함으로 분류하지 않고 Medium 성능 리스크로 등록**하며, 후속 조치로 `_apply_lazy_expiry`를 개별 UPDATE 반복이 아닌 단일 배치 UPDATE(`UPDATE interviews SET status='expired' WHERE candidate_id=:id AND status IN ('live','paused') AND started_at < now() - interval '24 hours'`)로 리팩터링할 것을 권고한다.
- **RISK-2: `POST /interviews` 레이트리밋 없음**: 이전 세션이 120회 연속 요청이 전부 201로 성공함을 확인(본 세션 재실행하지 않음, 수치만 인용). REQ-038/unit-8 범위로 명시적으로 배정되어 있어 이번 REQ-002 판정에는 영향을 주지 않는다(비차단, 정보성 기록).
- **RISK-3: `GET /interviews` 무페이지네이션**: 20000행 응답이 약 4.66MB/약 657ms(이전 세션 측정치 인용). 03 §4.2·04 `[C-03]`은 페이지네이션 파라미터를 규정하지 않았고, 동종 API(`/recruiter/reports`, `/transcripts`)도 무페이지네이션이라 05가 기존 관례를 따른 것으로 판단된다(`unit-19-note.md` §3-4, §5 질문 1 참고). UI는 이미 최근 10건만 렌더링해 화면 성능 영향은 없다. **판정**: REQ-002 인수 조건에 명시적 요구가 없고 기존 API 패턴과 일관되므로 이번 unit 판정을 막는 결함으로 분류하지 않는다. 다만 계정당 세션 수가 매우 커질 경우(레이트리밋 부재인 RISK-2와 결합 시 더 커짐) 응답 크기가 무제한 증가하므로, 05가 제안한 대로 선택적 `limit` 파라미터 도입을 RISK-2(레이트리밋)와 함께 후속 유닛에서 다루는 것을 권고한다.
- **동시 개발 스냅샷 한계(1차 검증에서 보완)**: 이번 06 실행은 `backend/app/core/config.py`·`main.py`·`api/v1/ws.py`·`services/*`·`worker/tasks.py`·`docker-compose.yml`을 unit-7이 **병렬로 동시 수정 중인 시점의 스냅샷**을 대상으로 했다(§7 `git status`의 unit-7 변경 목록 참고). unit-19가 직접 변경한 파일은 `interviews.py`(기존 05 변경, 무수정)뿐이지만, 서버 기동 시 이 공유 모듈들의 **그 순간의 작업 중 코드**가 함께 로드되어 실행됐다. unit-7 병합이 완료되면, 그 변경이 CORS·인증·WS 등 unit-19가 의존하는 공유 경로에 회귀를 일으키지 않았는지 **07(통합테스트) 또는 unit-7 병합 직후 회귀 스윕에서 재확인이 필요**하다(이번 06의 PASS 판정이 unit-7의 최종 병합본을 대상으로 한 것은 아님을 명시).
- **알려진 미검증 항목**: 실기 스크린리더 낭독, 다크/고대비 테마(해당 없음), 수백 동시 사용자 부하(이 유닛 범위 밖).
- **`.next` 빌드 상태**: §7 Teardown에 기록한 대로 검증용 빌드(8720)로 남아 있음(gitignore 대상, 기능적 영향 없음, 다음 프런트 작업자가 재빌드).

## 9. 결론 및 판정
- [ ] PASS
- [x] **CONDITIONAL PASS** — 조건:
  1. **DEF-001(Medium, Open)을 05가 조치**(예: `.header h1`에 `overflow-wrap`/`word-break` 추가)하고, **06이 `frontend/e2e/unit-19/home-a11y.spec.ts`의 해당 케이스만 빠르게 재실행해 Fixed로 전환**한 뒤에 **08(전체시스템테스트) 착수**해야 한다(안전장치 1번 — 08은 모든 REQ의 실질적 완결을 전제). 이 조건이 충족되기 전까지 REQ-002는 "부분 결함 보유(Medium, Open)" 상태로 `traceability.md`에 반영되어야 한다.
  2. RISK-1(N+1 성능)·RISK-3(무페이지네이션)은 이번 판정을 막지 않되, §8에 기록한 후속 조치(배치 UPDATE 리팩터링, RISK-2와 묶은 `limit` 파라미터 도입)가 추적되어야 한다.
  3. AC-B1~B12, AC-F1~F12, AC-F14, AC-F15 및 AC-F13의 리터럴 절차(390px/320px 일반 콘텐츠·Tab 순서·포커스 링·색대비·터치 타깃)는 전부 PASS로 확정되며, 이 부분은 재검증이 필요 없다.
  4. **07(통합테스트) 착수 가능 여부(명시)**: 07은 착수해도 된다 — DEF-001은 단일 CSS 선택자로 국한되어 07의 단위 간 데이터흐름·상태전이 검증 범위와 직접 얽히지 않는다. 다만 07의 feature 수준 회귀 스윕이 `frontend/e2e/unit-19/home-a11y.spec.ts`를 재실행하면 DEF-001이 다시 검출될 것이 확실하므로, **05가 DEF-001을 먼저 고치고 07을 시작하는 편이 07의 재작업 왕복을 줄인다**(권장이지 필수 차단은 아님). 08 착수는 위 1번 조건(Fixed 확인)이 필수다.
- [ ] FAIL

**판정 근거**: 27개 인수 조건 중 26개는 명확한 증거(총 60건의 자동화 테스트, API 21건 + 브라우저 39건, 3회 반복 안정 재현)로 PASS가 증명되었다. 나머지 1개(AC-F13)는 리터럴 절차는 PASS했으나 06이 위험 기반으로 추가한 경계값 확장 케이스에서 실제 제품 결함(DEF-001)을 발견했다. 이 결함은 (a) 핵심 기능을 막지 않고, (b) 원인과 수정 방향이 명확하며, (c) 영향 범위가 CSS 한 선택자로 국한되어 있어, 전체 유닛을 FAIL로 되돌려 처음부터 재검증하기보다 CONDITIONAL PASS로 명확한 조건을 걸어 조치·재확인 경로를 단축하는 것이 이 프로젝트(Tier=High, 20년차 QA 기준)에 더 맞는 판단이라고 결론지었다(규칙 A로 질문할 만큼 해석이 갈리는 사안은 아니라고 판단 — 근거: 인수 조건 문언 자체는 위반되지 않았고 06이 자체적으로 추가한 리스크 테스트에서만 발견됨).

## 10. 내부 검증 (최소 2회, `verification-log-template.md` 사용)
- 1차 검증 결과 요약: 작성자(06) 자가 재검토에서 결함 1건 발견(§8 서술 누락 위험 — unit-7이 동시 수정 중인 공유 백엔드 모듈에 대한 스냅샷 한계 고지 누락) → 즉시 보완.
- 2차 검증 결과 요약: 독립 심사자 관점 재검토에서 결함 1건 발견(§9 판정문에 "다음 단계로 넘어가도 되는가"에 대한 07 착수 가능 여부가 모호 — 명확화) → 즉시 보완. 이후 3차 검증에서 결함 0건 확인, 최종 PASS(검증 로그 자체의 판정).
- 검증 로그 파일 경로: `docs/harness/verify-log_unit-19-test.md`
