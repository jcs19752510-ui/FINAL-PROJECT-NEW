# unit-13 구현 노트 — Feature F. 채용담당자 질문지/루브릭 최소 커스터마이징(REQ-014)

- 작성 에이전트: `05-unit-developer`
- 속도 트랙: **L1**(오케스트레이터 지정, ORCHESTRATOR.md 1장) — 정상 경로 중심 구현. 06단계는 경량 테스트(정상 경로 1~2케이스)로 충분하며, 07단계는 "L1 부채"로 등록되어 08 착수 전 정산이 필요하다.
- 입력: `docs/harness/03-system-design.md`(v2, PASS) §3.1(ERD, RUBRIC_TEMPLATES/QUESTIONS)/§4.2(`/recruiter/rubric-templates`)/§6.1(RBAC, MVP 단일조직 정책)/§3.3(마이그레이션·시드 분리 원칙), `docs/harness/04-ux-design.md`(v2, PASS) [R-01]/[R-03], `docs/harness/units/unit-12-note.md`(recruiter 인증 패턴), `docs/harness/traceability.md` REQ-014 행

## 1. 구현 범위

### 백엔드 (신규)
- `backend/app/models/rubric_template.py`: `RubricTemplate` — `id`/`recruiter_id`(nullable FK, null=시스템 기본)/`name`/`criteria_json`(JSONB, `[{name, weight, description}]`)/`created_at`. 03-design §3.1 ERD와 1:1.
- `backend/app/schemas/rubric_template.py`: `RubricCriterionIn`(name 1~100자, weight 0~100, description 0~500자), `RubricTemplateCreateIn`/`RubricTemplateUpdateIn`(criteria 1~20개), `RubricTemplateOut`(`is_system_default` 파생 필드 포함).
- `backend/alembic/versions/d3f7a2c9e1b4_v7_rubric_templates.py`: `rubric_templates` 테이블 생성 + `interviews.rubric_template_id`에 FK 제약 추가(unit-2가 nullable 컬럼만 만들고 FK를 이번 유닛에 인수인계한 상태였음, `interview.py` 모듈 docstring 참고). `alembic history` 확인 결과 head가 `b84a71b986c5`(unit-9) 하나뿐이라 그 뒤로 이어 붙였고, 다른 병렬 유닛과 리비전 충돌 없음(단일 head 체인 유지 확인).
- `backend/app/api/v1/recruiter.py`(unit-12 소유 파일에 **추가만**, 기존 `/reports` 엔드포인트는 무변경): `GET /recruiter/rubric-templates`(본인 템플릿 + 시스템 기본), `POST /recruiter/rubric-templates`(생성, `recruiter_id=current_user.id` 고정), `PATCH /recruiter/rubric-templates/{id}`(본인 템플릿만 수정 가능, 404/403 명시). `_require_recruiter` 헬퍼(unit-12가 만든 것)를 그대로 재사용.
- `backend/alembic/env.py`: `RubricTemplate` 모델 임포트 1줄 추가(메타데이터 등록, autogenerate용).

### 프론트엔드 (신규)
- `frontend/app/recruiter/rubric-templates/page.tsx`: [R-03] 템플릿 목록 + 상세 편집 폼(템플릿 이름 입력, 평가기준 행 추가/삭제, 저장). 목록에서 시스템 기본 템플릿을 클릭하면 "복사해 시작"으로 처리(폼에 값만 채우고 저장 시 POST로 새 템플릿 생성), 본인 템플릿을 클릭하면 PATCH로 저장.
- `frontend/app/recruiter/page.tsx`: [R-01] 상단에 "질문지/루브릭 관리" 메뉴 링크 1줄 추가(04-ux-design §1.3 R-01 명세).
- `frontend/app/recruiter/recruiter.module.css`: R-03 전용 클래스(`rubricLayout`/`rubricList`/`formInput`/`criteriaRow` 등) 추가.
- `frontend/lib/api.ts`: `RubricCriterion`/`RubricTemplateOut` 타입, `listRubricTemplates`/`createRubricTemplate`/`updateRubricTemplate` 함수 추가.

## 2. 설계서 대비 편차/명확화

