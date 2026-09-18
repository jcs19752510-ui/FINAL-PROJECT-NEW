# unit-2 구현 노트 — Feature B. 면접 세션 관리 (REQ-002)

- 작성 에이전트: `05-unit-developer`
- 속도 트랙: **L1(최고속, DEC-003)** — 정상 경로 중심 구현, 06단계는 경량 테스트(정상 경로 1~2케이스), 07단계는 "L1 부채"로 등록되어 08 착수 전 정산 필요.
- 입력: `docs/harness/03-system-design.md`(v3, PASS) §3(INTERVIEWS ERD/상태머신), §4.2(`/interviews` POST/`/start`/`/end`), §6.1(RBAC), §6.2(DEC-023 동의 게이트), `docs/harness/04-ux-design.md`(v2, PASS) [C-03]/[C-04]/[C-05]/[C-06]/[C-09], `docs/harness/units/unit-1-note.md`(인증 미들웨어/User 모델 재사용)

## 1. 구현 범위

오케스트레이터 지시대로 **세션 생성/시작/종료 3개 엔드포인트**만 다룬다(`/resume`은 REQ-013/unit-3, `GET /interviews` 목록 조회는 traceability.md REQ-002 매핑에는 포함돼 있으나 이번 유닛 지시 범위에서 명시적으로 제외됨 — §2-6 참고).

### 데이터 모델
- `backend/app/models/interview.py`: 03-design §3.1 ERD `INTERVIEWS` 그대로(`status` enum: scheduled/live/paused/completed/expired, `report_status` enum: none/queued/ready/failed, `candidate_id`/`recruiter_id` FK to users, `overall_score` numeric(3,1)). `rubric_template_id`는 컬럼만 만들고 FK 제약은 걸지 않음(§2-1 편차 참고).
- `backend/app/models/consent.py`: `CONSENTS` 테이블의 **최소 구현**(`/start`의 DEC-023 게이트가 구조적으로 필요로 하는 스키마만). 전체 동의관리 API는 이번 범위가 아님(§2-2 편차).
- Alembic: `fdd74cee7615_v2_interviews_and_consents` 리비전(down_revision=unit-1의 `c74075595ceb`)으로 `interviews`/`consents` 테이블 및 관련 enum 타입 생성, 실제 PostgreSQL(Docker `final-project-db`)에 `alembic upgrade head` 적용 완료.

### API (`backend/app/api/v1/interviews.py`)
- `POST /api/v1/interviews` — 로그인한 candidate가 자신의 세션 생성(`status=scheduled`, `report_status=none`). recruiter/admin은 `403 AUTH_FORBIDDEN`.
- `POST /api/v1/interviews/{id}/start` — 본인 소유(`candidate_id` 일치) + `status==scheduled` 확인 후 **DEC-023 게이트**: `CONSENTS`(`ai_interview_notice`, `revoked_at IS NULL`)만 실시간 재조회로 검사(`biometric_voice`는 여기서 절대 검사하지 않음 — §6.2 그대로). 통과 시 `status=live`, `started_at` 기록, `opening_question` job enqueue(스텁, §2-3) 후 `202 {job_id, message, interview}` 반환.
- `POST /api/v1/interviews/{id}/end` — 본인 소유 + `status==live` 확인 후 `status=completed`, `ended_at` 기록, `report_status=queued`, `report_generation` job enqueue(스텁) 후 `202 {job_id, interview}` 반환.
- `backend/app/services/job_queue.py` — 아직 없는 Celery/Redis 큐·AI Worker에 대한 **경계 인터페이스**(§2-3).
- `app/main.py`에 `interviews_router` 등록.

### 인가(수평/수직 권한)
- `get_current_user`(unit-1)를 그대로 재사용.
- 수직: `POST /interviews`는 `role==candidate`만 허용(recruiter/admin 차단) — 03-design §6.1 "candidate(자신의 면접만)"과 `candidate_id` FK 명명에서 직접 도출.
- 수평: `_get_own_interview()`가 `interview.candidate_id != current_user.id`이면 무조건 `403 AUTH_FORBIDDEN` — 다른 지원자의 세션 ID를 알아내도 시작/종료 불가(실제 curl로 검증, §4).

