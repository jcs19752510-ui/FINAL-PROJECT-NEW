# unit-14 구현 노트 — Feature G. 규제 컴플라이언스 (REQ-029, REQ-030)

- 작성 에이전트: `05-unit-developer`
- 속도 트랙: **L1(최고속, DEC-003)** — 정상 경로 중심 구현, 06단계는 경량 테스트(정상 경로 1~2케이스), 07단계는 "L1 부채"로 등록되어 08 착수 전 정산 필요.
- 입력: `docs/harness/03-system-design.md`(v2, PASS) §3(CONSENTS/DELETION_REQUESTS ERD), §4.2(동의/삭제요청 API 표), §6.2(DEC-023 동의 게이트 이동/실시간 재검사 원칙), `docs/harness/04-ux-design.md`(v2, PASS) [C-13], `docs/harness/units/unit-2-note.md`(CONSENTS 최소 스키마 선행 생성 사실).
- **동시 진행 유닛**: unit-4(텍스트 채팅, REQ-003)가 `backend/app/api/v1/interviews.py`를 병행 수정 중이라는 지시를 받았다. 이번 유닛은 그 파일을 **전혀 건드리지 않았다** — 대신 신규 파일 `backend/app/api/v1/consents.py`를 만들어 동의/삭제요청 API를 완전히 분리했다(§1 참고). 공유 파일인 `backend/app/main.py`(라우터 등록)와 `backend/alembic/env.py`(모델 임포트)는 작업 중 실제로 다른 에이전트(unit-4/추정 unit-18)에 의해 이미 변경된 상태였음을 확인했고(`ops_router`, `ws_router` 등 추가), 그 위에 내 변경분(consents_router import/include, DeletionRequest import)만 **추가(additive)**로 얹어 충돌 없이 반영했다. `docs/harness/traceability.md`도 편집 시점에 디스크상 다른 내용으로 이미 변경되어 있었으나(다른 유닛이 동시에 REQ 행을 갱신 중), REQ-029/030 두 행만 정확히 치환해 다른 REQ 행에는 영향이 없음을 재확인했다(§4). **파일 충돌은 발견되지 않았다.**

## 1. 구현 범위

### 데이터 모델
- `backend/app/models/consent.py`: unit-2가 이미 03-design ERD 그대로 만들어둔 `Consent`(`CONSENTS`) 모델을 **그대로 재사용**, 신규 스키마 변경 없음.
- `backend/app/models/deletion_request.py`(신규): 03-design §3.1 ERD `DELETION_REQUESTS` 그대로(`user_id` FK, `target` enum `biometric_only|full_account`, `status` enum `pending|completed`, `completed_at` nullable). **주의**: 오케스트레이터 지시문은 "pending/processing/completed" 3단계를 언급했으나, 03-design ERD 원문에는 `processing` 상태가 없어(`pending|completed` 2값만) 임의로 추가하지 않고 설계서 원문을 그대로 따랐다(게이트2 "설계서 명세와 실제 구현 일치" 원칙, §2-1 편차 표 참고).
- Alembic: `8a55fda78a42_v4_deletion_requests` 리비전(down_revision=unit-3의 `0df1434883f2`, `alembic history` 확인 후 이어붙임)으로 `deletion_requests` 테이블 생성, 실제 PostgreSQL(Docker `final-project-db`)에 `alembic upgrade head` 적용 완료. `backend/alembic/env.py`에 `DeletionRequest` 모델 임포트 1줄 추가(메타데이터 등록 목적, unit-1/2/3 선례와 동일 패턴).

