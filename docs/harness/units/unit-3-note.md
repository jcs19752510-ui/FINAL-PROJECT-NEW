# unit-3 구현 노트 — Feature B. 면접 세션 관리: 세션 중단/재접속 (REQ-013)

- 작성 에이전트: `05-unit-developer`
- 속도 트랙: **L1(최고속, DEC-003)** — 정상 경로 중심 구현, 06단계는 경량 테스트(정상 경로 1~2케이스), 07단계는 "L1 부채"로 등록되어 08 착수 전 정산 필요.
- 입력: `docs/harness/03-system-design.md`(v3, PASS) §3(INTERVIEWS ERD/상태머신 `status=paused/expired`), §4.2(`/resume`, `code-submissions` GET, `whiteboard` GET), §4.1(`SESSION_EXPIRED` 410), §5.3(가용성)·§5.4(job idempotency), `docs/harness/04-ux-design.md`(v2, PASS) [C-12] 세션 재개 화면, `docs/harness/units/unit-2-note.md`(직전 유닛의 상태머신/모델), `docs/harness/traceability.md` REQ-013 행

## 1. 구현 범위

오케스트레이터 지시대로 **"세션 메타데이터 기준 재개 가능 여부 판단과 상세 조회"에 집중**하고, 실제 turn/코드/화이트보드 콘텐츠 복원은 해당 데이터가 생기는 이후 유닛의 몫으로 명확히 구분했다.

### API (`backend/app/api/v1/interviews.py`, 기존 unit-2 라우터에 추가)
- `GET /api/v1/interviews/{id}` — **(신규)** 본인 소유 세션의 상세 조회. `INTERVIEWS`의 현재 상태(`status`, `report_status`, `started_at`, `ended_at`, `overall_score` 등)와 파생 필드 `resumable`(status가 `live`/`paused`일 때만 true)을 반환. 03-design §4.2 원표에는 이 단수형 GET이 명시적으로 없었으나(있는 것은 `GET /interviews` 목록뿐, unit-2가 미구현), 오케스트레이터의 이번 지시가 "예시"로 명시한 엔드포인트이자 REQ-013("재접속 시 어디까지 진행됐는지 판단")을 만족하는 데 구조적으로 필요한 최소 조회 API라 additive로 판단해 구현함(두 갈래로 해석이 갈리는 사안이 아니라고 판단 — 근거는 §3 참고).
- `POST /api/v1/interviews/{id}/resume` — **(신규, 03-design §4.2 기존 명세 구현)** 중단된 세션 재개. `live` 또는 `paused` 상태에서만 허용:
  - `paused` → `live`로 전환 후 상세 스냅샷(`InterviewDetailOut`) 반환(`200`)
  - 이미 `live` → 멱등하게 그대로 반환(`200`, §5.4 job idempotency 원칙을 세션 재개에도 유추 적용)
  - `scheduled`/`completed` → `409 VALIDATION_ERROR`("애초에 중단이 성립하지 않는 상태")
  - 만료 판정(아래 §2) 결과 `expired` → `410 SESSION_EXPIRED`
  - 설계서 예시에 `job_id`가 없어(다른 엔드포인트와 달리 job enqueue 언급이 없음) 202가 아닌 200으로 응답하고 job도 발급하지 않음.
- 두 엔드포인트 모두 unit-2의 `_get_own_interview()`를 그대로 재사용해 수평 권한(본인 세션만) 검사.

### 세션 만료(SESSION_EXPIRED) — 반응적(lazy) 판정
- `_apply_lazy_expiry()`: `status in (live, paused)`이고 `started_at`으로부터 `SESSION_EXPIRY`(24시간, DEC-026)가 경과했으면 `status=expired`로 즉시 커밋. `GET /{id}`와 `POST /{id}/resume` 양쪽에서 호출해, 조회만 해도 실제 만료 여부가 DB에 반영되도록 함(배치/타이머 잡 신설 없이 "서버가 내려주는 SESSION_EXPIRED를 그대로 표시"하는 [C-12] 명세를 만족).
- 임계값 24시간과 그 근거, 그리고 `live→paused` 자동 전이 트리거(하트비트 등)를 이번 유닛에서 만들지 않기로 한 판단은 **DEC-026**(`docs/harness/decisions.md`)에 기록.

## 2. 규칙 A 관련 — 질문 여부 판단

아래 두 지점은 설계서에 명시가 부족했으나, 다음 근거로 **규칙 A 질문을 발생시키지 않고 자체 판단**해 진행했다(둘 다 DEC-026에 근거 기록):