## 2. 설계서 대비 편차 (사유 포함)

| # | 편차 | 사유 | 되돌리기 난이도 |
|---|---|---|---|
| 1 | `INTERVIEWS.rubric_template_id`를 nullable UUID 컬럼으로만 생성, FK 제약(및 대상 테이블 `RUBRIC_TEMPLATES`) 없음 | 03-design ERD는 `rubric_template_id`를 FK로 표기했으나 `RUBRIC_TEMPLATES`는 unit-13(REQ-014, Feature F)이 아직 만들지 않았다. unit-1이 이미 확립한 선례(03-design §3.3 "이후 변경은 유닛 단위로 순차 revision 추가", ERD 전체를 한번에 만들지 않음)를 그대로 따름. MVP 기본 경로(§6.1 지원자 자율 연습)에서는 이 값이 항상 null이라 기능 손실 없음. unit-13이 `RUBRIC_TEMPLATES`를 만들 때 별도 revision으로 FK 제약을 추가해야 함(인수인계) | 낮음(추가 revision으로 FK만 붙이면 됨, 기존 데이터 영향 없음) |
| 2 | `CONSENTS` 테이블을 **최소 스키마로 이번 유닛에서 선행 생성**(전체 동의관리 REST API는 만들지 않음) | `/start`의 DEC-023 게이트("`ai_interview_notice` 동의만 검사")는 REQ-002/03-design §4.2 자체가 `/start` 엔드포인트 계약의 일부로 명시한 요구사항이라, 이를 검사하려면 최소한 조회 가능한 테이블이 있어야 한다. `POST /consents`, `GET /users/me/consents`, `/consents/{id}/revoke`, `GET /interviews/{id}/pre-notice` 등 동의 관리 REST API 전체(REQ-029/030/032)는 traceability.md상 unit-14/unit-15의 책임이며 이번 유닛에서 만들지 않았다 — 즉 "REQ-002를 올바르게 구현하는 데 구조적으로 필요한 최소 스키마"만 선행하고, "동의 자체를 관리하는 기능"은 곁다리로 추가하지 않았다. **실제 curl 검증 시에도 이 이유로 동의 등록은 앱 API가 아니라 `docker exec ... psql`로 DB에 직접 INSERT/UPDATE해 재현했다**(§4 참고) — unit-14/15가 실제 `POST /consents`/`/revoke`를 구현하면 이 테이블을 그대로 채우게 된다 | 낮음(테이블 스키마가 ERD와 동일하므로 unit-14/15가 그대로 재사용, 마이그레이션 추가 불필요) |
| 3 | **[정당한 순서상 스텁, 임의 편차 아님]** `opening_question`/`report_generation` job enqueue를 실제 Celery+Redis 큐 대신 `job_id`(uuid4)만 발급하는 스텁(`app/services/job_queue.py`)으로 구현 | 오케스트레이터 지시대로, 실제 큐/AI Worker는 unit-4(WebSocket Gateway) 이후·unit-7(LLM)·unit-10(리포트)이 구축할 하위 컴포넌트이며 아직 존재하지 않는다. 이 시점에 실제로 GPU 워커를 만드는 것은 순서상 불가능(범위 외)하다. 대신 **API 응답 계약은 설계서 그대로 완성**했다: `/start`는 `202 {job_id, message}`, `/end`는 `202 {job_id}`를 정확히 반환하며, `INTERVIEWS.status`/`report_status` 상태 전이도 실제로 일어난다. 스텁으로 남긴 것은 오직 "job이 실제로 처리되어 WS `turn_result`/`report_ready`가 도착하는 것" 하나뿐이며, 이는 unit-2의 책임 범위(REQ-002: 상태머신 API) 밖이고 unit-4/7/10의 책임이다. `job_queue.py` 모듈 docstring에 다음 유닛이 내부만 교체하면 되도록 인터페이스 경계(함수 시그니처: `interview_id: UUID -> job_id: str`)를 명시했다 | 낮음(호출부 변경 없이 `job_queue.py` 내부만 실제 Celery 연동으로 교체 가능하도록 설계) |
| 4 | `POST /interviews`를 `role==candidate`로 제한(recruiter/admin은 403) | 03-design §4.2/§9는 role 제한을 명시적으로 기술하지 않았으나, §6.1 RBAC 정의("candidate: 자신의 면접만")와 `INTERVIEWS.candidate_id` FK 명명(면접의 주체가 candidate)에서 직접 도출되는 단일 해석이라 규칙A 질문 대상(두 가지 이상의 실질적으로 다른 해석)은 아니라고 판단. recruiter가 자기 자신을 위해 면접 세션을 만드는 시나리오는 설계서 어디에도 없음 | 낮음(권한 완화는 언제든 가능, 강화는 이미 이 상태) |
| 5 | `/start`/`/end` 응답에 설계서 예시(`{job_id, message}`/`{job_id}`)보다 넓은 `interview` 필드(전체 상태 스냅샷)를 추가 | 이번 유닛 범위에서 `GET /interviews`/`GET /interviews/{id}`를 만들지 않기로 했으므로(§2-6), 상태 전이 결과(예: `started_at`, `status=live`)를 클라이언트/curl 검증이 즉시 확인할 방법이 응답 바디뿐이다. 설계서의 JSON 예시는 필드 목록을 좁게 제시했을 뿐 "이 필드 외에는 절대 포함 금지"라는 명시적 제약은 없어 additive 확장으로 판단(계약을 깨지 않음 — `job_id`는 예시와 동일한 키/타입으로 최상위에 그대로 존재). 06단계 테스터가 이 필드를 계약 위반으로 오인하지 않도록 여기 명시 | 낮음(필드 제거만 하면 원 계약과 100% 동일) |
| 6 | `GET /api/v1/interviews`(내 면접 목록 조회)를 이번 유닛에서 구현하지 않음 | traceability.md REQ-002 행은 이 GET을 설계 매핑에 포함하고 있으나, 오케스트레이터의 이번 작업 지시("세션 생성/시작/종료 상태머신 API")가 명시적으로 3개 엔드포인트로 범위를 좁혔다. 넓은 traceability 매핑보다 좁은 명시적 작업 지시를 우선했다(임의 확장 자제 — "범위 외 변경 금지" 원칙과 정합). [C-03] 지원자 홈이 이 GET에 의존하므로, 이 엔드포인트는 이후 별도 작업 단위(또는 unit-2 후속 패스)로 넘겨야 한다는 사실을 traceability.md 비고에 남김 | 낮음(순수 추가 기능, 상태머신 로직 변경 없음) |