### API (`backend/app/api/v1/consents.py`, 신규 파일)
- `POST /api/v1/consents` — 로그인 사용자가 자신의 동의(`ai_interview_notice` 또는 `biometric_voice`) 등록. `201`과 함께 생성된 레코드 반환. 동일 종류를 다시 등록해도 거부하지 않고 새 이력 레코드를 추가한다(§2-2 편차 참고).
- `POST /api/v1/consents/{id}/revoke` — 본인 소유 확인(403) 후 `revoked_at` 기록. 이미 철회된 레코드면 `409 VALIDATION_ERROR`.
- `GET /api/v1/users/me/consents` — 내 동의 이력 전체를 `granted_at` 내림차순으로 반환([C-13] 마이페이지가 서버 상태를 그대로 표시하도록 함).
- `DELETE /api/v1/users/me/biometric-data` — `DELETION_REQUESTS`를 `target=biometric_only`, `status=pending`으로 생성, `202` 반환.
- `GET /api/v1/users/me/deletion-requests` — 내 삭제 요청 이력을 `requested_at` 내림차순으로 반환.
- `backend/app/schemas/consent.py`(신규): `ConsentCreate`, `ConsentOut`, `DeletionRequestOut`.
- `backend/app/main.py`에 `consents_router` 등록(다른 라우터들과 동일한 `/api/v1` prefix).

## 2. 설계서 대비 편차 (사유 포함)

| # | 편차 | 사유 | 되돌리기 난이도 |
|---|---|---|---|
| 1 | `DELETION_REQUESTS.status`를 `pending`/`completed` 2값으로만 구현(오케스트레이터 지시문의 "processing" 3단계 언급을 따르지 않음) | 03-design ERD(§3.1)가 명시한 enum이 `pending\|completed` 2값뿐이고, 오케스트레이터 지시문 자체도 "설계서에 명시돼 있으면 그걸 따르고, 없으면 임의로 만들지 말라"고 했다. 설계서가 명시적으로 2값을 정의했으므로 이를 우선했다 — 임의 확장(3번째 상태 추가)은 스키마 변경이라 규칙A 대상(비가역 결정)에 해당할 수 있어 하지 않았다 | 낮음(3번째 상태가 필요해지면 unit-15가 배치 잡을 만들 때 별도 revision으로 enum 값 추가 가능, 기존 데이터 영향 없음) |
| 2 | 실제 하드 삭제(파기) 로직 없음 — `DELETE /users/me/biometric-data`는 `DELETION_REQUESTS`를 `pending`으로 생성만 하고 실제로 음성 데이터를 지우지 않음(애초에 음성 데이터 자체가 이 프로젝트에 아직 저장되지 않음, unit-5 이후 범위) | 오케스트레이터 지시 2번("실제 삭제 처리 자체는 이 단위 범위가 아니면 요청 접수 및 상태 관리까지만") 그대로. 03-design §6.2가 실제 파기를 "delete_requested_data" Celery beat 배치의 책임으로 명시했고, 이 배치는 traceability.md상 REQ-033(unit-15) 소관이다 — 임의로 이번 유닛이 배치까지 만들지 않았다 | 낮음(순수 추가 기능, 이번 유닛의 API 계약을 바꾸지 않고 unit-15가 배치만 얹으면 됨) |
| 3 | `POST /consents`는 동일 `consent_type`의 중복 등록을 거부하지 않고 매번 새 이력 레코드를 생성 | 03-design ERD의 `CONSENTS`에는 `(user_id, consent_type)` 유니크 제약이 없고, "활성 동의 여부"는 항상 "철회되지 않은 레코드가 존재하는가"로 판정하는 방식(unit-2가 이미 `/start`에서 이 방식으로 구현, DEC-023)이라 중복 레코드가 정합성을 깨지 않는다. 설계서에 "중복 등록 거부"에 대한 명시가 없어 두 가지 해석(거부 vs 허용)이 가능했으나, 기존 소비 로직(`_has_active_consent`류 EXISTS 쿼리)과 정합되는 쪽(허용)이 유일하게 실질적으로 문제 없는 해석이라 판단해 규칙A 질문 대상으로 보지 않았다 | 낮음(추후 유니크 제약을 추가하고 싶으면 새 revision으로 가능, 현재 어떤 소비 로직도 단일 레코드를 가정하지 않음) |
| 4 | `biometric_voice` 동의 철회의 실제 강제(차단) 동작을 이번 유닛에서 end-to-end로 재현하지 못함 | 03-design §6.2에 따르면 `biometric_voice` 게이트는 `POST /interviews/{id}/turns`의 **음성(multipart) 제출** 시점에만 실시간 재검사된다. 그런데 음성 제출 엔드포인트 자체가 아직 없다(unit-4는 텍스트 전용 `/turns`만 구현, `app/services/job_queue.py` 및 `interviews.py` 모듈 docstring이 음성 경로를 unit-5/REQ-004·005 범위로 명시). 따라서 이번 유닛은 `CONSENTS` 레코드가 정확히 기록/조회/철회되는 것까지만 curl로 검증했고, `403 CONSENT_REQUIRED_VOICE`가 실제로 반환되는지는 unit-5가 음성 경로를 만든 뒤에 검증 가능하다 — 반대로 `ai_interview_notice`는 unit-2의 `/start` 게이트가 이미 존재해 완전한 end-to-end 통합 검증을 마쳤다(§4 참고) | 해당 없음(unit-5 구현 후 자연히 해소되는 순서상 제약, 코드 결함 아님) |
| 5 | [C-13] 마이페이지 프론트엔드 화면(동의 이력/철회/삭제요청 UI)은 구현하지 않음 | 오케스트레이터의 이번 작업 지시가 "동의 생성/철회/이력조회, 삭제요청 생성/조회" API 구현과 curl 검증만 명시했고(02-planning §9 unit-14 설명도 "생체정보 동의/철회/삭제 **기능**"으로, unit-1처럼 "API+화면"이라 못박지 않음), unit-2/3 선례도 API 전용 유닛에서는 프론트를 만들지 않았다. 04-ux-design [C-13] 화면 명세는 이 API들을 그대로 소비할 수 있도록 응답 스키마(`consent_type`/`granted_at`/`revoked_at`, `target`/`status`/`requested_at`/`completed_at`)를 명세와 1:1로 맞췄다 | 낮음(프론트는 이 API를 그대로 소비하면 되므로 후속 작업 시 API 변경 불필요) |