1. **SESSION_EXPIRED 정확한 시간 값** — 04-ux-design.md [C-12]가 "정확한 시간 값은 05단계 확정"이라고 **이미 이 단계에 판단 권한을 명시적으로 위임**했으므로, 두 가지 이상의 실질적 해석이 갈리는 규칙 A 대상이 아니라 "위임된 구현 세부사항 결정"으로 판단. 24시간으로 확정(이유는 §1 참고). 비가역성이 낮아(상수 하나) 사용자 확인 없이 진행 후 기록.
2. **`live`→`paused` 전이를 실제로 언제/어떻게 발생시키는가(하트비트, WS 접속 끊김 감지 등)** — 이건 03-design 어디에도 메커니즘이 정의돼 있지 않고, 오케스트레이터 지시문 자체가 "없다면 live 상태에서 단순 재접속만으로 재개 가능한지 여부를 설계서 기준으로 판단"하라고 이미 폴백 경로를 제시했다. 이 폴백을 그대로 채택(브라우저 종료 후에도 DB `status`는 `live`로 남고, 재인증만으로 동일 세션을 다시 조회/재개 가능) — 새로운 하트비트/WS 인프라를 이번 유닛에서 발명하는 것은 REQ-013 범위를 벗어나는 신규 서브시스템 추가라 "범위 외 변경 금지" 원칙에 위배된다고 판단해 보류. `paused`는 ERD에 존재하는 값을 방어적으로 받아들이기만 함(향후 unit-4의 WS 게이트웨이가 실제 트리거를 설계할 몫으로 인수인계).

**따라서 이번 유닛에서는 사용자에게 실제로 질문을 던지지 않았다** — 둘 다 설계서가 이미 판단 기준(위임 문구 / 폴백 경로)을 제공한 경우였기 때문.

## 3. 설계서 대비 편차 (사유 포함)

| # | 편차 | 사유 | 되돌리기 난이도 |
|---|---|---|---|
| 1 | `GET /api/v1/interviews/{id}`(단수 상세조회)를 03-design §4.2 표에 명시되지 않았음에도 신규 구현 | REQ-013("재접속 시 어디까지 진행됐는지 복원")을 만족하려면 최소한 단일 세션 상태를 조회할 방법이 있어야 하는데, `GET /interviews`(목록)조차 unit-2에서 미구현 상태였다. 오케스트레이터 지시문이 이 엔드포인트를 구체적 예시로 제시했고, 기존 계약을 깨지 않는 순수 추가라 additive로 판단 | 낮음(순수 추가 GET, 제거해도 기존 계약 영향 없음) |
| 2 | `GET /interviews/{id}/code-submissions`, `GET /interviews/{id}/whiteboard`(03-design v2에 이미 명시된 신규 엔드포인트) **미구현** | 오케스트레이터 지시대로, `CODE_SUBMISSIONS`/`WHITEBOARD_SNAPSHOTS` 테이블/모델이 아직 존재하지 않는다(각각 unit-9/unit-17 책임). 있지도 않은 데이터를 조회하는 API를 먼저 만들면 항상 빈 응답만 내는 껍데기가 되어 오히려 오해를 유발한다. traceability.md REQ-013 비고에 미구현 사실과 담당 유닛을 명시 | 낮음(unit-9/17이 각자 모델 생성 시 해당 GET을 자기 라우터에 추가하면 됨, unit-3과 충돌 없음) |
| 3 | `live→paused` 자동 전이 메커니즘(하트비트/WS 접속 감지) 미구현, `SESSION_EXPIRED` 판정을 배치 잡이 아닌 조회 시점 반응형(lazy)으로 구현 | §2에서 설명한 대로 03-design에 메커니즘 자체가 정의되어 있지 않고, 새로 발명하면 범위 외 신규 서브시스템이 된다. §5.3(SPOF, 베스트에포트, 별도 타이머 인프라 부재 전제)과도 정합적 | 중간(unit-4 WS 게이트웨이가 실제 하트비트/접속끊김 감지를 설계하면 그 결과에 따라 `paused` 전이 지점만 추가하면 되고, `_apply_lazy_expiry`/`resume`의 기존 로직은 그대로 재사용 가능) |
| 4 | `POST /resume` 응답을 `202 {job_id}`가 아닌 `200 {InterviewDetailOut}`으로 구현 | 03-design §4.2의 `/resume` 행에는 `/start`·`/end`와 달리 job enqueue에 대한 언급이 전혀 없다("중단된 세션 재개(직전 질문부터)"만 명시). 재개 자체는 AI 파이프라인 job을 새로 만드는 동작이 아니므로(다음 턴은 기존 `/turns`가 처리할 unit-5 이후 몫) job_id를 발급할 근거가 없다고 판단 | 낮음(다른 엔드포인트와 별개 스키마라 영향 범위 한정) |

