# unit-19 구현 노트 — Feature B. 내 면접 목록 API + [C-03] 지원자 홈 (REQ-002)

- 작성 에이전트: `05-unit-developer`
- 작성 시각: 2026-09-20 03:06 KST
- **속도 트랙: L3(일반)** (DEC-031) — 06단계는 정식(10섹션 전체) + 브라우저 자동화 포함, 07 정식, 규칙 B 원문(Tier=High), 부채 없음
- 입력: `03-system-design.md` §3.1(INTERVIEWS ERD)·§4.2(`GET /interviews`, 신규 DEC-024 갭1)·§4.3("리포트 완료 통지 경로")·§6.1(RBAC), `04-ux-design.md` §2 [C-03](118행)·§1.1(중단/재접속 플로우), `02-planning.md` §9 unit-19, `units/unit-2-note.md`·`unit-3-note.md`, `decisions.md` DEC-024/026/029/031/032, `traceability.md` REQ-002(읽기 전용)
- 범위 제한(병렬 충돌 방지): 백엔드는 `interviews.py`에 핸들러 1개 + `schemas/interview.py`에 스키마 1개만 추가. `backend/app/services/**`·`worker/**`·`models/**`·`main.py`·Alembic·기존 핸들러 무변경. 프런트는 `app/page.tsx`, `lib/api.ts`(additive), 홈 전용 신규 컴포넌트·CSS 모듈만. `app/interviews/[id]/**`·`e2e/**`·`playwright.config.ts`·`package.json`/lock·`traceability.md`/`decisions.md`/`02-planning.md` 무변경. 신규 패키지 없음.

## 1. 구현 범위

| 파일 | 변경 |
|---|---|
| `backend/app/api/v1/interviews.py` | **`GET /api/v1/interviews`**(`list_my_interviews`) + 응답 변환 헬퍼 `_to_list_item` 추가, 스키마 import 정리, 모듈 docstring에 unit-19 범위 문단 추가(기존 "GET /interviews는 범위 밖" 문장에 후속 표기). 기존 핸들러 로직은 변경 없음(단, 아래 "주의" 참고) |
| `backend/app/schemas/interview.py` | `InterviewListItemOut` 추가(기존 클래스 무변경) |
| `frontend/lib/api.ts` | `InterviewListItemOut` 타입 + `listMyInterviews(accessToken)` 추가(additive) |
| `frontend/components/CandidateHome.tsx` (신규) | [C-03] 지원자 홈 본체: 새 면접 시작 CTA, 중단 세션 배너, 최근 면접 카드(일시/상태/점수/리포트 배지), 로딩·빈·에러 상태 |
| `frontend/components/CandidateHome.module.css` (신규) | 홈 전용 스타일(04 §3 토큰만 사용, `globals.css` 무수정) |
| `frontend/app/page.tsx` | candidate 로그인 시 `CandidateHome` 렌더. 비-candidate(recruiter/admin)는 기존 환영 카드 유지 + recruiter에게 `/recruiter` 링크. stale 안내 문구("이후 작업 단위에서 추가됩니다") 제거. **하이드레이션 불일치 수정**(아래 편차 6) |

주의(작업 중 실수와 복구): 핸들러 삽입 중 편집 도구가 기존 `/start` 데코레이터 줄의 공백 하나(`"/start", response_model` → `"/start",response_model`)를 잃은 것을 `ruff` 에러가 아닌 `git diff -U0` 점검에서 발견해 원문대로 복구했다. 최종 diff에서 `/start` 데코레이터 줄 변경 없음(확인 완료).

### API 계약 — `GET /api/v1/interviews`
- 인증: Bearer 필수. 없음/무효 → `401 AUTH_INVALID_TOKEN`. candidate 외 역할 → `403 AUTH_FORBIDDEN`.
- 요청 파라미터 없음(소유자 필터는 토큰의 사용자 id로만 서버가 고정, 쿼리로 `candidate_id`를 넘겨도 무시됨).
- 응답 `200` — `InterviewListItemOut[]`(봉투 없는 배열, `/transcripts`·`/recruiter/reports` 선례와 동일):
  `id, status, report_status, started_at, ended_at, overall_score(문자열 Decimal|null), created_at, resumable`.
  - `resumable` = `status in (live, paused)`(unit-3 `GET /{id}`의 `resumable`과 동일 규칙, 서버가 단일 진실원천).
  - `candidate_id`/`recruiter_id`/`rubric_template_id`는 홈이 쓰지 않으므로 응답에서 제외(최소 노출).
