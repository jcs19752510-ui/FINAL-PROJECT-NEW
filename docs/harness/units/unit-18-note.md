# unit-18 구현 노트 — Feature H. 부가 UX: 운영자 기본 모니터링 (REQ-016)

- 작성 에이전트: `05-unit-developer`
- 속도 트랙: **L1(최고속, DEC-003)** — 정상 경로 중심 구현, 06단계는 경량 테스트(정상 경로 1~2케이스), 07단계는 "L1 부채"로 등록되어 08 착수 전 정산 필요.
- 입력: `docs/harness/03-system-design.md`(v3, PASS) §4.2(`/ops/health` 표), §7.2(Prometheus 지표: `queue_length`, `gpu_memory_used_bytes`, `error_rate`, `active_sessions`), `docs/harness/04-ux-design.md`(v2, PASS) [O-01] 운영자 모니터링 화면, `docs/harness/traceability.md` REQ-016 행

## 0. 병렬 작업 격리 확인

이 유닛은 unit-4(텍스트 채팅, `interviews.py`/`ws.py`/`transcript.py` 등)·unit-14(동의/삭제, `consents.py`/`users` 관련)와 동시에 병렬 진행되었다. 이번 유닛이 신규로 만든 파일(`backend/app/api/v1/ops.py`, `backend/app/schemas/ops.py`, `frontend/app/admin/ops/page.tsx`)은 두 유닛의 담당 파일과 전혀 겹치지 않는다. 공유 진입점 파일(`backend/app/main.py`, `frontend/lib/api.ts`, `frontend/app/globals.css`)은 각 유닛이 끝부분에 자기 몫만 추가하는 additive 방식으로 편집해 충돌 없이 공존을 확인했다(`main.py`는 편집 중 unit-14의 `consents_router` 등록과 이 유닛의 `ops_router` 등록이 동시에 반영된 상태를 실제로 확인함). **파일 범위 충돌 없음.**

## 1. 구현 범위

### 백엔드
- `backend/app/api/v1/ops.py` — **(신규)** `GET /api/v1/ops/health`. `current_user.role != admin`이면 `403 AUTH_FORBIDDEN`(unit-2가 확립한 인라인 역할 체크 패턴 + `app.api.deps.get_current_user` 재사용, 별도 role 전용 의존성을 새로 만들지 않아 unit-1 인증 미들웨어를 그대로 재사용). 인증 토큰이 없으면 `get_current_user`가 그대로 `401 AUTH_INVALID_TOKEN`을 발생시킨다(unit-1 로직 재사용).
- `backend/app/schemas/ops.py` — **(신규)** `OpsHealthOut`: `queue_length`, `gpu_memory_used_bytes`, `error_rate`, `active_sessions`, `checked_at`, `notes`(필드별 실측/스텁 여부 설명, 아래 §2 참고).
- `backend/app/main.py` — `ops_router`를 `/api/v1` 프리픽스로 등록(1줄 import + 1줄 include, additive).

### 프론트엔드
- `frontend/lib/api.ts` — `OpsHealthOut` 타입 + `getOpsHealth(accessToken)` 추가(파일 끝에 additive).
- `frontend/app/admin/ops/page.tsx` — **(신규)** [O-01] 운영자 모니터링 화면. `getMe`로 role 확인 후 `admin`이 아니면 04-ux-design [G-02] 스타일의 권한 없음 안내(홈으로 링크)를 보여주고 API 호출 자체를 하지 않는다(서버측 403이 최종 방어선이며, 클라이언트 가드는 UX 편의일 뿐 — fail-closed 원칙은 서버가 담당). `admin`이면 7초 간격(5~10초 사양의 중간값)으로 `GET /ops/health`를 폴링해 4개 지표 카드(큐 길이/GPU 메모리 사용량/에러율/활성 세션 수) + 최근 갱신 시각을 표시한다.
  - 로딩: 초기 조회 중 스켈레톤 카드 4개(`.ops-metric-card--skeleton`, `prefers-reduced-motion: reduce` 시 애니메이션 정지).
  - 에러: 폴링 실패 시 마지막 성공값을 화면에서 지우지 않고 헤더에 "갱신 실패" 배지만 노출(03-design §7.2 "낡은 데이터라도 보이는 것이 아예 안 보이는 것보다 낫다" 원칙).
  - 빈 상태: 03-design/04-ux-design 명시대로 해당 없음(지표는 항상 존재하는 응답 스키마).
  - 지표 산출 근거(`notes`)는 `<details>` 접이식 영역으로 노출해, 어떤 지표가 실측이고 어떤 지표가 하위 시스템 미구축으로 인한 0인지 화면에서도 숨기지 않는다.