## 4. 수동 확인 필요 부분 (06단계 테스터가 알아야 할 것)

- **CONSENTS 데이터 준비**: unit-2와 동일하게 `POST /interviews/{id}/start`를 태우려면 `ai_interview_notice` 동의를 DB에 직접 INSERT해야 한다(unit-2-note.md §3 SQL 그대로 재사용).
- **`paused` 상태 재현 방법**: 이번 유닛은 `live→paused`를 만드는 API가 없으므로(§3 편차 3), 06단계가 `paused`에서의 `/resume`·`GET` 동작을 검증하려면 `UPDATE interviews SET status='paused' WHERE id=...;`로 직접 DB를 조작해야 한다(운영 경로 아님, 개발/테스트 전용).
- **만료(expired) 재현 방법**: `UPDATE interviews SET started_at = now() - interval '25 hours' WHERE id=...;` 후 `GET /{id}` 또는 `POST /{id}/resume`을 호출하면 그 시점에 `status=expired`로 반영되고 `/resume`은 `410 SESSION_EXPIRED`를 반환한다(05단계에서 실제 재현 완료, §6 참고).
- **PostgreSQL/venv**: unit-1·2와 동일하게 `docker compose up -d`(`final-project-db`, 포트 5544)와 `.harness-tmp/venv_05_unit1` 재사용. 새 Alembic 리비전 없음(신규 컬럼 추가 없이 기존 `status`/`started_at`만 활용).
- **code-submissions/whiteboard 재조회는 아직 없음**: 06단계가 [C-12] 세션 재개 화면의 코드/화이트보드 복원까지 테스트하려 하면 대상 API 자체가 없다 — 이번 유닛의 인수조건(§5)에는 포함되어 있지 않으니 혼동하지 말 것.

## 5. 6단계 인수조건 (Acceptance Criteria) — L1 경량판, 정상 경로 위주

1. `scheduled` 상태 세션에 소유자가 `GET /interviews/{id}`를 호출하면 `200`과 함께 `status=scheduled`, `resumable=false`가 반환된다.
2. `scheduled` 상태 세션에 소유자가 `POST /interviews/{id}/resume`을 호출하면 `409 VALIDATION_ERROR`가 반환된다.
3. 동의 부여 후 `/start`로 `live` 전환한 세션에 소유자가 `GET /interviews/{id}`를 호출하면 `resumable=true`가 반환된다(재접속 시뮬레이션: 같은 세션 id로 새로 GET을 호출해도 상태가 그대로 조회됨).
4. 3의 `live` 세션에 소유자가 `POST /interviews/{id}/resume`을 호출하면 `200`과 함께 `status=live`(변화 없음, 멱등)가 반환된다.
5. DB에서 해당 세션 `status`를 `paused`로 직접 변경한 뒤 소유자가 `/resume`을 호출하면 `200`과 함께 `status=live`로 전환된 응답이 반환된다.
6. DB에서 `started_at`을 25시간 전으로 변경한 뒤(상태는 `live`) 소유자가 `GET /interviews/{id}`를 호출하면 `status=expired`, `resumable=false`가 반환되고, 동일 세션에 `/resume`을 호출하면 `410 SESSION_EXPIRED`가 반환된다.
7. `completed` 상태 세션에 `/resume`을 호출하면 `409 VALIDATION_ERROR`가 반환된다.
8. 세션 소유자가 아닌 다른 candidate 계정으로 `GET /interviews/{id}` 또는 `/resume`을 호출하면 `403 AUTH_FORBIDDEN`이 반환된다(수평 권한 상승 차단).
9. 인증 토큰 없이 두 엔드포인트를 호출하면 `401 AUTH_INVALID_TOKEN`, 존재하지 않는 id로 호출하면 `404 NOT_FOUND`가 반환된다.

(이번 05단계 자체 검증에서 이미 실행 확인한 것: 위 1~9 전부 curl로 재현 완료, §6 참고. 06단계가 그대로 재사용해도 되나 unit-1·2-test.md 선례대로 독립 재현을 권장.)

## 6. 게이트 1 — 정적 분석/린트

- `ruff check app alembic/env.py` → **통과(에러 0건)**. 변경 파일(`api/v1/interviews.py`, `schemas/interview.py`) 포함.
- 프론트엔드 변경 없음(이번 유닛도 unit-2와 동일하게 API 전용 — [C-12] 화면 자체 구현은 별도 작업 단위 미배정).
- 신규 Alembic 리비전 없음(기존 컬럼만 사용, 모델/DB 스키마 변경 없음).