- 정렬: `COALESCE(started_at, created_at)` 내림차순, 동률은 `id` 내림차순. 페이지네이션·필터 없음.
- 부수효과: 24시간(`SESSION_EXPIRY`)을 넘긴 `live`/`paused`는 기존 `_apply_lazy_expiry`로 이 시점에 `expired` 확정(unit-3의 `GET /{id}`/`resume`과 동일 정책 재사용).

## 2. 설계서 → 구현 매핑

| 설계 명세 | 구현 |
|---|---|
| 03 §4.2: 내(지원자 본인) 면접 목록, `status`/`report_status`/`started_at`/`overall_score` 포함 | 4개 필드 모두 응답에 포함(+`id`,`ended_at`,`created_at`,`resumable`). `WHERE candidate_id = current_user.id` |
| 03 §4.2/§4.3: `report_status=ready` → 홈 "리포트 준비 완료" 배지(WS 끊긴 뒤 재방문 확인) | 카드에 `리포트 준비 완료` 배지. `queued`→"리포트 생성 중", `failed`→"리포트 생성 실패", `none`→배지 없음 |
| 03 §6.1 RBAC: candidate = 자신의 면접만 | 소유자 서버 고정 + candidate 외 403(`POST /interviews`와 동일 근거) |
| 04 [C-03] 구성요소: "새 면접 시작" CTA / 중단 세션 배너(있을 때만) / 최근 면접 카드(일시·상태·점수) / 마이페이지 링크 | 모두 구현. CTA → `/interviews/new`(unit-15, `POST /interviews` 후 `/interviews/{id}/consent`로 이동) |
| 04 [C-03] 상태: 정상 / 로딩(스켈레톤 3개) / 빈("아직 진행한 면접이 없습니다. 첫 모의면접을 시작해보세요" + CTA 강조) / 에러(카드 영역만 인라인 "불러오지 못했습니다, 다시 시도", CTA는 항상 동작) | 4상태 구현. 에러는 `role="alert"` 인라인 + "다시 시도" 버튼, CTA는 상태와 무관하게 링크로 항상 활성 |
| 04 §1.1: 재접속 시 "중단된 면접이 있습니다" 배너 → 재개 | 배너 + "이어서 진행"(→ `/interviews/{id}`; 기존 면접장/동의 화면이 live·paused를 이어 진행) |
| 04 §5 접근성 / §6 반응형 | 상태를 색뿐 아니라 텍스트 라벨로 표기, 포커스 링, 터치 타깃 44px+, `aria-busy`/`aria-label`/`role="status"`, 390px 가로 스크롤 없음 |

## 3. 설계서 대비 편차·해석 (전부 기록, 비가역성 모두 낮음)