## 3. 수동 확인 필요 부분 (06단계 테스터가 알아야 할 것)

- **PostgreSQL/venv**: 기존 `final-project-db`(Docker, 포트 5544) 컨테이너와 `.harness-tmp/venv_05_unit1` 재사용. 이번 유닛은 새 venv를 만들지 않았다.
- **`biometric_voice` 동의의 실제 차단(`403 CONSENT_REQUIRED_VOICE`) 재현은 이번 유닛의 커버리지가 아니다** — 그 엔드포인트(`/turns` 음성 multipart)가 아직 없다(§2-4). 06단계가 이 케이스를 요구하면 "unit-5 완료 후 재검증 필요"로 보류해야 한다.
- **실제 데이터 파기는 일어나지 않는다** — `DELETE /users/me/biometric-data`는 상태를 `pending`으로 만들 뿐이며, 이를 `completed`로 바꾸는 배치는 아직 어떤 유닛도 구현하지 않았다(unit-15 예정, REQ-033). 06단계가 "24시간 이내 실제 삭제 완료"를 검증하려 하면 안 된다 — 이는 unit-15/07·08단계의 몫이다.
- **동의 등록 시 IP 기록**: `POST /consents`는 `request.client.host`를 `ip_address`에 기록한다. 로컬 curl 테스트에서는 `127.0.0.1`이 기록됨을 확인했다(프록시/로드밸런서 뒤에서는 `X-Forwarded-For` 처리가 필요할 수 있으나, 03-design에 이 요구가 명시되지 않아 이번 유닛에서 다루지 않았다).

## 4. 6단계 인수조건 (Acceptance Criteria) — L1 경량판, 정상 경로 위주