## 3. 수동 확인 필요 부분 (06단계 테스터가 알아야 할 것)

- **CONSENTS 데이터 준비**: `POST /consents` API가 아직 없으므로(§2-2), 06단계도 `ai_interview_notice` 동의를 준비하려면 아래처럼 DB에 직접 INSERT해야 한다(개발/테스트 전용, 운영 경로 아님):
  ```sql
  INSERT INTO consents (id, user_id, consent_type, granted_at)
  VALUES (gen_random_uuid(), '<user_id>', 'ai_interview_notice', now());
  ```
  철회 재현은 `UPDATE consents SET revoked_at = now() WHERE user_id = '<user_id>';`.
- **PostgreSQL/venv**: unit-1과 동일하게 `docker compose up -d`(backend/, 컨테이너명 `final-project-db`, 포트 5544)와 `.harness-tmp/venv_05_unit1`(재사용 가능)을 사용하면 된다. 이번 유닛은 새 venv를 만들지 않았다.
- **opening_question/report_generation job은 실제로 처리되지 않는다**(§2-3 스텁) — 06단계가 WS로 `turn_result`/`report_ready`를 기다리는 테스트를 설계하면 영원히 오지 않는다. L1 경량판 인수조건(§4)에는 이 부분이 포함되어 있지 않으니 혼동하지 말 것.
- **알림, 자동화 없음**: 큐 길이 429, SESSION_EXPIRED 410 등은 이번 유닛에서 구현하지 않음(각각 §1.3/§4.1 관련이지만 실제 트리거 조건— 대기열/세션 만료 타이머 —은 unit-4/unit-3 이후 범위).