- `frontend/app/globals.css` — `.ops-*` 클래스 추가(기존 `.interview-room__*`/`.chat-*`와 이름 공간 분리, 파일 끝 additive).

## 2. 지표별 실측/스텁 경계 (가짜 데이터 금지 원칙 — 오케스트레이터 지시 §1 대응)

03-design §7.2가 정의한 4개 지표 중, 이 시점에 실제로 존재하는 하위 시스템은 `INTERVIEWS` 테이블뿐이다. Celery/Redis 큐, GPU AI Worker, Prometheus 메트릭 수집 파이프라인은 모두 아직 코드베이스에 없다(`app/services/job_queue.py`는 unit-2 docstring이 명시한 "정당한 순서상 스텁"으로 job_id만 발급).

| 지표 | 구현 | 근거 |
|---|---|---|
| `active_sessions` | **실측**. `SELECT count(*) FROM interviews WHERE status='live'` | INTERVIEWS 테이블은 실존하며 unit-2/3이 이미 상태머신을 구현해둠. 05단계 자체 검증에서 세션 1건을 실제로 `live`로 전환시켜 0→1 반영을 확인(§6) |
| `queue_length` | 상시 `0` | 실제 큐(Celery/Redis)가 없음 — `job_queue.py`는 job_id만 발급, 큐 길이 개념 자체가 아직 존재하지 않음(unit-4/7/10이 실제 큐를 구축할 예정) |
| `gpu_memory_used_bytes` | 상시 `0` | GPU AI Worker(unit-6/7)가 아직 없어 측정 대상 자체가 없음 |
| `error_rate` | 상시 `0.0` | Prometheus/로그 집계 파이프라인(03-design §7.2)이 이 코드베이스에 아직 도입되지 않음 |

각 필드의 실측/스텁 여부는 응답 `notes`에 한국어 설명으로 명시해, 06단계 테스터와 화면 사용자 모두가 "0"이 "정상적으로 낮음"인지 "측정 불가"인지 혼동하지 않도록 했다. **가짜 수치로 채우지 않았다.**

## 3. 규칙 A 관련 — 질문 여부 판단 (역할 범위: admin vs recruiter)

오케스트레이터 지시문은 "recruiter/운영자 역할만 접근 가능"이라고 했으나, 04-ux-design.md [O-01] 1.4절이 "**관리자(admin) 역할로 로그인** → [O-01] 운영자 모니터링 화면"이라고 **이미 명시적으로 admin으로 확정**해 두었고, `USERS.role` enum도 `candidate|recruiter|admin` 3종으로 recruiter(채용담당자, [R-01] 리포트 열람 화면 담당)와 admin(운영자)을 이미 구분하고 있었다. 따라서 이는 "두 가지 이상의 실질적 해석이 갈리는" 규칙 A 대상이 아니라 설계서가 이미 답을 준 경우로 판단해 **admin 역할만 허용**으로 구현했고, 질문을 던지지 않았다. (근거 문서 위치를 여기 명시해 이후 유닛/06단계가 재해석하지 않도록 함.)

## 4. 설계서 대비 편차

없음. `GET /ops/health` 경로·응답 지표 4종·역할 게이트·화면 구성요소(4개 카드+최근 갱신 시각)·폴링 방식·상태(정상/로딩/빈상태/에러) 모두 03-system-design §4.2/§7.2, 04-ux-design [O-01] 명세를 그대로 따랐다. 지표 값 자체가 대부분 0인 것은 편차가 아니라 §2에서 설명한 "아직 존재하지 않는 하위 시스템의 정직한 반영"이다.