1. 로그인한 사용자가 `POST /api/v1/consents` (`{"consent_type":"ai_interview_notice"}`)를 호출하면 `201`과 함께 `id`/`consent_type`/`granted_at`(not null)/`revoked_at`(null)이 반환된다.
2. 1 직후 `GET /api/v1/users/me/consents`를 호출하면 방금 생성한 레코드가 목록에 포함된다.
3. 1에서 만든 레코드 id로 `POST /api/v1/consents/{id}/revoke`를 호출하면 `200`과 함께 `revoked_at`(not null)이 채워진 레코드가 반환된다.
4. 3 직후 동일 id로 다시 `revoke`를 호출하면 `409 VALIDATION_ERROR`가 반환된다.
5. 존재하지 않는 임의의 UUID로 `revoke`를 호출하면 `404 NOT_FOUND`가 반환된다.
6. 사용자 A가 만든 동의 레코드를 사용자 B의 토큰으로 `revoke`하면 `403 AUTH_FORBIDDEN`이 반환된다(수평 권한 상승 차단).
7. `consent_type`에 유효하지 않은 값(예: `"bogus"`)을 보내면 `422 VALIDATION_ERROR`가 반환된다.
8. 로그인한 사용자가 `DELETE /api/v1/users/me/biometric-data`를 호출하면 `202`와 함께 `target="biometric_only"`, `status="pending"`, `completed_at=null`인 레코드가 반환된다.
9. 8 직후 `GET /api/v1/users/me/deletion-requests`를 호출하면 방금 생성한 요청이 목록에 포함된다.
10. 인증 토큰 없이 위 엔드포인트(consents/deletion-requests 계열) 아무거나 호출하면 `401 AUTH_INVALID_TOKEN`이 반환된다.
11. **통합 확인(unit-2 회귀 없음 검증)**: `ai_interview_notice` 동의가 없는 상태에서 `POST /interviews/{id}/start`를 호출하면 여전히 `403 CONSENT_REQUIRED_NOTICE`가 반환되고, 이 유닛이 신설한 `POST /consents`로 `ai_interview_notice`를 등록한 뒤 동일 요청을 재시도하면 `202`(status=live)가 반환된다(이번 유닛이 `interviews.py`를 건드리지 않고도 기존 게이트가 새 API로 채워지는 `CONSENTS` 데이터를 그대로 소비함을 증명).

(이번 05단계 자체 검증에서 이미 실행 확인한 것: 위 1~11 전부 실제 서버+DB로 curl 재현 완료, §5 참고.)

## 5. 게이트 1 — 정적 분석/린트

- `ruff check .`(backend 루트, `pyproject.toml` 설정 그대로 — `alembic/versions`는 프로젝트 설정상 제외 대상) → **통과(에러 0건)**. 신규 파일(`models/deletion_request.py`, `schemas/consent.py`, `api/v1/consents.py`) 및 수정 파일(`main.py`, `alembic/env.py`) 전부 포함해 확인.
- 프론트엔드 변경 없음(§2-5 편차 참고, 이번 유닛은 API 전용).

## 6. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현 일치 — §2에 모든 편차와 사유 기록. 응답 스키마 필드명은 ERD 컬럼명 그대로(`consent_type`/`granted_at`/`revoked_at`, `target`/`status`/`requested_at`/`completed_at`).
- [x] 에러 처리 누락 경로 없음 — 존재하지 않는 동의 레코드(404), 소유권 없음(403), 이미 철회됨(409), 잘못된 enum 값(422), 인증 없음(401) 각각 명시적 `AppError`/FastAPI validation으로 처리, 예외를 조용히 삼키는 코드 없음.
- [x] 시스템 경계(사용자 입력) 검증 — `consent_type`은 Pydantic이 `ConsentType` enum으로 강제(잘못된 값은 자동 422). path param `consent_id`는 `UUID` 타입으로 강제. 삭제 요청 생성은 바디가 없어 별도 스키마 불필요.
- [x] 하드코딩된 시크릿/자격증명 없음 — 신규 코드에 시크릿 없음.
- [x] 신규 외부 의존성 실존 확인 — 이번 유닛은 신규 PyPI/npm 패키지를 추가하지 않았다(기존 unit-1/2 의존성만 사용).
- [x] 범위 외 변경 없음 — `interviews.py`(unit-2/3/4 소유 상태머신/턴 로직)는 전혀 수정하지 않았다. `main.py`/`alembic/env.py`는 라우터 등록/모델 임포트 한 줄씩만 추가한 최소 변경이며, 편집 시점에 이미 다른 유닛이 넣어둔 변경분(`ops_router` 등)은 그대로 보존했다. 실제 파기 배치(REQ-033/unit-15 소관)는 만들지 않았다.