## 4. 6단계 인수조건 (Acceptance Criteria) — L1 경량판, 정상 경로 위주

1. 로그인한 candidate가 `POST /api/v1/interviews`(바디 없음)를 호출하면 `201`과 함께 `status=scheduled`, `report_status=none`, `candidate_id`가 본인 id와 일치하는 `Interview`가 반환된다.
2. recruiter 역할 사용자가 `POST /api/v1/interviews`를 호출하면 `403 AUTH_FORBIDDEN`이 반환된다.
3. 1에서 만든 세션 id로, 해당 candidate에게 `ai_interview_notice` 동의(`revoked_at IS NULL`)가 없는 상태에서 `POST /interviews/{id}/start`를 호출하면 `403 CONSENT_REQUIRED_NOTICE`가 반환된다.
4. 위 상태에서 DB에 `ai_interview_notice` 동의 레코드를 INSERT한 뒤 동일 요청을 다시 보내면 `202`와 함께 `job_id`(문자열), `message`, `interview.status=live`, `interview.started_at`(not null)이 반환된다.
5. 4에서 이미 `live` 상태인 세션에 `POST /interviews/{id}/start`를 다시 호출하면 `409 VALIDATION_ERROR`가 반환된다(중복 시작 차단).
6. 4의 세션 소유자가 아닌 다른 candidate 계정의 access token으로 `POST /interviews/{id}/start` 또는 `/end`를 호출하면 `403 AUTH_FORBIDDEN`이 반환된다(수평 권한 상승 차단).
7. `live` 상태의 세션에 소유자가 `POST /interviews/{id}/end`를 호출하면 `202`와 함께 `job_id`, `interview.status=completed`, `interview.report_status=queued`, `interview.ended_at`(not null)이 반환된다.
8. 7 이후 동일 세션에 `POST /interviews/{id}/end`를 다시 호출하면 `409 VALIDATION_ERROR`가 반환된다.
9. 인증 토큰 없이 위 엔드포인트를 호출하면 `401 AUTH_INVALID_TOKEN`, 존재하지 않는 interview id로 호출하면 `404 NOT_FOUND`가 반환된다.

(이번 05단계 자체 검증에서 이미 실행 확인한 것: 위 1~9 전부 curl로 재현 완료, §5 참고. 06단계가 그대로 재사용해도 되나 unit-1-test.md 선례대로 06단계가 독립적으로 재현하는 것을 권장.)

## 5. 게이트 1 — 정적 분석/린트

- `ruff check app alembic/env.py` → **통과(에러 0건)**. 신규 파일(`models/interview.py`, `models/consent.py`, `schemas/interview.py`, `services/job_queue.py`, `api/v1/interviews.py`) 전부 포함.
- 프론트엔드 변경 없음(이번 유닛은 API 전용 — [C-03]~[C-09] 프론트 화면은 04-ux-design에 명세만 있고 별도 화면 구현 작업 단위가 아직 배정되지 않아 이번 unit-2 지시 범위에 포함되지 않음. 지시문이 "세션 생성/시작/종료 상태머신 API"로 한정했으므로 API 전용으로 해석함).