## 5. 수동 확인 필요 부분 (06단계 테스터가 알아야 할 것)

- **admin 계정 생성 경로 없음**: `POST /auth/register`는 `role: "candidate"|"recruiter"`만 허용한다(`backend/app/schemas/user.py`). admin 테스트 계정은 회원가입 후 DB에서 직접 `UPDATE users SET role='admin' WHERE email=...;`로 승격해야 한다(05단계에서 이렇게 재현, §6 참고). 이는 unit-18의 결함이 아니라 admin 계정 자체가 unit-1 범위(자가입 아님)에 없기 때문이다.
- **PostgreSQL/venv**: 기존 `final-project-db`(Docker, 포트 5544)와 `.harness-tmp/venv_05_unit1` 재사용. 신규 Alembic 리비전 없음(신규 테이블/컬럼 없음 — `INTERVIEWS` 기존 컬럼만 조회).
- **`active_sessions`를 1 이상으로 재현하려면**: candidate로 `POST /interviews` → 동의(`ai_interview_notice`) DB INSERT(unit-2-note.md §3 SQL 재사용) → `POST /interviews/{id}/start`로 `live` 전환 후 `/ops/health`를 admin으로 호출하면 된다(§6에서 실제 재현 완료).
- **큐/GPU/에러율 지표가 0에서 바뀌는 시점**: unit-4/7/10이 실제 Celery/Redis 큐와 GPU Worker를 구축하고, 이후 별도 유닛이 Prometheus 연동을 완료해야 이 세 지표가 실측치로 바뀐다. 그전까지 06단계는 이 세 값이 항상 0으로 나오는 것을 "정상"으로 판정해야 한다(응답 `notes` 필드로 확인 가능).

## 6. 6단계 인수조건 (Acceptance Criteria) — L1 경량판, 정상 경로 위주

1. 인증 토큰 없이 `GET /api/v1/ops/health` 호출 시 `401 AUTH_INVALID_TOKEN` 반환.
2. `role=candidate` 계정 토큰으로 호출 시 `403 AUTH_FORBIDDEN` 반환.
3. `role=admin` 계정 토큰으로 호출 시 `200`과 함께 `queue_length=0`, `gpu_memory_used_bytes=0`, `error_rate=0.0`, `active_sessions`(정수), `checked_at`(ISO 타임스탬프), `notes`(4개 키 모두 포함) 반환.
4. candidate가 면접 세션을 생성→동의→`/start`로 `live` 전환한 뒤 admin이 `/ops/health`를 다시 호출하면 `active_sessions`가 이전 값보다 1 증가한다.
5. 프론트엔드 `/admin/ops`: candidate/recruiter 계정으로 로그인한 상태에서 접근하면 "권한이 없습니다" 화면(API 호출 없이 즉시 표시)이 뜨고, admin 계정으로 접근하면 초기 스켈레톤 → 4개 지표 카드와 최근 갱신 시각이 표시된다.

(05단계 자체 검증에서 위 1~4는 curl로, 5는 코드 레벨 로직 검토 + `npm run lint`/`tsc --noEmit`로 확인. 브라우저 렌더링 자체는 06단계가 독립 재현 권장 — Playwright 등 브라우저 자동화 MCP 미연동이므로 05단계는 실제 브라우저 화면 스크린샷까지는 확인하지 않았다는 점을 정직하게 명시.)

## 7. 게이트 1 — 정적 분석/린트

- 백엔드: `ruff check app/api/v1/ops.py app/schemas/ops.py app/main.py` → **통과(에러 0건)**. (최초 1건 E501 라인 길이 초과 발견 → 즉시 줄바꿈으로 수정 후 재통과.)
- 프론트엔드: `npm run lint`(ESLint, `next.config`의 `react-hooks/set-state-in-effect` 룰 포함) → **통과**. (최초 1건 "effect 내부 동기 setState" 위반 발견 → 기존 `frontend/app/page.tsx` 선례와 동일하게 `useState(() => Boolean(token))` lazy 초기값 패턴으로 수정 후 재통과.) `npx tsc --noEmit` → **통과(타입 에러 0건)**.