## 7. 로컬 최소 동작 확인 (실제 실행 로그 요약)

1. 기존 `final-project-db`(Docker, 포트 5544) 컨테이너 재사용, `.harness-tmp/venv_05_unit1` 재사용.
2. `alembic history` 확인 → 현재 head `0df1434883f2`(unit-3 v3_transcripts) 위에 이어붙임.
3. `app/models/deletion_request.py` 작성 → `alembic/env.py`에 임포트 추가 → `alembic revision --autogenerate -m "v4_deletion_requests"` → `8a55fda78a42` 생성(첫 시도는 임포트 누락으로 빈 diff가 나와 삭제 후 재생성) → 생성된 DDL이 ERD와 1:1 일치함을 육안 확인 → `alembic upgrade head` 적용 확인(`alembic current` → `8a55fda78a42 (head)`).
4. `ruff check .` 통과.
5. `uvicorn app.main:app --port 8031`으로 기동 후 curl로 아래 전체 플로우를 실제 실행·확인:
   - candidate 회원가입/로그인(unit-1 API 재사용)
   - `GET /users/me/consents`, `GET /users/me/deletion-requests` 최초 빈 배열 확인
   - `POST /consents`(`ai_interview_notice`) → `201`, 이력 조회에 반영 확인
   - `POST /consents/{id}/revoke` → `200`, `revoked_at` 채워짐 확인
   - 동일 id 재철회 → `409 VALIDATION_ERROR`
   - 존재하지 않는 id 철회 → `404 NOT_FOUND`
   - `DELETE /users/me/biometric-data` → `202`, `target=biometric_only`/`status=pending` 확인, 이력 조회에 반영 확인
   - 잘못된 `consent_type`(`"bogus"`) → `422 VALIDATION_ERROR`
   - 토큰 없이 조회 → `401 AUTH_INVALID_TOKEN`
   - 2번째 사용자 계정 생성 후, 1번째 사용자의 동의를 2번째 사용자 토큰으로 철회 시도 → `403 AUTH_FORBIDDEN`
   - **통합 회귀 확인**: 신규 interview 생성 → 동의 없이 `/start` → `403 CONSENT_REQUIRED_NOTICE` → 이번 유닛의 `POST /consents`로 `ai_interview_notice` 등록 → 동일 `/start` 재시도 → `202`, `status=live` (unit-2가 만든 게이트가 이번 유닛의 API로 채워진 데이터를 그대로 정상 소비함을 확인, `interviews.py`는 무수정)
6. 검증 후 uvicorn 프로세스(포트 8031) 종료 확인(`curl` 연결 거부 `000` 확인, `ps aux`로 잔여 프로세스 없음 재확인).
7. 생성한 임시 파일(`.harness-tmp/u14_*.txt`, `u14_*.json`, `uvicorn_05_unit14.log`)은 전부 삭제, `git status` 재확인 결과 이번 유닛이 만든 정식 산출물(`backend/app/api/v1/consents.py`, `app/models/deletion_request.py`, `app/schemas/consent.py`, 신규 Alembic 리비전, `main.py`/`alembic/env.py`/`traceability.md` 수정분)만 남고 임시 아티팩트는 없음 — 규칙 K 준수. (다른 동시 진행 유닛들이 남긴 untracked 파일들은 내 산출물이 아니므로 임의로 건드리지 않았다.)

## 8. traceability.md 갱신

REQ-029/REQ-030 두 행의 "구현 상태"를 "구현 완료(05단계) — 06단위테스트 대기"로, "단위테스트" 열을 "PASS(05단계 자체검증)"으로, "비고" 열에 L1 트랙/부채 상태, `biometric_voice` 게이트 end-to-end 검증 한계(unit-5 선행 필요), 실제 파기 배치는 unit-15(REQ-033) 소관이라는 사실을 추가했다. 편집 시점에 다른 유닛이 파일을 동시에 수정 중이었으나 REQ-029/030 두 행만 정확히 치환해 다른 행에는 영향 없음을 확인했다.