## 6. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현 일치 — §2에 모든 편차와 사유를 기록했고, 나머지(상태값, enum, 에러코드, 202/201 상태코드, DEC-023 게이트 위치)는 03-design §3/§4.2/§6.2 그대로 구현.
- [x] 에러 처리 누락 경로 없음 — 존재하지 않는 세션(404), 소유권 없음(403), 잘못된 상태 전이(409), 동의 없음/철회(403), 인증 없음(401) 각각 명시적 `AppError`로 처리, 예외를 조용히 삼키는 코드 없음.
- [x] 시스템 경계(사용자 입력) 검증 — path param `interview_id`는 FastAPI가 `UUID` 타입으로 강제 검증(잘못된 형식은 자동 422). `POST /interviews`는 바디가 없어 별도 스키마 불필요. 상태 전이는 서버가 현재 DB 상태를 기준으로 판단(클라이언트가 보낸 값을 신뢰하지 않음).
- [x] 하드코딩된 시크릿/자격증명 없음 — 신규 코드에 시크릿 없음(기존 `.env` 설정 재사용).
- [x] 신규 외부 의존성 실존 확인 — 이번 유닛은 신규 PyPI/npm 패키지를 추가하지 않았다(기존 unit-1 의존성만 사용).
- [x] 범위 외 변경 없음 — unit-3 이후 기능(`/resume`, `/turns`, WebSocket, STT/LLM/TTS, 리포트 실제 생성, 코드/화이트보드, recruiter 대시보드, 동의관리 REST API 전체)은 만들지 않았다. `CONSENTS`/`interview.rubric_template_id`처럼 다른 유닛의 최종 소유 영역과 맞닿은 부분은 전부 "최소 스키마만" 원칙을 지키고 §2에 명시했다.

## 7. 로컬 최소 동작 확인 (실제 실행 로그 요약)

1. 기존 `final-project-db`(Docker, 포트 5544) 컨테이너 재사용, `.harness-tmp/venv_05_unit1` 재사용.
2. `alembic revision --autogenerate -m "v2_interviews_and_consents"` → `fdd74cee7615`(down_revision=`c74075595ceb`) 생성 → `alembic upgrade head` 적용 확인(`alembic current` → `fdd74cee7615 (head)`).
3. `ruff check app alembic/env.py` 통과.
4. `uvicorn app.main:app --port 8020`으로 기동 후 curl로 아래 전체 플로우를 실제 실행·확인:
   - candidate 2명 + recruiter 1명 회원가입/로그인(unit-1 API 재사용)
   - recruiter가 `POST /interviews` 시도 → `403 AUTH_FORBIDDEN`
   - candidate1이 `POST /interviews` → `201 scheduled`
   - candidate1이 동의 없이 `/start` → `403 CONSENT_REQUIRED_NOTICE`
   - candidate2가 candidate1의 세션에 `/start` 시도 → `403 AUTH_FORBIDDEN`(수평 권한 차단)
   - DB에 candidate1의 `ai_interview_notice` 동의 INSERT
   - candidate1이 `/start` → `202`, `status=live`, `job_id` 발급 확인
   - candidate1이 `/start` 재호출 → `409 VALIDATION_ERROR`
   - candidate2가 `/end` 시도 → `403 AUTH_FORBIDDEN`
   - candidate1이 `/end` → `202`, `status=completed`, `report_status=queued`
   - candidate1이 `/end` 재호출 → `409 VALIDATION_ERROR`
   - 토큰 없이 요청 → `401 AUTH_INVALID_TOKEN`
   - 존재하지 않는 id → `404 NOT_FOUND`
   - candidate1의 동의를 `UPDATE ... SET revoked_at=now()`로 철회 후 새 세션 `/start` → 다시 `403 CONSENT_REQUIRED_NOTICE`(철회 재검사 확인)
5. 검증 후 uvicorn 프로세스(포트 8020) 종료 확인(`curl`이 연결 거부로 응답).
6. 생성한 임시 파일(`.harness-tmp/unit2_*.txt`, `u2_r*.json`, `uvicorn_05_unit2.log`)은 전부 삭제, `git status` 재확인 결과 이 세션 시작 시점과 동일한 diff(신규 `backend/`만 untracked)로 회귀됨 — 규칙 K 준수.

## 8. traceability.md 갱신

REQ-002 행: 작업 단위는 이미 `unit-2`로 기록되어 있었음. 구현 상태를 "구현 완료(05단계) — 06단위테스트 대기"로 갱신, 비고에 L1 트랙/부채 상태, `GET /interviews` 미구현(§2-6 편차) 사실, `CONSENTS`/`rubric_template_id` 최소 스키마 선행 사실을 추가.