## 8. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현 일치 — §4 참고(편차 없음).
- [x] 에러 처리 누락 경로 없음 — 인증 없음(401, `get_current_user` 재사용)·권한 없음(403, `AUTH_FORBIDDEN`) 모두 명시적 `AppError`. 프론트 폴링 실패는 예외를 삼키지 않고 `healthError` 상태로 표시.
- [x] 시스템 경계(사용자 입력) 검증 — 이 엔드포인트는 요청 바디/쿼리 파라미터가 없어(GET, 인증 헤더만) 별도 입력 검증 대상이 없음. 응답 스키마는 Pydantic `OpsHealthOut`으로 타입 고정.
- [x] 하드코딩된 시크릿/자격증명 없음.
- [x] 신규 외부 의존성 없음(FastAPI/SQLAlchemy/Pydantic 기존 의존성만 사용, npm/pip 신규 패키지 추가 없음 — 별도 레지스트리 조회 불필요).
- [x] 범위 외 변경 없음 — `interviews.py`, `ws.py`, `transcript.py`, `consent`/`user` 관련 파일은 전혀 건드리지 않았다(§0 참고). `main.py`/`api.ts`/`globals.css`는 기존 내용을 수정하지 않고 끝에 추가만 했다.

## 9. 로컬 최소 동작 확인 (실제 실행 로그 요약)

1. `.harness-tmp/venv_05_unit1` 재사용, 기존 `final-project-db`(Docker, 포트 5544) 재사용. Alembic 변경 없음.
2. `ruff check`, `npm run lint`, `npx tsc --noEmit` 모두 통과(§7).
3. `uvicorn app.main:app --port 8040`으로 새 프로세스 기동(다른 병렬 유닛이 기동해 둔 8000/8031 프로세스와 별개, 서로 간섭 없음 확인).
4. curl로 실제 검증:
   - candidate/recruiter 계정 가입 → recruiter 계정을 DB에서 `role='admin'`으로 승격.
   - candidate 토큰으로 `/ops/health` → `403 AUTH_FORBIDDEN` 확인.
   - 토큰 없이 `/ops/health` → `401 AUTH_INVALID_TOKEN` 확인.
   - admin 토큰으로 `/ops/health` → `200`, `active_sessions=0`, 나머지 지표 0/0.0, `notes` 4개 키 확인.
   - candidate로 면접 생성→동의 INSERT 대신 `POST /consents`(unit-14가 이미 구현해 둔 API를 그대로 사용, 별도 유닛 코드 수정 없이 호출만)→`/start`(202, live) 이후 admin 토큰으로 `/ops/health` 재호출 → `active_sessions=1` 확인(실측 반영 확인).
5. 검증 후 uvicorn 프로세스(포트 8040) 종료 확인(`curl` 연결 실패, http_code=000).
6. 테스트로 만든 candidate/admin 계정 2명, interview 1건, consent 1건을 DB에서 DELETE로 정리 완료. 생성한 임시 파일(`.harness-tmp/u18_admin_reg.json`, `u18_cand_reg.json`, `uvicorn_05_unit18.log`)은 전부 삭제. `git status` 확인 결과 이 유닛이 추가한 파일(`backend/app/api/v1/ops.py`, `backend/app/schemas/ops.py`, `frontend/app/admin/ops/page.tsx`)과 additive 편집(`main.py`/`api.ts`/`globals.css`/`traceability.md`)만 남고 다른 잔여물 없음 — 규칙 K 준수.

## 10. traceability.md 갱신

REQ-016 행: 구현 상태를 "구현 완료(05단계)"로, 단위테스트 칸에 05단계 자체 curl 검증 요약을 기록(06 정식 단위테스트는 미실시임을 명시). 비고에 L1 트랙과 L1 부채(06 정식화 + 07/08 착수 전 정산 필요) 명시.