1. **배너 기준을 `status=paused`가 아니라 `resumable`(live 또는 paused)로 함.** 04 [C-03]은 `status=paused`라고 쓰지만, 현재 `paused`로 전이시키는 코드가 어디에도 없다(unit-3 DEC-026: 브라우저 종료 후 DB에는 `live`로 남고 재인증만으로 재개). 문자 그대로 구현하면 배너가 영원히 뜨지 않아 04 §1.1 플로우(재접속 → 배너 → 재개)가 성립하지 않는다. unit-3의 `resumable` 규칙을 그대로 재사용했다.
2. **비-candidate는 `200 []`이 아니라 `403`.** 설계는 "내(지원자 본인) 면접 목록"이고 §6.1 RBAC는 candidate만 자신의 면접을 갖는다. `POST /interviews`가 이미 candidate 전용 403이라 일관성을 택했다. 프런트는 비-candidate에게 이 API를 호출하지 않는다.
3. **정렬 키 = `COALESCE(started_at, created_at)` 내림차순.** 설계는 "최근 면접"만 명시. 카드에 표시되는 일시와 정렬 키를 일치시켜(시작 전 세션은 생성 일시) 화면상 일시가 뒤죽박죽 정렬되어 보이지 않게 했다. (초안은 `created_at`이었으나 브라우저 확인 중 표시 일시와 어긋나는 것을 보고 변경.)
4. **페이지네이션/필터 미도입.** 설계에 없고 동종 목록(`/recruiter/reports`, `/transcripts`)도 무페이지네이션이다. 대신 UI가 최근 10건만 표시(`RECENT_LIMIT`)하고 초과 시 "최근 10건만 표시합니다(전체 N건)"를 알린다. 배너는 전체 응답 기준. 응답 크기는 무제한이므로 §5 질문 1 참고.
5. **리포트 배지는 링크 없음.** 리포트 화면([C-10]/[C-11])이 저장소에 없다(unit-10/11 범위). 링크를 만들면 404 라우트로 유도하므로 배지는 상태 표시만 한다. `failed`의 재시도 버튼(`POST /report/regenerate`)도 [C-10] 소관이라 만들지 않았다.
6. **`app/page.tsx` 하이드레이션 불일치(React #418) 수정.** 기존 코드는 `useState(() => readAccessToken())`로 첫 렌더 분기를 정해, 토큰이 있는 로그인 상태에서 서버 HTML(랜딩)과 클라이언트 첫 렌더("불러오는 중...")가 달랐다(빌드된 앱에서 재현: 토큰 주입 후 `/` 로드 시 pageerror 1건, 수정 후 0건). 이 파일이 [C-03]의 진입점이라 같은 유닛에서 고쳤다: `useSyncExternalStore`로 마운트 전에는 서버와 같은 "불러오는 중..."만 그린다. 신규 패키지·다른 파일 영향 없음.
7. **카드 링크 규칙**: `scheduled`→`/interviews/{id}/consent`(사전고지 후 시작), 그 외→`/interviews/{id}`(live/paused는 이어서 진행, completed/expired는 기존 면접장 화면의 읽기 전용 대화 이력). "대화 이력 보기"는 기존 화면 동작(`이 세션은 현재 진행 중이 아니라 대화 이력만 열람`)에 기댄 것이라 06에서 라우트 동작 확인 필요.
8. **[C-13] 진입 링크**: 04 [C-03]의 "마이페이지 진입 링크"를 헤더에 배치(`/mypage`). 이 화면에 recruiter용 진입 링크(`/recruiter`)를 추가한 것은 설계에 없는 최소 편의이며 candidate 홈 동작과 무관하다.

## 4. 06 테스터용 수동 확인이 필요한 부분

- **데이터 준비(상태 조작은 SQL)**: 현재 `paused` 전이·`ready` 리포트·`overall_score`를 만드는 운영 경로가 없다(Feature E 미구현). 아래 SQL로 직접 조작한다(개발/테스트 전용):
  `docker exec final-project-db psql -U final_app -d final_project -c "update interviews set status='completed', report_status='ready', overall_score=7.5, started_at=now()-interval '30 hours', ended_at=now()-interval '29 hours' where id='<id>'"` 등.
- **`/start` 경로는 이 유닛이 검증하지 않았다**: `live` 세션은 SQL로 만들었다(`/start`는 Celery/Redis enqueue를 동반하며 병렬 유닛 워커와 충돌 우려). 06이 실제 `/start`로 live를 만들려면 `REDIS_URL`을 논리 DB로 분리할 것.
- **브라우저 필요 항목**: 아래 인수조건 중 "브라우저" 표기 항목(Playwright 또는 수동). 저장소의 `frontend/e2e`·`@playwright/test` 재사용 가능하나 이 유닛은 수정하지 않았다(`e2e`에 홈 회귀 스펙 추가 여부는 06 판단).
- **빌드 산출물 주의**: `next build`를 (a) `NEXT_PUBLIC_API_BASE_URL=http://localhost:8520/api/v1`로 검증용 1회, (b) 환경변수 없이 최종 게이트로 1회 실행했다. 현재 `frontend/.next`는 (b) 기준(기본 `localhost:8000`)이다. 06이 다른 포트의 백엔드를 쓰려면 다시 빌드하거나 `next dev`를 쓸 것(`NEXT_PUBLIC_*`는 빌드 시점 고정).
- **미검증**: 스크린리더 실기 낭독, 다크/고대비 테마(설계상 라이트 단일), 세션 수천 건 규모의 성능, 만료 확정 커밋이 일어난 요청에서의 추가 SELECT(커밋이 세션 내 다른 행을 expire시켜 이후 행 접근마다 재조회가 생길 수 있음 — 코드 검토상의 추정이며 측정하지 않음).

## 5. 미해결 질문 (규칙 A 형식, 모두 비차단 — 합리적 기본값으로 진행함)

1. `[05/unit-19] GET /interviews`에 페이지네이션(`limit`/`offset` 또는 cursor)을 넣을 것인가 / 03 §4.2와 04 [C-03]이 파라미터를 정하지 않아 임의로 계약을 만들 수 없음 / (a) 현 상태 유지: 응답 무제한, 홈은 10건만 표시 — 단순하고 동종 API 선례와 같으나 세션을 대량 생성하는 계정(현재 `POST /interviews` 레이트리밋 없음)은 응답이 커짐 (b) 선택적 `limit`(기본 50, 최대 100) 추가: 안전하지만 계약 신설 — 추천은 (b)를 후속 REQ-038(레이트리밋) 유닛과 함께 처리.
2. `[05/unit-19] 배너 기준을 status=paused에서 resumable(live|paused)로 바꾼 해석(편차 1)이 맞는가` / 설계 문구와 다르지만 `paused` 전이 코드가 없어 문자 구현은 기능 불능 / 이견이 있으면 03/04에서 `live→paused` 전이 정의(하트비트 등)를 먼저 확정해야 함.
3. `[05/unit-19] 비-candidate 403(편차 2) vs 200 []` — 이견이 있으면 핸들러의 역할 검사 3줄만 바꾸면 되고 프런트는 영향 없음.

## 6. 게이트 1 — 정적 분석/린트

| 명령(작업 디렉터리) | 결과 |
|---|---|
| `ruff check app alembic/env.py` (`backend`, `.harness-tmp/venv_05_unit7`의 ruff) | **All checks passed!** (중간에 E501 1건 발생 → 즉시 수정 후 통과) |
| `npm run lint` (`frontend`) | 0 errors, 1 warning — 기존 파일 `app/interviews/new/page.tsx:57` `no-html-link-for-pages`(이 유닛 소관 아님, 미수정) |
| `npx tsc --noEmit` (`frontend`) | 통과(exit 0) |
| `npm run build` (`frontend`) | 통과. 라우트 `/` 등 13개 생성, 에러 없음(검증용 8520 빌드 포함 총 3회 실행, 전부 성공) |
| 백엔드 포매터/타입체커 | `pyproject.toml`에 ruff 설정만 있고 mypy/포매터 설정 없음 → 해당 없음(사실 기록) |
| 프런트 포매터 | 설정 없음 → 해당 없음 |

추적 생성물: 실행 전 `git diff --stat`(`frontend/next-env.d.ts`, `frontend/tsconfig.tsbuildinfo`) = 둘 다 변경 없음(sha256 기록). 실행 후 `tsconfig.tsbuildinfo`만 변경되어 **`git checkout -- frontend/tsconfig.tsbuildinfo`로 원복**했고 `next-env.d.ts`는 변경 없음. 원복 후 두 파일 `git diff --stat` 공백, sha256이 실행 전 값과 일치(`eb6dc015…`/`1b59d4c6…`).

## 7. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] **설계서/디자인서 명세와 구현 일치** — §2 매핑. 해석·편차 8건은 §3에 전부 기록.
- [x] **에러 처리 누락 없음** — 401(토큰 없음/무효/사용자 없음: 기존 `get_current_user`), 403(비-candidate), 프런트: 목록 실패는 인라인 에러+재시도, 401은 토큰 폐기 후 랜딩, 요청 취소 시 `cancelled` 플래그로 언마운트 후 상태 갱신 방지. 삼키는 `catch` 없음(에러는 상태로 노출). 
- [x] **입력 검증/권한(시스템 경계)** — 요청 입력이 없다(파라미터·바디 없음). 소유자 필터를 쿼리가 아닌 인증 사용자로 고정: 브라우저·API 검증에서 (a) B의 세션이 A 목록에 나타나지 않음, (b) `?candidate_id=<B>`를 붙여도 A 목록 `[]`, (c) A가 B 세션 상세 조회 시 403(기존 동작), (d) recruiter 403, (e) 무토큰/쓰레기 토큰 401. 외부 API 응답은 프런트 `request()`가 `ApiError`로 정규화하며 응답 필드는 TS 타입으로만 신뢰하므로 렌더 시 React 이스케이프에 의존(`dangerouslySetInnerHTML` 없음).
- [x] **하드코딩 시크릿 없음** — 신규 코드에 시크릿·URL 하드코딩 없음(API base는 기존 `NEXT_PUBLIC_API_BASE_URL`). 로컬 확인용 DB 자격증명은 `docker-compose.yml` 개발 값을 확인용으로만 썼고 저장소에 남기지 않음.
- [x] **신규 외부 의존성 없음** — `package.json`/`requirements*.txt` 무변경(`git status`상 병렬 유닛의 변경분만 존재).
- [x] **범위 외 변경 없음** — 파일 범위 준수. 유일한 범위 인접 수정은 `page.tsx`의 하이드레이션 수정(편차 6)과 stale 문구 제거로, 둘 다 [C-03] 진입 파일 안이다.

## 8. 로컬 동작 확인 로그 (2026-09-20 02:50~03:03 KST, 05단계 자체 확인 — 테스트 결과서 아님)

환경: 백엔드 `uvicorn` 포트 **8520**(`.harness-tmp/venv_05_unit7` python 읽기 전용 사용, `REDIS_URL=redis://localhost:6389/15`·`CORS_ORIGINS`·`COOKIE_SECURE=false`를 환경변수로만 지정, `.env` 미열람), 프런트 `next start` 포트 **3520**(빌드 시 API base 8520 주입). Docker `final-project-db`(5544)·`final-project-redis`(6389) 사용. 브라우저는 저장소 `@playwright/test`의 Chromium을 라이브러리로만 사용하는 임시 스크립트(`.harness-tmp/u19_*`, 종료 후 삭제)로 실행.

API(curl 대신 임시 파이썬 스크립트, 정확한 상태 확인):
- 무토큰 401 / 쓰레기 토큰 401 / 신규 candidate `200 []` / recruiter `403 AUTH_FORBIDDEN`.
- 계정 B에 세션 7개 생성 후 SQL로 상태 조작(scheduled·live 1h·live 25h·paused 2h·completed+ready 7.5점·completed+queued·completed+failed): `200`, 7건, 순서 `[scheduled, live(1h), paused(2h), completed/queued(3h), completed/failed(4h), live(25h)→expired, completed/ready(30h)]` = 기대한 `COALESCE(started_at, created_at)` 내림차순과 일치, 응답 키는 스키마의 8개 필드와 정확히 일치, `resumable`은 live·paused만 true.
- 25시간 경과 live 세션이 목록 호출 한 번에 DB에서 `expired`로 확정됨(SQL 재조회 `expired`).
- A 목록에 B 세션 없음(`[]`), `?candidate_id=<B>` 무시(`[]`), A→B 세션 상세 403, recruiter 여전히 403.

브라우저(Chromium, 33개 점검 **전부 통과**):
- 비로그인 랜딩, 목록 API 미호출 / 신규 계정 빈 상태(문구·CTA 강조·카드 0·배너 없음) / "새 면접 시작" → `/interviews/{id}/consent` 이동 → 홈 복귀 시 "시작 전" 카드 1개(링크=consent) / 로그아웃.
- 계정 B: 카드 7개, 정렬·링크 규칙(scheduled=consent, 나머지=`/interviews/{id}`), "리포트 준비 완료" 배지 정확히 1개, "생성 중"/"생성 실패" 배지, 점수 7.5, 상태 라벨 5종, 중단 배너("외 1건") 링크=가장 최근 resumable, 만료 세션은 "대화 이력 보기", 배너 클릭 → 면접장 라우트.
- 로딩 스켈레톤 3개 + 로딩 중 CTA 표시, 목록 500 강제 시 인라인 `role="alert"` + CTA 유지 + "다시 시도" 성공 시 복구, 목록 401 강제 시 토큰 폐기 후 랜딩.
- Tab 순서(마이페이지→로그아웃→새 면접 시작→카드 링크), 390px 가로 스크롤 0·터치 타깃 44px 미만 0, 마이페이지 링크 이동, recruiter: `/recruiter` 링크 노출·CTA 미노출·`GET /interviews` 미호출.
- 하이드레이션: 토큰 주입 후 `/` 로드 콘솔/pageerror 0건(수정 전 #418 1건 재현), 비로그인 `/`·`/login`·`/mypage`도 0건.
- 스크린샷으로 데스크톱(정상·빈 상태)과 모바일 레이아웃 육안 확인.

이 확인 중 발견해 이미 고친 것: (1) 정렬 키/표시 일시 불일치(§3-3), (2) 하이드레이션 불일치(§3-6), (3) 편집 도구가 삭제한 `/start` 데코레이터 공백(§1 주의). 확인 스크립트 자체의 오류(Next 라우트 어나운서의 `role="alert"` 선택, 재시도 버튼 셀렉터 모호성)는 스크립트만 수정했고 제품 결함이 아니다 — 단 **06은 `role="alert"` 로케이터를 `main [role="alert"]`로 좁혀야 한다**(Next가 빈 `role="alert"` 라우트 어나운서를 삽입).

## 9. 06 테스터용 인수조건 (Acceptance Criteria)

전제: 백엔드 기동(자체 포트), `harness_test_<uuid>@harness-test.example` 계정 사용, 세션 상태 조작은 §4의 SQL. 종료 후 자기 계정·연쇄 데이터를 정확한 id로 삭제.

### 백엔드(curl/HTTP 클라이언트)
| # | 절차 | 기대 결과 |
|---|---|---|
| AC-B1 | Authorization 없이 `GET /api/v1/interviews` | `401`, `code=AUTH_INVALID_TOKEN` |
| AC-B2 | `Authorization: Bearer garbage` | `401`, `code=AUTH_INVALID_TOKEN` |
| AC-B3 | 세션이 없는 신규 candidate로 조회 | `200`, 본문 `[]` |
| AC-B4 | recruiter 계정으로 조회 (세션 유무와 무관) | `403`, `code=AUTH_FORBIDDEN` |
| AC-B5 | candidate가 `POST /interviews` 3회 후 조회 | `200`, 3건, 모두 `status=scheduled`,`report_status=none`,`resumable=false`,`started_at=null`,`overall_score=null`, `created_at` 내림차순(마지막 생성 세션이 첫 원소) |
| AC-B6 | SQL로 세션별 상태 조작(completed+ready+`overall_score=7.5`, live `started_at=now()-1h`, paused `now()-2h`) 후 조회 | 각 항목의 `status`/`report_status`/`overall_score`(문자열 `"7.5"`)/`resumable`(live·paused만 true)가 DB와 일치, 순서는 `COALESCE(started_at, created_at)` 내림차순 |
| AC-B7 | live 세션의 `started_at`을 `now()-25h`로 바꾼 뒤 조회 | 해당 항목 `status=expired`,`resumable=false`; SQL 재조회 시 DB에도 `expired` 저장됨 |
| AC-B8 | 계정 A와 B 각각 세션 보유. A 토큰으로 조회 | A의 세션만 포함, B 세션 id 0건 |
| AC-B9 | A 토큰으로 `GET /interviews?candidate_id=<B의 user id>` | 여전히 A의 세션만(파라미터 무시) |
| AC-B10 | 응답 항목의 키 집합 | 정확히 `id,status,report_status,started_at,ended_at,overall_score,created_at,resumable` (`candidate_id`/`recruiter_id`/`rubric_template_id` 없음) |
| AC-B11 | 회귀: `POST /interviews`(201), `POST /{id}/start`(동의 후 202), `GET /{id}`, `POST /{id}/resume`, `/turns`, `/transcripts` 기존 동작 | 변경 없음(기존 unit-2/3/4 테스트 재실행 통과) |
| AC-B12 | `ruff check app alembic/env.py` | 에러 0 |

### 프런트엔드(브라우저 필요 — Playwright 또는 수동, 로그인은 `/login` UI 사용)
| # | 절차 | 기대 결과 |
|---|---|---|
| AC-F1 | 비로그인 `/` | 랜딩(로그인/회원가입 링크), `GET /interviews` 호출 없음 |
| AC-F2 | 세션 없는 신규 candidate 로그인 | "○○님, 환영합니다", "최근 면접" 아래 "아직 진행한 면접이 없습니다. 첫 모의면접을 시작해보세요.", 카드 0개, 배너 없음, "새 면접 시작" 강조 |
| AC-F3 | "새 면접 시작" 클릭 | `/interviews/{새 id}/consent`로 이동; 홈 복귀 시 "시작 전" 카드 1개, 액션 "사전고지 확인하고 시작"(href=`/interviews/{id}/consent`) |
| AC-F4 | 다건 계정(scheduled/live/paused/completed·ready·queued·failed/expired) 로그인 | 카드 수=세션 수(최대 10), 서버 정렬 순서 그대로, 상태 라벨(시작 전/진행 중/중단됨/완료/만료), "리포트 준비 완료" 배지는 ready 세션에만, "리포트 생성 중"/"실패" 배지, 점수 `7.5`, 점수 없으면 "아직 없음", 만료 세션 액션은 "대화 이력 보기" |
| AC-F5 | live/paused 세션이 있을 때 | "중단된 면접이 있습니다." 배너(`role="status"`), 가장 최근 resumable 세션 링크, 2건 이상이면 "(외 N건은 아래 목록에서 확인)". 클릭 시 `/interviews/{id}` 이동 |
| AC-F6 | 세션 11건 이상 계정 | 카드 10개 + "최근 10건만 표시합니다 (전체 N건)." |
| AC-F7 | 목록 API 응답 지연 주입 | `aria-busy` 스켈레톤 3개, 그동안 CTA 표시·클릭 가능 |
| AC-F8 | 목록 API 500 주입 | 카드 영역에만 `role="alert"` "불러오지 못했습니다. 다시 시도해주세요." + "다시 시도" 버튼, CTA 유지. 주입 해제 후 재시도 → 목록 복구 (`main [role="alert"]`로 로케이터 한정) |
| AC-F9 | 목록 API 401 주입 | `sessionStorage.access_token` 삭제, 랜딩 표시 |
| AC-F10 | 다른 계정 세션 비노출 | 계정 A 화면에 B의 세션 id(링크 href)가 하나도 없음 |
| AC-F11 | recruiter 로그인 | 환영 카드 + "지원자 리포트 목록으로 이동"(`/recruiter`), "새 면접 시작" 없음, 네트워크에 `GET /interviews` 없음 |
| AC-F12 | 하이드레이션 | 토큰이 저장된 상태로 `/` 새로고침 시 콘솔 error·pageerror 0건(React #418 없음) |
| AC-F13 | 반응형/접근성 | 390px에서 가로 스크롤 없음, 링크·버튼 높이 ≥44px, Tab으로 마이페이지→로그아웃→새 면접 시작→카드 액션 순서 도달, 포커스 링 표시 |
| AC-F14 | 로그아웃 | 랜딩으로 전환, sessionStorage 토큰 삭제 |
| AC-F15 | `npm run lint`(에러 0, 기존 warning 1건 허용) / `npx tsc --noEmit` / `npm run build` | 전부 통과 |

## 10. 정리(규칙 K) 및 `git status`

- 자신이 띄운 프로세스만 종료(백엔드 launcher 26792·uvicorn 17668 → 코드 수정 후 재기동한 launcher 30300·uvicorn 34776, 프런트 34672 → 재빌드 후 재기동한 33532). 종료 후 포트 8520/3520 리슨 없음 확인. 다른 에이전트의 `8422` uvicorn·Adobe node는 손대지 않음.
- DB: 이 유닛이 만든 계정 8개(전부 `harness_test_<uuid>@harness-test.example`)와 연쇄 데이터(interviews 18, transcripts/whiteboard/code/consents/deletion_requests 각 0)를 **정확한 id 목록**으로 삭제하고 재조회로 `users 0 / interviews 0` 확인. `backend/tests/support/cleanup.py`는 사용하지 않음. Docker 컨테이너 중지/삭제 없음, Redis 논리 DB 15에 Celery 워커가 없어 남은 job 영향 없음(다른 유닛 워커는 DB 0).
- **테스트 계정 형식 공지 반영(오케스트레이터, unit-22 규약)**: 이 유닛의 계정은 `harness_test_<12hex>@harness-test.example` 형식(전체 UUID 36자 아님, 이름 `u19 empty/many/recruiter`)이라 unit-22 정리 헬퍼가 인식할 수 없다. 공지 수신 시점에 재조회한 결과 **이미 전부 삭제된 상태**였다(위 8개 계정 = 3회 확인 실행분, 정확한 id 목록 기준 삭제, `--all` 미사용). 재조회: 이름 `u19 empty/many/recruiter` 0건, 이메일 `^harness_test_[0-9a-f]{12}@harness-test\.example$` 0건, `harness_test_%` 중 전체-UUID 형식이 아닌 계정 0건 → 잔여 0건. 연쇄 데이터는 FK상 계정 삭제 전에 제거했고 남을 수 없다. 다른 에이전트/실사용자 데이터는 조회 외에 접촉하지 않았다. 이후 이 유닛에서 새 계정은 만들지 않았다(06 등이 새로 만들 때는 `account_factory`의 전체 UUID 형식을 써야 한다).
- `.harness-tmp/`의 이 유닛 산출물(`u19_*` 스크립트·스크린샷·로그·PID 파일·상태 JSON) 전부 삭제. 기존 잔여물(`venv_05_unit*`, `venv_06_unit5`, `unit9/12/13_server.log`)은 무변경. (`u22t*`/`venv_06_unit22`는 내가 만든 것이 아니며 정리 시점에 이미 없었다 — unit-22 쪽 정리로 추정.)
- 추적 생성물: `frontend/tsconfig.tsbuildinfo` 원복 완료(§6). `.next`(gitignore)는 최종 빌드(기본 API base) 상태.
- **최종 `git status --short` 중 이 유닛 변경**: `M backend/app/api/v1/interviews.py`, `M backend/app/schemas/interview.py`, `M frontend/app/page.tsx`, `M frontend/lib/api.ts`, `?? frontend/components/CandidateHome.tsx`, `?? frontend/components/CandidateHome.module.css`, `?? docs/harness/units/unit-19-note.md`.
  그 외 `M/??` 항목(`.gitignore`, `backend/alembic/env.py`, `ws.py`, `config.py`, `main.py`, `models/transcript.py`, `services/*`, `worker/`, `docker-compose.yml`, `pyproject.toml`, `requirements*.txt`, `alembic/versions/e4b6…`, `docs/harness/{02-planning,decisions,traceability,verify-log_*}.md`, `docs/harness/units/unit-{7,20,22}-*`, `unit-22-test.md`, `verify-log_unit-*-test.md`, `docs/harness/test-infra.md`, `frontend/app/globals.css`, `frontend/app/interviews/[id]/**`, `frontend/components/WebcamPreview.tsx`, `frontend/lib/useMediaQuery.ts`, `frontend/e2e/`, `frontend/playwright.config.ts`, `frontend/package*.json`, `99.현재상태/`)는 **병렬로 진행된 다른 유닛·오케스트레이터의 변경**이며 이 유닛은 건드리지 않았다. 커밋/푸시 없음.

## 11. traceability.md REQ-002 갱신 제안 (오케스트레이터가 반영 — 이 유닛은 수정하지 않음)

- "작업 단위": `unit-2, unit-19` (변경 없음)
- "구현 상태" 끝의 `**[v3]** unit-19 신규 배정(미착수).`를 다음 문자열로 교체:
  `**[v3]** unit-19 구현 완료(05단계, L3, 06 대기): backend/app/api/v1/interviews.py GET /api/v1/interviews(내 면접 목록 — candidate 전용·본인 세션만·COALESCE(started_at,created_at) 내림차순·비-candidate 403·24h 경과 live/paused lazy expiry, 응답 InterviewListItemOut은 backend/app/schemas/interview.py) + [C-03] 지원자 홈(frontend/app/page.tsx, frontend/components/CandidateHome.tsx/.module.css; 최근 면접 카드·resumable(live|paused) 중단 배너·리포트 준비 완료 배지·로딩/빈/에러 상태, 홈 하이드레이션 #418 수정). 리포트 배지의 링크·failed 재시도 CTA는 [C-10]/[C-11](unit-10/11) 범위. 자체 확인: API 점검 전부·브라우저 33항목 통과, 상세 unit-19-note.md`
- 비고: 설계 대비 편차 3건(배너=resumable 해석, 비-candidate 403, 무페이지네이션+UI 10건 표시)은 `unit-19-note.md` §3·§5 참조.