- **`/recruiter/questions` 미구현(범위 해석)**: 오케스트레이터 지시문 예시는 "질문 은행에 커스텀 질문 추가/조회" API(`POST/GET /recruiter/questions`)를 언급했으나, 03-system-design/04-ux-design 어디에도 그런 엔드포인트나 recruiter 전용 QUESTIONS 커스터마이징 화면이 정의되어 있지 않다. QUESTIONS 테이블(§3.1)은 RAG 질문은행(Feature C 소유, `embedding`/pgvector 포함)이며 traceability REQ-014 행의 설계 매핑도 애초에 `RUBRIC_TEMPLATES`/`/recruiter/rubric-templates`만 가리킨다. 두 해석이 갈리는 모호함이 아니라 "지시문 예시가 설계서에 없는 기능을 곁다리로 요구한 경우"에 해당한다고 판단해, **설계서에 실제로 정의된 `/recruiter/rubric-templates`만 구현**했다(범위 외 임의 기능 추가 금지 원칙 우선 적용). "질문지... 커스터마이징"은 04-design [R-03]이 명시한 대로 `criteria_json`의 평가기준 항목(항목명+가중치/설명)을 편집하는 것으로 실현된다.
- **목록 조회 범위 해석**: 03-design §6.1은 `/recruiter/reports`(리포트 열람)에 한해 "단일조직 내 모든 recruiter가 모든 리포트 열람 가능"을 명시했으나, RUBRIC_TEMPLATES는 리포트가 아니라 recruiter 개인이 만드는 커스터마이징 자산이다. §3.1 ERD 주석("recruiter_id nullable=시스템기본")도 개별 소유를 전제한다. 이에 따라 `GET /recruiter/rubric-templates`는 **본인 템플릿 + 시스템 기본 템플릿(recruiter_id IS NULL)만** 반환하도록 구현했고, curl 검증으로 recruiter2가 recruiter1의 템플릿을 조회/수정할 수 없음을 확인했다(§4). 이는 규칙 A 질문 대상인 정책적 모호함이 아니라 "리포트 열람"과 "개인 커스터마이징 자산"이라는 서로 다른 개념에 대한 자연스러운 해석 차이라고 판단했다.
- **시스템 기본 템플릿 시드 데이터 없음**: 03-design §3.3 "질문은행 초기 데이터는 별도 시드 스크립트로 관리하고 마이그레이션과 분리"라는 원칙을 그대로 준용해, 이번 마이그레이션에는 `rubric_templates` 시드 행을 넣지 않았다. 따라서 현재 DB에는 시스템 기본 템플릿이 0건이며, [R-03] 빈 상태 문구("아직 만든 템플릿이 없습니다. 기본 템플릿을 복사해 시작하세요")는 실제로 복사할 기본 템플릿이 없는 상태에서도 그대로 노출된다(문구 자체는 오류가 아니나 실질적으로 복사 가능한 대상이 없음). **후속 인수인계**: 별도 시드 스크립트(`seed_rubric_templates.py` 등)로 최소 1~2개 시스템 기본 템플릿을 넣는 작업이 필요하다.
- **`PATCH`가 시스템 기본 템플릿을 직접 수정 못하게 막음**: 04-design [R-03] 빈 상태 문구가 "복사해서 시작"을 전제하므로, `recruiter_id IS NULL`인 템플릿은 소유자가 없어 PATCH 대상에서 제외(403)했다. 복사는 별도 "복제" API 없이 클라이언트가 기존 템플릿 값을 새 템플릿 생성 폼에 채워 넣는 방식(POST 재사용)으로 처리 — 03-design에 별도 clone 엔드포인트가 정의되어 있지 않으므로 새 엔드포인트를 만들지 않았다.

## 3. 다른 유닛과의 파일 충돌 여부

- `backend/app/api/v1/recruiter.py`, `frontend/app/recruiter/page.tsx`: unit-12가 이미 완성한 파일에 **추가(append-only)만** 했다. 기존 `/reports`/`/reports/{id}` 엔드포인트, `_require_recruiter`/`_report_state_message` 함수, 기존 JSX 구조는 한 글자도 수정하지 않았다(diff로 직접 확인).
- `frontend/lib/api.ts`, `backend/alembic/env.py`: 다른 유닛들도 additive로 이어 붙여온 공유 파일 — 이번 유닛도 기존 내용 뒤에 새 함수/임포트만 추가했다.
- `backend/app/models/interview.py`: 수정하지 않음. `rubric_template_id` 컬럼 자체는 unit-2가 이미 만들어 두었고, 이번 유닛은 별도 Alembic 리비전으로 FK 제약만 추가했다(모델 파일의 Python 컬럼 정의는 FK 제약 유무와 무관하게 그대로 유효 — SQLAlchemy `ForeignKey`를 모델에 선언하지 않고 순수 Alembic DDL로만 제약을 추가했으므로 모델 파일 수정 불필요).
- 지시받은 제외 파일(`interviews.py`, `consents.py`, `ops.py`, `whiteboard.py`, `ws.py`, `code_submissions.py`, 음성 관련)은 전혀 열거나 수정하지 않았다.
- **충돌 없음.**

## 4. 수동 확인 필요 부분 (06단계 테스터가 알아야 할 것)