## 7. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현 일치 — §3에 모든 편차와 사유 기록. `resume`의 상태 전이 규칙, 만료 판정 방식은 03-design §3/§4.2/§5.3/§5.4 및 04-ux-design [C-12] 그대로 구현.
- [x] 에러 처리 누락 경로 없음 — 존재하지 않는 세션(404), 소유권 없음(403), 잘못된 상태 전이(409), 만료(410), 인증 없음(401) 각각 명시적 `AppError`로 처리. 예외를 조용히 삼키는 코드 없음.
- [x] 시스템 경계(사용자 입력) 검증 — path param `interview_id`는 FastAPI가 `UUID` 타입으로 강제 검증(잘못된 형식은 자동 422). 두 엔드포인트 모두 요청 바디가 없어 별도 스키마 불필요. 상태 전이는 서버가 DB의 현재 `status`/`started_at`을 기준으로 판단.
- [x] 하드코딩된 시크릿/자격증명 없음 — 신규 코드에 시크릿 없음.
- [x] 신규 외부 의존성 실존 확인 — 신규 PyPI/npm 패키지 추가 없음(표준 라이브러리 `datetime.timedelta`만 추가 사용).
- [x] 범위 외 변경 없음 — `code-submissions`/`whiteboard` GET, `paused` 자동 전이 메커니즘, turn/코드/화이트보드 실제 콘텐츠 복원 등은 만들지 않았고 §3에 각각 명시. 기존 unit-2 엔드포인트(`create`/`start`/`end`)는 로직 변경 없이 그대로 재사용(헬퍼 `_get_own_interview` 공유).

## 8. 로컬 최소 동작 확인 (실제 실행 로그 요약)

1. 기존 `final-project-db`(Docker, 포트 5544) 컨테이너 재사용, `.harness-tmp/venv_05_unit1` 재사용. Alembic 변경 없음(`alembic current` → `fdd74cee7615 (head)`, unit-2와 동일).
2. `ruff check app alembic/env.py` 통과.
3. `uvicorn app.main:app --port 8022`로 기동 후 curl로 아래 전체 플로우를 실제 실행·확인(§5 인수조건 1~9 전부 포함):
   - candidate 회원가입/로그인 → `POST /interviews` → `201 scheduled`
   - `GET /interviews/{id}` → `resumable=false`(scheduled) 확인
   - `/resume`(scheduled) → `409 VALIDATION_ERROR`
   - `/start`(동의 없음) → `403 CONSENT_REQUIRED_NOTICE` (unit-2 로직 재사용 확인)
   - DB에 `ai_interview_notice` 동의 INSERT → `/start` → `202 live`
   - **재접속 시뮬레이션**: 새 `GET /interviews/{id}` 호출(클라이언트 상태 없이) → `status=live`, `resumable=true` 확인
   - `/resume`(live) → `200`, 멱등하게 `status=live` 유지 확인
   - DB에서 `status='paused'`로 직접 변경 → `GET` → `paused`/`resumable=true` 확인 → `/resume` → `200`, `status=live`로 복귀 확인
   - DB에서 `started_at`을 25시간 전으로 변경 → `GET` → `status=expired`(반응형 판정 후 DB 반영 확인), `resumable=false` → `/resume` → `410 SESSION_EXPIRED`
   - DB에서 `status='completed'`로 변경 → `/resume` → `409 VALIDATION_ERROR`, `GET` → `resumable=false`
   - 다른 candidate 토큰으로 `GET`/`resume` 시도 → 둘 다 `403 AUTH_FORBIDDEN`
   - 토큰 없이 `GET` → `401 AUTH_INVALID_TOKEN`
   - 존재하지 않는 id → `404 NOT_FOUND`
4. 검증 후 uvicorn 프로세스(포트 8022) 종료 확인(`curl`이 연결 거부로 응답).
5. 테스트로 만든 candidate 2명·interview 1건·consent 1건을 DB에서 직접 DELETE로 정리, 생성한 임시 파일(`.harness-tmp/u3_*.json`, `u3_*.txt`, `uvicorn_05_unit3.log`)은 전부 삭제, `git status` 재확인 결과 이 세션 시작 시점과 동일한 diff(신규 `backend/`만 untracked, 기존 `.harness-tmp/` 잔존 파일은 unit-1 세션이 남긴 것으로 이번 세션이 생성하지 않아 그대로 둠)로 회귀됨 — 규칙 K 준수.

## 9. traceability.md 갱신

REQ-013 행: 작업 단위는 이미 `unit-3`으로 기록되어 있었음. 구현 상태를 "구현 완료(05단계) — 06단위테스트 대기"로 갱신, 비고에 L1 트랙/부채 상태, `code-submissions`/`whiteboard` GET 미구현 사실과 담당 유닛(unit-9/unit-17), `paused` 자동전이 미구현 사실(DEC-026)을 추가.