- **recruiter 계정 준비**: unit-12와 동일하게 `POST /auth/register`에서 `role: "recruiter"`로 직접 가입 가능.
- **시스템 기본 템플릿 부재**: 위 §2에서 밝힌 대로 시드 데이터가 없어, 신규 recruiter 계정으로 목록을 조회하면 항상 빈 배열이 반환된다. "기본 템플릿 복사" 흐름은 recruiter가 먼저 템플릿을 1개 만들어야 로컬에서 재현 가능(또는 DB에 직접 시스템 기본 행을 INSERT해 확인).
- **브라우저 렌더링 자체는 미확인**: unit-12 선례와 동일한 한계 — ESLint/tsc 통과와 API 계약 curl 검증까지만 확인, 실제 브라우저 화면(폼 입력/행 추가삭제 상호작용)은 이 환경에 브라우저 자동화 도구가 없어 확인하지 못했다.
- **`weight` 합계 검증 없음**: 각 criterion의 `weight`는 0~100 범위만 검증하고, 여러 항목의 weight 합이 100이 되어야 한다는 제약은 걸지 않았다(02-planning §4.2 "최소 커스터마이징" 범위 판단, L1 트랙에 맞는 최소 검증).

## 5. 6단계 인수조건 (Acceptance Criteria) — L1 경량판, 정상 경로 위주

1. 인증 토큰 없이 `GET /api/v1/recruiter/rubric-templates` 호출 시 `401` 반환.
2. `role=candidate` 계정 토큰으로 `GET`/`POST /api/v1/recruiter/rubric-templates` 호출 시 각각 `403 AUTH_FORBIDDEN` 반환.
3. `role=recruiter` 계정 토큰으로 `POST /api/v1/recruiter/rubric-templates`에 `{"name": "...", "criteria": [{"name": "...", "weight": 40, "description": "..."}]}`를 보내면 `201`과 함께 `recruiter_id`가 현재 사용자 id로 채워진 객체 반환.
4. 같은 recruiter 토큰으로 `GET /api/v1/recruiter/rubric-templates` 호출 시 방금 만든 템플릿이 목록에 포함된다.
5. 같은 recruiter 토큰으로 `PATCH /api/v1/recruiter/rubric-templates/{id}`(본인 템플릿)에 새 `name`/`criteria`를 보내면 `200`과 함께 갱신된 값 반환.
6. **다른** recruiter 토큰으로 위 템플릿을 `PATCH` 시도하면 `403 AUTH_FORBIDDEN` 반환하고, 그 recruiter의 `GET` 목록에는 다른 recruiter의 템플릿이 노출되지 않는다(개인 소유 원칙).
7. 존재하지 않는 UUID로 `PATCH` 시 `404 NOT_FOUND`.
8. 프론트엔드 `/recruiter/rubric-templates`: candidate 계정 접근 시 "권한이 없습니다" 안내(API 미호출), recruiter 계정 접근 시 목록(또는 빈 상태 문구) + 편집 폼이 표시되고, `/recruiter` 페이지에 "질문지/루브릭 관리" 링크로 진입 가능하다.

(05단계 자체 검증에서 1~7은 curl로 직접 재현, 8은 코드 레벨 로직 검토 + `npx eslint`/`npx tsc --noEmit`으로 확인. 실제 브라우저 렌더링은 §4에서 밝힌 대로 06단계 몫.)

## 6. 게이트 1 — 정적 분석/린트

- 백엔드: `ruff check app alembic/env.py` → **통과(에러 0건)**. 신규 마이그레이션 파일(`alembic/versions/d3f7a2c9e1b4_...py`)은 `pyproject.toml`의 `exclude = ["alembic/versions"]` 설정으로 lint 대상에서 제외됨(기존 마이그레이션 파일들과 동일한 관례, 프로젝트 정책이 아니라 lint 설정을 임의로 우회한 것이 아님을 기존 파일에도 동일 규칙이 적용됨을 재확인해 검증).
- 프론트엔드: `npx eslint app/recruiter lib/api.ts --max-warnings=0` → **통과(경고/에러 0건)**. `npx tsc --noEmit` → **통과(타입 에러 0건)**.

## 7. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현 일치 — §2에서 편차(범위 해석, 목록 조회 소유권 해석, 시드 데이터 부재) 사유 명시.
- [x] 에러 처리 누락 경로 없음 — 인증 없음(401), 권한 없음(403, `AUTH_FORBIDDEN` — role 불일치/타 recruiter 소유 템플릿 두 경우 모두), 존재하지 않는 템플릿(404, `NOT_FOUND`) 모두 명시적 `AppError`. Pydantic이 이름 길이/weight 범위/criteria 개수를 422로 자동 검증.
- [x] 시스템 경계 입력 검증 — `RubricCriterionIn`(name 1~100자, weight 0~100, description 0~500자), `RubricTemplateCreateIn.criteria`(1~20개) 모두 Pydantic `Field` 제약으로 서버 측 검증. 경로 파라미터 `template_id`는 FastAPI `UUID` 타입으로 자동 검증(잘못된 형식 422). 프론트도 저장 전 이름/criteria 공백 트림 후 빈 값이면 저장을 막는 클라이언트 측 1차 검증을 추가했으나, 서버 검증이 최종 방어선.
- [x] 하드코딩된 시크릿/자격증명 없음.
- [x] 신규 외부 의존성 없음(백엔드 `requirements.txt`, 프론트 `package.json` 변경 없음 — 레지스트리 조회 불필요). lint 실행을 위해 격리 venv(`.harness-tmp/venv_05_unit13`)에 `ruff`를 설치했으나 이는 개발 도구이지 런타임 의존성이 아니며 `requirements.txt`에 추가하지 않았다(다른 유닛들의 lint 실행 방식과 동일한 관례).
- [x] 범위 외 변경 없음 — 지시받은 제외 파일(면접장/코드에디터/웹캠/화이트보드/동의/운영자/음성 관련) 전혀 건드리지 않음. `recruiter.py`/`recruiter/page.tsx`는 unit-12 기존 코드를 무변경 유지하고 새 코드만 추가.

## 8. 로컬 최소 동작 확인 (실제 실행 로그 요약)

1. `.harness-tmp/venv_05_unit13`(이 유닛 전용 격리 venv, DEC-027) 신규 생성 후 `requirements.txt` 설치, 기존 `final-project-db`(Docker, 포트 5544) 재사용.
2. `alembic history` → 단일 head(`b84a71b986c5`) 확인 후 `d3f7a2c9e1b4_v7_rubric_templates`를 그 뒤에 이어 붙임. `alembic upgrade head` 성공(`rubric_templates` 테이블 생성 + `interviews.rubric_template_id` FK 제약 추가).
3. `ruff check app alembic/env.py`(백엔드), `npx eslint app/recruiter lib/api.ts --max-warnings=0` + `npx tsc --noEmit`(프론트) 모두 통과(§6).
4. `uvicorn app.main:app --port 8213`으로 신규 프로세스 기동(PID 34220, 다른 병렬 유닛과 포트 겹치지 않음), `GET /api/v1/health` → `200` 확인.
5. curl로 실제 검증(신규 candidate/recruiter/recruiter2 3계정 발급 후, UTF-8 파일(`--data-binary @파일`)로 한글 페이로드 전송 — 쉘 따옴표 직접 전달 시 인코딩 깨짐을 발견해 우회):
   - 토큰 없음 `GET /recruiter/rubric-templates` → `401`.
   - candidate 토큰 `GET`/`POST /recruiter/rubric-templates` → 각각 `403`.
   - recruiter 토큰 `GET`(최초, 빈 배열) → `200 []`.
   - recruiter 토큰 `POST`(신규 템플릿) → `201`, `recruiter_id`가 본인 id로 채워짐.
   - recruiter 토큰 `GET`(생성 후) → 방금 만든 템플릿 1건 포함 확인.
   - recruiter 토큰 `PATCH`(본인 템플릿, 이름/criteria 변경) → `200`, 갱신값 반영.
   - recruiter 토큰 `PATCH`(존재하지 않는 UUID) → `404`.
   - recruiter2(별도 신규 계정) 토큰 `PATCH`(recruiter1의 템플릿) → `403`.
   - recruiter2 토큰 `GET` → `200 []`(recruiter1의 개인 템플릿이 보이지 않음, §2 소유권 해석 실측 확인).
6. 검증 후 DB에서 테스트로 만든 템플릿(`백엔드 신입%` name)과 candidate/recruiter/recruiter2 계정 3명을 SQL `DELETE`로 정리 완료. 임시 파일(`.harness-tmp/unit13_*.json`, `*_token.txt`) 전부 삭제.
7. 서버 프로세스는 기동 시 확인한 **정확한 PID(34220)** 하나만 `taskkill //F //PID 34220`으로 종료(이미지 이름 기준 광범위 종료 금지, DEC-028 준수). 종료 후 `netstat`로 8213 포트에 LISTENING 항목이 없음을 확인(TIME_WAIT 잔여 연결만 존재, 정상).

## 9. traceability.md 갱신

REQ-014 행: 작업 단위는 기존대로 unit-13, 구현 상태를 "구현 완료(05단계)"로 갱신하고 구현 산출물(백엔드 모델/스키마/API 3개 엔드포인트 추가, Alembic 리비전, 프론트 신규 페이지 1개+기존 페이지 링크 추가)을 명시. 단위테스트 컬럼은 "06단계 대기"로 표시. 비고에 Speed Track L1, `/recruiter/questions` 미구현 사유, 목록 조회 소유권 해석, 시드 데이터 부재를 명시.
